# drone/agent/commander.py
"""MAVLink command surface used by the command executor.

`MavCommander` is the contract; `PymavlinkCommander` is the real implementation
over an established mavutil connection. The executor depends on the protocol, so
it can be unit-tested with a fake and never needs a live autopilot.
"""
from __future__ import annotations

from typing import Protocol

from pymavlink import mavutil


class MavCommander(Protocol):
    def arm(self) -> None: ...
    def disarm(self) -> None: ...
    def set_mode(self, mode: str) -> None: ...
    def takeoff(self, alt_m: float) -> None: ...
    def rtl(self) -> None: ...
    def land(self) -> None: ...
    def goto(self, lat: float, lon: float, alt_m: float) -> None: ...
    def upload_mission(self, waypoints: list[dict]) -> None: ...
    def send_velocity(self, vx: float, vy: float, vz: float, yaw_rate: float) -> None: ...


class PymavlinkCommander:
    """Real implementation. `conn` is a connected mavutil.mavlink_connection."""

    def __init__(self, conn) -> None:
        self._c = conn

    def _arm_disarm(self, value: int) -> None:
        self._c.mav.command_long_send(
            self._c.target_system, self._c.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0,
            value, 0, 0, 0, 0, 0, 0)

    def arm(self) -> None:
        self._arm_disarm(1)

    def disarm(self) -> None:
        self._arm_disarm(0)

    def set_mode(self, mode: str) -> None:
        mode_id = self._c.mode_mapping()[mode]
        self._c.mav.set_mode_send(
            self._c.target_system,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, mode_id)

    def takeoff(self, alt_m: float) -> None:
        self.set_mode("GUIDED")
        self.arm()
        self._c.mav.command_long_send(
            self._c.target_system, self._c.target_component,
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0,
            0, 0, 0, 0, 0, 0, alt_m)

    def rtl(self) -> None:
        self.set_mode("RTL")

    def land(self) -> None:
        self.set_mode("LAND")

    def goto(self, lat: float, lon: float, alt_m: float) -> None:
        self.set_mode("GUIDED")
        self._c.mav.set_position_target_global_int_send(
            0, self._c.target_system, self._c.target_component,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
            0b0000111111111000,
            int(lat * 1e7), int(lon * 1e7), alt_m,
            0, 0, 0, 0, 0, 0, 0, 0)

    def send_velocity(self, vx: float, vy: float, vz: float, yaw_rate: float) -> None:
        # body-frame velocity in GUIDED; type_mask enables vx/vy/vz + yaw_rate only
        self._c.mav.set_position_target_local_ned_send(
            0, self._c.target_system, self._c.target_component,
            mavutil.mavlink.MAV_FRAME_BODY_NED,
            0b0000011111000111,  # use velocity + yaw_rate
            0, 0, 0,
            vx, vy, vz,
            0, 0, 0,
            0, yaw_rate)

    def upload_mission(self, waypoints: list[dict]) -> None:
        """waypoints: list of {seq, lat, lon, alt_m}. Standard MISSION_COUNT +
        MISSION_ITEM_INT upload handshake."""
        n = len(waypoints)
        self._c.mav.mission_count_send(
            self._c.target_system, self._c.target_component, n)
        for wp in waypoints:
            self._c.mav.mission_item_int_send(
                self._c.target_system, self._c.target_component,
                wp["seq"],
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                0, 1, 0, 0, 0, 0,
                int(wp["lat"] * 1e7), int(wp["lon"] * 1e7), wp["alt_m"])
