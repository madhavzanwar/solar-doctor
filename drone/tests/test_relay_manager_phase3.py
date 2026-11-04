# drone/tests/test_relay_manager_phase3.py
import asyncio
import pytest
from drone.relay.manager import RelayManager


class FakeSink:
    def __init__(self):
        self.sent = []

    async def send_text(self, data: str):
        self.sent.append(data)


async def test_send_to_operator_targets_one():
    mgr = RelayManager()
    a, b = FakeSink(), FakeSink()
    mgr.register_operator("d1", "op-a", a)
    mgr.register_operator("d1", "op-b", b)
    ok = await mgr.send_to_operator("d1", "op-a", "frame")
    assert ok is True
    assert a.sent == ["frame"]
    assert b.sent == []


async def test_send_to_unknown_operator_returns_false():
    mgr = RelayManager()
    assert await mgr.send_to_operator("d1", "ghost", "x") is False


async def test_unregister_operator_removes_target():
    mgr = RelayManager()
    s = FakeSink()
    mgr.register_operator("d1", "op-a", s)
    mgr.unregister_operator("d1", "op-a")
    assert await mgr.send_to_operator("d1", "op-a", "x") is False
