# drone/tests/test_ws_client.py
import pytest
from drone.agent.ws_client import RelayClient


class FakeConn:
    def __init__(self):
        self.sent: list[str] = []
        self.open = True

    async def send(self, data: str):
        if not self.open:
            raise ConnectionError("closed")
        self.sent.append(data)

    async def close(self):
        self.open = False


async def test_send_passes_text_to_connection():
    conn = FakeConn()

    async def connector():
        return conn

    client = RelayClient(connector)
    await client.connect()
    await client.send("frame-1")
    assert conn.sent == ["frame-1"]


async def test_send_triggers_reconnect_after_failure():
    conns = [FakeConn(), FakeConn()]
    conns[0].open = False  # first connection is already dead
    calls = {"n": 0}

    async def connector():
        c = conns[calls["n"]]
        calls["n"] += 1
        return c

    client = RelayClient(connector)
    await client.connect()
    await client.send("frame-1")  # first send fails -> reconnect -> retry
    assert conns[1].sent == ["frame-1"]
    assert calls["n"] == 2
