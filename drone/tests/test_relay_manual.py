# drone/tests/test_relay_manual.py
import json
import pytest
from fastapi.testclient import TestClient
from drone.relay.server import create_app
from drone.tests.relay_sync import sync_drone


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DRONE_TOKENS", "sitl-01:dtok")
    monkeypatch.setenv("OPS_TOKEN", "otok")
    # one shared event loop for every WebSocket session (see relay_sync.py)
    with TestClient(create_app()) as c:
        yield c


def _telemetry(tier):
    return json.dumps({"type": "telemetry", "telemetry": {
        "drone_id": "sitl-01", "ts": 1, "seq": 0, "lat": 28.4, "lon": 77.1,
        "alt_rel_m": 40, "alt_amsl_m": 255, "heading_deg": 90, "groundspeed_ms": 0,
        "battery_pct": 80, "battery_voltage": 22.0, "mode": "GUIDED", "armed": True,
        "gps_fix": 3, "satellites": 14, "roll_deg": 0, "pitch_deg": 0, "yaw_deg": 90,
        "link_tier": tier}})


def _manual():
    return json.dumps({"type": "manual", "manual": {
        "operator_id": "op-a", "seq": 1, "vx": 1.0, "vy": 0, "vz": 0, "yaw_rate": 0}})


def test_manual_forwarded_on_green_with_lock(client):
    with client.websocket_connect("/ws/drone/sitl-01?token=dtok") as drone:
        drone.send_text(_telemetry("GREEN"))
        sync_drone(drone)  # tier applied before the manual frame is authorized
        with client.websocket_connect("/ws/ops/sitl-01?token=otok&operator=op-a") as ops:
            ops.send_text(json.dumps({"type": "control",
                "control": {"action": "acquire", "operator_id": "op-a"}}))
            ops.receive_text()  # grant
            ops.send_text(_manual())
            fwd = json.loads(drone.receive_text())
            assert fwd["type"] == "manual" and fwd["manual"]["vx"] == 1.0


def test_manual_dropped_on_amber(client):
    with client.websocket_connect("/ws/drone/sitl-01?token=dtok") as drone:
        drone.send_text(_telemetry("AMBER"))
        with client.websocket_connect("/ws/ops/sitl-01?token=otok&operator=op-a") as ops:
            ops.send_text(json.dumps({"type": "control",
                "control": {"action": "acquire", "operator_id": "op-a"}}))
            ops.receive_text()
            ops.send_text(_manual())
            # Probe: send a heartbeat after. If manual had been forwarded, the drone
            # would receive it first; instead the next frame is the heartbeat echo.
            drone.send_text(json.dumps({"type": "heartbeat", "ts": 9.0}))
            echoed = json.loads(drone.receive_text())
            assert echoed["type"] == "heartbeat"  # manual was dropped, not forwarded
