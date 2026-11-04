# drone/agent/safety.py
"""Agent-side safety primitives: link-tier classification + deadman timer.

`tier_from_rtt` maps a measured round-trip time to the safety tier the relay
enforces. `Deadman` tracks the last sign of life from the relay; when it expires
the agent triggers an ArduPilot failsafe (RTL) — see main.py.
"""
from __future__ import annotations

from drone.common.telemetry import LinkTier

GREEN_MAX_RTT_S = 0.05   # 50 ms
AMBER_MAX_RTT_S = 0.30   # 300 ms


def tier_from_rtt(rtt_s: float | None) -> LinkTier:
    if rtt_s is None:
        return LinkTier.RED
    if rtt_s <= GREEN_MAX_RTT_S:
        return LinkTier.GREEN
    if rtt_s <= AMBER_MAX_RTT_S:
        return LinkTier.AMBER
    return LinkTier.RED


class Deadman:
    def __init__(self, timeout_s: float) -> None:
        self.timeout_s = timeout_s
        self._last: float | None = None

    def beat(self, now: float) -> None:
        self._last = now

    def expired(self, now: float) -> bool:
        if self._last is None:
            return True
        return (now - self._last) > self.timeout_s
