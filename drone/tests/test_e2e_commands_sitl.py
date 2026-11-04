# drone/tests/test_e2e_commands_sitl.py
import asyncio
import json
import os
import uuid

import pytest


def _enabled() -> bool:
    return os.getenv("RUN_SITL_E2E") == "1"


pytestmark = pytest.mark.skipif(
    not _enabled(), reason="set RUN_SITL_E2E=1 with SITL + relay + agent running"
)


async def test_arm_command_round_trips_with_ack():
    """Acquire control, send ARM, expect a success ack from the agent."""
    import websockets

    relay = os.getenv("RELAY_WS_URL", "ws://127.0.0.1:8800")
    ops_token = os.getenv("OPS_TOKEN", "otok")
    drone_id = os.getenv("DRONE_ID", "sitl-01")
    op = "e2e-op"
    url = f"{relay}/ws/ops/{drone_id}?token={ops_token}&operator={op}"

    async with websockets.connect(url) as ws:
        # wait until tier is known (a telemetry frame has set it on the relay)
        await asyncio.sleep(2)
        await ws.send(json.dumps({"type": "control",
                                  "control": {"action": "acquire", "operator_id": op}}))
        grant = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        assert grant["control"]["granted"] is True

        cmd_id = str(uuid.uuid4())
        await ws.send(json.dumps({"type": "command",
                                  "command": {"cmd_id": cmd_id, "type": "ARM"}}))

        # the ops socket receives a stream (telemetry + ack); find our ack
        deadline = asyncio.get_event_loop().time() + 15
        ack = None
        while asyncio.get_event_loop().time() < deadline:
            frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
            if frame.get("type") == "ack" and frame["ack"]["cmd_id"] == cmd_id:
                ack = frame["ack"]
                break
        assert ack is not None and ack["success"] is True
