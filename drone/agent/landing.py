# drone/agent/landing.py
"""Detect a landing as an armed->disarmed edge, firing the handoff exactly once
per flight. Pure state machine driven by the `armed` telemetry field.
"""
from __future__ import annotations


class LandingDetector:
    def __init__(self) -> None:
        self._was_armed = False
        self._flew = False

    def update(self, armed: bool) -> bool:
        landed = False
        if armed:
            self._was_armed = True
            self._flew = True
        elif self._was_armed and self._flew:
            landed = True
            self._flew = False  # consume; require a new arm to fire again
        self._was_armed = armed
        return landed
