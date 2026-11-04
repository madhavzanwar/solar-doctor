# drone/tests/relay_sync.py
"""Barriers for relay WebSocket tests.

Two separate races made multi-socket relay tests hang intermittently:

1. Unless the TestClient is entered as a context manager, Starlette runs every
   `websocket_connect` session on its own event-loop thread, and a frame the
   server sends from one session's loop into another's stream may never wake the
   receiver. Fixtures therefore use `with TestClient(app) as c: yield c`.
2. Returning from `websocket_connect` / `send_text` doesn't mean the server has
   registered the socket or applied the frame (e.g. the telemetry link tier).
   These helpers round-trip a frame through the server handler, which proves
   everything sent before it on that socket has been handled.
"""
from __future__ import annotations

import json


def sync_drone(drone) -> None:
    """Wait until the drone socket is registered and earlier frames are applied."""
    drone.send_text(json.dumps({"type": "heartbeat", "ts": 0.0}))
    while json.loads(drone.receive_text())["type"] != "heartbeat":
        pass


def sync_ops(ops, operator_id: str) -> None:
    """Wait until the operator socket is registered for fan-out and signaling."""
    ops.send_text(json.dumps({"type": "control",
                              "control": {"action": "status", "operator_id": operator_id}}))
    while json.loads(ops.receive_text())["type"] != "control":
        pass
