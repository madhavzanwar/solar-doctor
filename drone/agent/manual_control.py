# drone/agent/manual_control.py
"""Apply manual velocity input to the autopilot, with stale-frame rejection.

`ManualController.apply` forwards a ManualInput to the commander, ignoring
out-of-order frames (seq must advance). `ManualDeadman` is a separate, faster
deadman than the relay-link one: if manual frames stop arriving, the agent calls
`hover()` so the drone holds instead of coasting on the last velocity.
"""
from __future__ import annotations

from drone.agent.commander import MavCommander
from drone.common.manual import ManualInput


class ManualController:
    def __init__(self, commander: MavCommander) -> None:
        self.commander = commander
        self._last_seq = -1

    def apply(self, m: ManualInput) -> None:
        if m.seq <= self._last_seq:
            return  # stale / out-of-order
        self._last_seq = m.seq
        self.commander.send_velocity(m.vx, m.vy, m.vz, m.yaw_rate)

    def hover(self) -> None:
        self.commander.send_velocity(0.0, 0.0, 0.0, 0.0)


class ManualDeadman:
    def __init__(self, timeout_s: float) -> None:
        self.timeout_s = timeout_s
        self._last: float | None = None

    def beat(self, now: float) -> None:
        self._last = now

    def expired(self, now: float) -> bool:
        if self._last is None:
            return False  # not in manual mode yet
        return (now - self._last) > self.timeout_s
