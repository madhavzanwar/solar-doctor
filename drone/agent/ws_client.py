# drone/agent/ws_client.py
"""Outbound WebSocket client from the agent to the relay.

Takes an async `connector()` that returns a connection object with
`async send(str)` / `async close()`. In production this opens a real
`websockets` connection; tests inject a fake. On send failure it reconnects once
and retries, so a relay restart or a brief LTE drop doesn't kill the agent.
"""
from __future__ import annotations

from typing import Awaitable, Callable, Protocol


class Connection(Protocol):
    async def send(self, data: str) -> None: ...
    async def close(self) -> None: ...


class RelayClient:
    def __init__(self, connector: Callable[[], Awaitable[Connection]]) -> None:
        self._connector = connector
        self._conn: Connection | None = None

    async def connect(self) -> None:
        self._conn = await self._connector()

    async def send(self, data: str) -> None:
        if self._conn is None:
            await self.connect()
        try:
            await self._conn.send(data)
        except Exception:
            # reconnect once and retry; let a second failure propagate
            await self.connect()
            await self._conn.send(data)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
