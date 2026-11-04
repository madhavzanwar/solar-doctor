# drone/tests/test_relay_manager_phase2.py
import pytest
from drone.common.telemetry import LinkTier
from drone.relay.manager import RelayManager


class FakeSink:
    def __init__(self):
        self.sent: list[str] = []

    async def send_text(self, data: str):
        self.sent.append(data)


async def test_send_to_drone_delivers_to_registered_drone():
    mgr = RelayManager()
    drone = FakeSink()
    mgr.register_drone("d1", drone)
    ok = await mgr.send_to_drone("d1", "cmd-frame")
    assert ok is True
    assert drone.sent == ["cmd-frame"]


async def test_send_to_offline_drone_returns_false():
    mgr = RelayManager()
    assert await mgr.send_to_drone("ghost", "x") is False


def test_tier_defaults_to_red_until_set():
    mgr = RelayManager()
    assert mgr.tier_for("d1") is LinkTier.RED


def test_set_and_read_tier():
    mgr = RelayManager()
    mgr.set_tier("d1", LinkTier.AMBER)
    assert mgr.tier_for("d1") is LinkTier.AMBER


async def test_fan_to_operators_sends_to_all():
    mgr = RelayManager()
    a, b = FakeSink(), FakeSink()
    mgr.add_operator("d1", a)
    mgr.add_operator("d1", b)
    await mgr.fan_to_operators("d1", "ack-frame")
    assert a.sent == ["ack-frame"] and b.sent == ["ack-frame"]
