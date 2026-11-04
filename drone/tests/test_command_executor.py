# drone/tests/test_command_executor.py
import pytest
from drone.common.commands import Command, CommandType
from drone.agent.command_executor import CommandExecutor


class FakeCommander:
    def __init__(self):
        self.calls = []

    def arm(self): self.calls.append(("arm",))
    def disarm(self): self.calls.append(("disarm",))
    def set_mode(self, mode): self.calls.append(("set_mode", mode))
    def takeoff(self, alt_m): self.calls.append(("takeoff", alt_m))
    def rtl(self): self.calls.append(("rtl",))
    def land(self): self.calls.append(("land",))
    def goto(self, lat, lon, alt_m): self.calls.append(("goto", lat, lon, alt_m))
    def upload_mission(self, wps): self.calls.append(("upload_mission", len(wps)))


def _exec():
    return CommandExecutor(FakeCommander(), min_alt_m=5.0, max_alt_m=120.0)


def test_arm_dispatches_and_acks_success():
    ex = _exec()
    ack = ex.execute(Command(cmd_id="1", type=CommandType.ARM))
    assert ack.success is True
    assert ("arm",) in ex.commander.calls


def test_takeoff_validates_altitude_bounds():
    ex = _exec()
    ack = ex.execute(Command(cmd_id="2", type=CommandType.TAKEOFF, params={"alt": 500}))
    assert ack.success is False
    assert "altitude" in ack.message.lower()
    assert ex.commander.calls == []  # never dispatched


def test_takeoff_within_bounds_dispatches():
    ex = _exec()
    ack = ex.execute(Command(cmd_id="3", type=CommandType.TAKEOFF, params={"alt": 40}))
    assert ack.success is True
    assert ("takeoff", 40.0) in ex.commander.calls


def test_pause_and_resume_map_to_modes():
    ex = _exec()
    ex.execute(Command(cmd_id="4", type=CommandType.PAUSE))
    ex.execute(Command(cmd_id="5", type=CommandType.RESUME))
    assert ("set_mode", "BRAKE") in ex.commander.calls
    assert ("set_mode", "AUTO") in ex.commander.calls


def test_goto_validates_lat_lon_and_alt():
    ex = _exec()
    bad = ex.execute(Command(cmd_id="6", type=CommandType.GOTO,
                             params={"lat": 200, "lon": 0, "alt": 40}))
    assert bad.success is False
    good = ex.execute(Command(cmd_id="7", type=CommandType.GOTO,
                              params={"lat": 28.4, "lon": 77.1, "alt": 40}))
    assert good.success is True
    assert ("goto", 28.4, 77.1, 40.0) in ex.commander.calls


def test_missing_required_param_is_a_clean_nack():
    ex = _exec()
    ack = ex.execute(Command(cmd_id="8", type=CommandType.TAKEOFF, params={}))
    assert ack.success is False
    assert ex.commander.calls == []


def test_commander_exception_becomes_failed_ack():
    class Boom(FakeCommander):
        def rtl(self): raise RuntimeError("link lost")
    ex = CommandExecutor(Boom(), min_alt_m=5.0, max_alt_m=120.0)
    ack = ex.execute(Command(cmd_id="9", type=CommandType.RTL))
    assert ack.success is False
    assert "link lost" in ack.message
