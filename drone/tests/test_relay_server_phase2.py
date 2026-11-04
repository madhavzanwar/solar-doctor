# drone/tests/test_relay_server_phase2.py
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


def _telemetry_frame(tier="AMBER"):
    return json.dumps({
        "type": "telemetry",
        "telemetry": {
            "drone_id": "sitl-01", "ts": 1, "seq": 0,
            "lat": 28.4, "lon": 77.1, "alt_rel_m": 40, "alt_amsl_m": 255,
            "heading_deg": 90, "groundspeed_ms": 5, "battery_pct": 80,
            "battery_voltage": 22.0, "mode": "GUIDED", "armed": False,
            "gps_fix": 3, "satellites": 14, "roll_deg": 0, "pitch_deg": 0,
            "yaw_deg": 90, "link_tier": tier,
        },
    })


def test_empty_operator_id_is_rejected(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/ops/sitl-01?token=otok&operator="):
            pass


def test_lock_released_when_holder_disconnects(client):
    app = client.app
    lock = app.state.lock
    with client.websocket_connect("/ws/ops/sitl-01?token=otok&operator=op-a") as ops:
        ops.send_text(json.dumps({"type": "control",
                                  "control": {"action": "acquire", "operator_id": "op-a"}}))
        ops.receive_text()
        assert lock.holder("sitl-01") == "op-a"
    # after the context manager exits (disconnect), the lock is freed
    assert lock.holder("sitl-01") is None


def test_operator_acquires_control(client):
    with client.websocket_connect("/ws/ops/sitl-01?token=otok&operator=op-a") as ops:
        ops.send_text(json.dumps({"type": "control",
                                  "control": {"action": "acquire", "operator_id": "op-a"}}))
        reply = json.loads(ops.receive_text())
        assert reply["type"] == "control"
        assert reply["control"]["granted"] is True
        assert reply["control"]["holder"] == "op-a"


def test_command_forwarded_to_drone_when_lock_held_and_tier_ok(client):
    with client.websocket_connect("/ws/drone/sitl-01?token=dtok") as drone:
        # establish tier via a telemetry frame
        drone.send_text(_telemetry_frame("AMBER"))
        sync_drone(drone)  # tier applied before the command is authorized
        with client.websocket_connect("/ws/ops/sitl-01?token=otok&operator=op-a") as ops:
            ops.send_text(json.dumps({"type": "control",
                                      "control": {"action": "acquire", "operator_id": "op-a"}}))
            ops.receive_text()  # control grant
            ops.send_text(json.dumps({"type": "command",
                                      "command": {"cmd_id": "c1", "type": "ARM"}}))
            fwd = json.loads(drone.receive_text())
            assert fwd["type"] == "command"
            assert fwd["command"]["type"] == "ARM"


def test_command_rejected_without_lock(client):
    with client.websocket_connect("/ws/drone/sitl-01?token=dtok") as drone:
        drone.send_text(_telemetry_frame("AMBER"))
        with client.websocket_connect("/ws/ops/sitl-01?token=otok&operator=op-a") as ops:
            ops.send_text(json.dumps({"type": "command",
                                      "command": {"cmd_id": "c2", "type": "ARM"}}))
            reply = json.loads(ops.receive_text())
            assert reply["type"] == "ack"
            assert reply["ack"]["success"] is False
            assert "lock" in reply["ack"]["message"].lower()


def test_command_rejected_on_red_tier(client):
    with client.websocket_connect("/ws/drone/sitl-01?token=dtok") as drone:
        drone.send_text(_telemetry_frame("RED"))
        with client.websocket_connect("/ws/ops/sitl-01?token=otok&operator=op-a") as ops:
            ops.send_text(json.dumps({"type": "control",
                                      "control": {"action": "acquire", "operator_id": "op-a"}}))
            ops.receive_text()
            ops.send_text(json.dumps({"type": "command",
                                      "command": {"cmd_id": "c3", "type": "TAKEOFF",
                                                  "params": {"alt": 40}}}))
            reply = json.loads(ops.receive_text())
            assert reply["ack"]["success"] is False
            assert "tier" in reply["ack"]["message"].lower()


def test_ack_from_drone_fans_to_operator(client):
    with client.websocket_connect("/ws/drone/sitl-01?token=dtok") as drone:
        with client.websocket_connect("/ws/ops/sitl-01?token=otok&operator=op-a") as ops:
            sync_ops(ops, "op-a")
            drone.send_text(json.dumps({"type": "ack",
                                        "ack": {"cmd_id": "c1", "success": True, "message": "armed"}}))
            reply = json.loads(ops.receive_text())
            assert reply["type"] == "ack" and reply["ack"]["cmd_id"] == "c1"


def test_heartbeat_echoed_back_to_drone(client):
    with client.websocket_connect("/ws/drone/sitl-01?token=dtok") as drone:
        drone.send_text(json.dumps({"type": "heartbeat", "ts": 123.0}))
        reply = json.loads(drone.receive_text())
        assert reply["type"] == "heartbeat" and reply["ts"] == 123.0
