# drone/tests/test_relay_server.py
import json
import pytest
from fastapi.testclient import TestClient
from drone.relay.server import create_app
from drone.tests.relay_sync import sync_ops


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DRONE_TOKENS", "sitl-01:dtok")
    monkeypatch.setenv("OPS_TOKEN", "otok")
    # one shared event loop for every WebSocket session (see relay_sync.py)
    with TestClient(create_app()) as c:
        yield c


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_drone_frame_reaches_operator(client):
    # operator subscribes first
    with client.websocket_connect("/ws/ops/sitl-01?token=otok&operator=op-a") as ops:
        sync_ops(ops, "op-a")
        with client.websocket_connect("/ws/drone/sitl-01?token=dtok") as drone:
            frame = {"type": "telemetry", "telemetry": None}
            drone.send_text(json.dumps(frame))
            received = ops.receive_text()
            assert json.loads(received)["type"] == "telemetry"


def test_drone_rejected_with_bad_token(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/drone/sitl-01?token=WRONG"):
            pass


def test_ops_rejected_with_bad_token(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/ops/sitl-01?token=WRONG"):
            pass
