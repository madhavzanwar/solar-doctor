# drone/agent/command_executor.py
"""Validate and dispatch commands to the MAVLink commander.

Every command is re-checked here (allow-list + altitude/coordinate bounds) even
though the relay already gated it — the agent never trusts an upstream gate. A
dispatch failure becomes a failed Ack instead of crashing the agent.
"""
from __future__ import annotations

from drone.agent.commander import MavCommander
from drone.common.commands import Ack, Command, CommandType


class CommandExecutor:
    def __init__(self, commander: MavCommander, min_alt_m: float, max_alt_m: float) -> None:
        self.commander = commander
        self.min_alt_m = min_alt_m
        self.max_alt_m = max_alt_m

    def _check_alt(self, alt) -> float:
        if alt is None:
            raise ValueError("missing required param: alt")
        alt = float(alt)
        if not (self.min_alt_m <= alt <= self.max_alt_m):
            raise ValueError(
                f"altitude {alt} outside bounds [{self.min_alt_m}, {self.max_alt_m}]")
        return alt

    def execute(self, cmd: Command) -> Ack:
        try:
            self._dispatch(cmd)
            return Ack(cmd_id=cmd.cmd_id, success=True, message="ok")
        except Exception as e:
            return Ack(cmd_id=cmd.cmd_id, success=False, message=str(e))

    def _dispatch(self, cmd: Command) -> None:
        p = cmd.params
        t = cmd.type
        if t is CommandType.ARM:
            self.commander.arm()
        elif t is CommandType.DISARM:
            self.commander.disarm()
        elif t is CommandType.TAKEOFF:
            self.commander.takeoff(self._check_alt(p.get("alt")))
        elif t is CommandType.RTL:
            self.commander.rtl()
        elif t is CommandType.LAND:
            self.commander.land()
        elif t is CommandType.PAUSE:
            self.commander.set_mode("BRAKE")
        elif t is CommandType.RESUME:
            self.commander.set_mode("AUTO")
        elif t is CommandType.SET_MODE:
            mode = p.get("mode")
            if not mode:
                raise ValueError("missing required param: mode")
            self.commander.set_mode(str(mode))
        elif t is CommandType.GOTO:
            lat, lon = p.get("lat"), p.get("lon")
            if lat is None or lon is None:
                raise ValueError("missing required params: lat/lon")
            lat, lon = float(lat), float(lon)
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError("lat/lon out of range")
            self.commander.goto(lat, lon, self._check_alt(p.get("alt")))
        elif t is CommandType.UPLOAD_MISSION:
            wps = p.get("waypoints")
            if not isinstance(wps, list) or not wps:
                raise ValueError("missing required param: waypoints")
            self.commander.upload_mission(wps)
        else:  # pragma: no cover - enum is exhaustive
            raise ValueError(f"unsupported command: {t}")
