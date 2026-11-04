# drone/tests/test_e2e_sitl.py
import asyncio
import os

import pytest


def _sitl_enabled() -> bool:
    return os.getenv("RUN_SITL_E2E") == "1"


pytestmark = pytest.mark.skipif(
    not _sitl_enabled(), reason="set RUN_SITL_E2E=1 with ArduPilot SITL + relay + agent running"
)


async def test_telemetry_flows_sitl_to_ops():
    """With SITL + relay + agent running, an ops client receives valid telemetry."""
    import websockets
    from drone.common.telemetry import Envelope

    relay = os.getenv("RELAY_WS_URL", "ws://127.0.0.1:8800")
    ops_token = os.getenv("OPS_TOKEN", "otok")
    drone_id = os.getenv("DRONE_ID", "sitl-01")
    url = f"{relay}/ws/ops/{drone_id}?token={ops_token}"

    async with websockets.connect(url) as ops:
        raw = await asyncio.wait_for(ops.recv(), timeout=15)
        env = Envelope.model_validate_json(raw)
        assert env.type == "telemetry"
        assert env.telemetry is not None
        assert -90 <= env.telemetry.lat <= 90
        assert env.telemetry.mode  # non-empty
