# drone/relay/manager.py
"""In-memory registry of connected drones and operators, with telemetry fan-out.

A "sink" is any object with `async def send_text(str)`. FastAPI's WebSocket
satisfies this, and tests use a fake. Keeping the manager transport-agnostic is
what makes the routing logic unit-testable without sockets.
"""
from __future__ import annotations

from typing import Protocol

from drone.common.telemetry import LinkTier


class Sink(Protocol):
    async def send_text(self, data: str) -> None: ...


class RelayManager:
    def __init__(self) -> None:
        self._operators: dict[str, set[Sink]] = {}
        self._operators_by_id: dict[str, dict[str, "Sink"]] = {}
        self._drones: dict[str, Sink] = {}
        self._tier: dict[str, LinkTier] = {}

    # --- operators ---
    def add_operator(self, drone_id: str, sink: Sink) -> None:
        self._operators.setdefault(drone_id, set()).add(sink)

    def remove_operator(self, drone_id: str, sink: Sink) -> None:
        self._operators.get(drone_id, set()).discard(sink)

    def operators_for(self, drone_id: str) -> set[Sink]:
        return self._operators.get(drone_id, set())

    # --- addressable operators (for per-peer signaling) ---
    def register_operator(self, drone_id: str, operator_id: str, sink: "Sink") -> None:
        self._operators_by_id.setdefault(drone_id, {})[operator_id] = sink

    def unregister_operator(self, drone_id: str, operator_id: str) -> None:
        self._operators_by_id.get(drone_id, {}).pop(operator_id, None)

    async def send_to_operator(self, drone_id: str, operator_id: str, raw: str) -> bool:
        sink = self._operators_by_id.get(drone_id, {}).get(operator_id)
        if sink is None:
            return False
        await sink.send_text(raw)
        return True

    # --- drones ---
    def register_drone(self, drone_id: str, sink: Sink) -> None:
        self._drones[drone_id] = sink

    def unregister_drone(self, drone_id: str) -> None:
        self._drones.pop(drone_id, None)

    def is_online(self, drone_id: str) -> bool:
        return drone_id in self._drones

    # --- link tier (authoritative, updated from telemetry) ---
    def set_tier(self, drone_id: str, tier: LinkTier) -> None:
        self._tier[drone_id] = tier

    def tier_for(self, drone_id: str) -> LinkTier:
        return self._tier.get(drone_id, LinkTier.RED)  # unknown link = safe default

    # --- sending ---
    async def send_to_drone(self, drone_id: str, raw: str) -> bool:
        sink = self._drones.get(drone_id)
        if sink is None:
            return False
        await sink.send_text(raw)
        return True

    async def fan_to_operators(self, drone_id: str, raw: str) -> None:
        dead = []
        for sink in list(self.operators_for(drone_id)):
            try:
                await sink.send_text(raw)
            except Exception:
                dead.append(sink)
        for sink in dead:
            self.remove_operator(drone_id, sink)

    # --- fan-out ---
    async def broadcast_telemetry(self, drone_id: str, raw: str) -> None:
        await self.fan_to_operators(drone_id, raw)
