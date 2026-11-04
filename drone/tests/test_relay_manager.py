# drone/tests/test_relay_manager.py
import pytest
from drone.relay.manager import RelayManager


class FakeSink:
    def __init__(self):
        self.sent: list[str] = []
        self.closed = False

    async def send_text(self, data: str):
        if self.closed:
            raise RuntimeError("sink closed")
        self.sent.append(data)


async def test_telemetry_fans_out_to_all_ops_for_that_drone():
    mgr = RelayManager()
    ops_a, ops_b = FakeSink(), FakeSink()
    mgr.add_operator("sitl-01", ops_a)
    mgr.add_operator("sitl-01", ops_b)
    mgr.add_operator("other", FakeSink())  # must NOT receive

    await mgr.broadcast_telemetry("sitl-01", '{"hello":1}')

    assert ops_a.sent == ['{"hello":1}']
    assert ops_b.sent == ['{"hello":1}']


async def test_broadcast_to_drone_with_no_operators_is_noop():
    mgr = RelayManager()
    await mgr.broadcast_telemetry("ghost", "{}")  # must not raise


async def test_dead_operator_is_dropped_and_does_not_break_others():
    mgr = RelayManager()
    good, dead = FakeSink(), FakeSink()
    dead.closed = True
    mgr.add_operator("sitl-01", good)
    mgr.add_operator("sitl-01", dead)

    await mgr.broadcast_telemetry("sitl-01", "x")

    assert good.sent == ["x"]
    assert dead not in mgr.operators_for("sitl-01")


async def test_remove_operator():
    mgr = RelayManager()
    s = FakeSink()
    mgr.add_operator("sitl-01", s)
    mgr.remove_operator("sitl-01", s)
    assert s not in mgr.operators_for("sitl-01")
