# drone/agent/mavlink_source.py
"""Translate the ArduPilot MAVLink message stream into our Telemetry schema.

`TelemetryAccumulator` is intentionally pure: feed it decoded mavlink messages
via `update()`, then call `build()` to snapshot the current state. The real
mavlink connection lives in main.py, which keeps this unit testable with
synthetic SimpleNamespace messages.
"""
from __future__ import annotations

import math

from drone.common.telemetry import Telemetry

# ArduCopter flight-mode numbers (custom_mode) -> name.
_COPTER_MODES = {
    0: "STABILIZE", 2: "ALT_HOLD", 3: "AUTO", 4: "GUIDED",
    5: "LOITER", 6: "RTL", 9: "LAND", 16: "POSHOLD",
}
_MAV_MODE_FLAG_SAFETY_ARMED = 128


class TelemetryAccumulator:
    def __init__(self, drone_id: str) -> None:
        self.drone_id = drone_id
        self._pos: dict | None = None
        self._att = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}
        self._battery_pct = 0.0
        self._battery_v = 0.0
        self._gps_fix = 0
        self._sats = 0
        self._mode = "UNKNOWN"
        self._armed = False

    def update(self, m) -> None:
        t = m.get_type()
        if t == "GLOBAL_POSITION_INT":
            self._pos = {
                "lat": m.lat / 1e7,
                "lon": m.lon / 1e7,
                "alt_rel_m": m.relative_alt / 1000.0,
                "alt_amsl_m": m.alt / 1000.0,
                "heading_deg": (m.hdg / 100.0) % 360.0,
                "groundspeed_ms": math.hypot(m.vx, m.vy) / 100.0,
            }
        elif t == "ATTITUDE":
            self._att = {"roll": m.roll, "pitch": m.pitch, "yaw": m.yaw}
        elif t == "SYS_STATUS":
            self._battery_pct = max(0.0, float(m.battery_remaining))
            self._battery_v = m.voltage_battery / 1000.0
        elif t == "GPS_RAW_INT":
            self._gps_fix = m.fix_type
            self._sats = m.satellites_visible
        elif t == "HEARTBEAT":
            self._mode = _COPTER_MODES.get(m.custom_mode, f"MODE_{m.custom_mode}")
            self._armed = bool(m.base_mode & _MAV_MODE_FLAG_SAFETY_ARMED)

    def build(self, ts: float, seq: int) -> Telemetry | None:
        if self._pos is None:
            return None  # no fix yet — nothing meaningful to send
        return Telemetry(
            drone_id=self.drone_id,
            ts=ts,
            seq=seq,
            lat=self._pos["lat"],
            lon=self._pos["lon"],
            alt_rel_m=self._pos["alt_rel_m"],
            alt_amsl_m=self._pos["alt_amsl_m"],
            heading_deg=self._pos["heading_deg"],
            groundspeed_ms=self._pos["groundspeed_ms"],
            battery_pct=min(100.0, self._battery_pct),
            battery_voltage=self._battery_v,
            mode=self._mode,
            armed=self._armed,
            gps_fix=self._gps_fix,
            satellites=self._sats,
            roll_deg=math.degrees(self._att["roll"]),
            pitch_deg=math.degrees(self._att["pitch"]),
            yaw_deg=math.degrees(self._att["yaw"]) % 360.0,
        )
