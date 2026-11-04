# drone/relay/control_lock.py
"""Single-operator control lock, keyed by drone_id.

Exactly one operator may hold a given drone's lock at a time. Acquiring is
idempotent for the current holder. Only flight commands from the lock holder are
forwarded by the relay; everyone else is view-only.
"""
from __future__ import annotations


class ControlLock:
    def __init__(self) -> None:
        self._holder: dict[str, str] = {}

    def acquire(self, drone_id: str, operator_id: str) -> bool:
        current = self._holder.get(drone_id)
        if current is None or current == operator_id:
            self._holder[drone_id] = operator_id
            return True
        return False

    def release(self, drone_id: str, operator_id: str) -> bool:
        if self._holder.get(drone_id) == operator_id:
            del self._holder[drone_id]
            return True
        return False

    def holder(self, drone_id: str) -> str | None:
        return self._holder.get(drone_id)

    def holds(self, drone_id: str, operator_id: str) -> bool:
        return self._holder.get(drone_id) == operator_id
