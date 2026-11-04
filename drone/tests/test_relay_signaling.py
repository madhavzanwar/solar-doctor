# drone/tests/test_relay_signaling.py
import json
import pytest
from fastapi.testclient import TestClient
from drone.relay.server import create_app
from drone.tests.relay_sync import sync_drone, sync_ops


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DRONE_TOKENS", "sitl-01:dtok")
    monkeypatch.setenv("OPS_TOKEN", "otok")
    # one shared event loop for every WebSocket session (see relay_sync.py)
    with TestClient(create_app()) as c:
        yield c


def test_offer_from_ops_reaches_drone(client):
    with client.websocket_connect("/ws/drone/sitl-01?token=dtok") as drone:
        sync_drone(drone)
        with client.websocket_connect("/ws/ops/sitl-01?token=otok&operator=op-a") as ops:
            ops.send_text(json.dumps({"type": "signal",
                "signal": {"kind": "offer", "operator_id": "op-a", "sdp": "v=0"}}))
            fwd = json.loads(drone.receive_text())
            assert fwd["type"] == "signal"
            assert fwd["signal"]["kind"] == "offer"
            assert fwd["signal"]["operator_id"] == "op-a"


def test_answer_from_drone_routes_to_target_operator(client):
    with client.websocket_connect("/ws/drone/sitl-01?token=dtok") as drone:
        with client.websocket_connect("/ws/ops/sitl-01?token=otok&operator=op-a") as ops_a:
            with client.websocket_connect("/ws/ops/sitl-01?token=otok&operator=op-b") as ops_b:
                sync_ops(ops_a, "op-a")
                sync_ops(ops_b, "op-b")
                drone.send_text(json.dumps({"type": "signal",
                    "signal": {"kind": "answer", "operator_id": "op-a", "sdp": "v=0"}}))
                reply = json.loads(ops_a.receive_text())
                assert reply["signal"]["kind"] == "answer"
                # op_a received it -> proves targeted routing by operator_id.
