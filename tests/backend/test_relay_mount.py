"""The drone relay is served by the API app under /relay.

Hugging Face now requires a paid plan for new Docker Spaces, so the relay can't
get its own Space. It rides the existing API Space instead: same container, same
TLS, WebSockets at wss://<api>/relay/ws/... The relay authenticates drones and
operators with its own tokens, so the API's key/users auth must not gate it, and
the API's CORS middleware must be the only one adding CORS headers.
"""
import json

import pytest
from fastapi.testclient import TestClient

from drone.tests.relay_sync import sync_ops


@pytest.fixture
def relay_client(temp_db, monkeypatch):
    monkeypatch.setenv("DRONE_TOKENS", "drone-01:dtok")
    monkeypatch.setenv("OPS_TOKEN", "otok")
    from axalon.api.app import app

    # Context manager: one shared event loop for all WebSocket sessions (relay_sync.py).
    with TestClient(app) as c:
        yield c


def test_relay_health_is_served_under_relay_prefix(relay_client):
    r = relay_client.get("/relay/health")

    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_drone_telemetry_reaches_operator_through_mounted_relay(relay_client):
    with relay_client.websocket_connect("/relay/ws/ops/drone-01?token=otok&operator=op-a") as ops:
        sync_ops(ops, "op-a")
        with relay_client.websocket_connect("/relay/ws/drone/drone-01?token=dtok") as drone:
            drone.send_text(json.dumps({"type": "telemetry", "telemetry": None}))

            assert json.loads(ops.receive_text())["type"] == "telemetry"


def test_relay_rejects_bad_ops_token(relay_client):
    with pytest.raises(Exception):
        with relay_client.websocket_connect("/relay/ws/ops/drone-01?token=WRONG&operator=op-a"):
            pass


@pytest.mark.parametrize("mode_env", [{"AXALON_API_KEY": "k"}, {"AXALON_AUTH_MODE": "users"}])
def test_api_auth_does_not_gate_the_relay(relay_client, monkeypatch, mode_env):
    for key, value in mode_env.items():
        monkeypatch.setenv(key, value)

    assert relay_client.get("/relay/health").status_code == 200
    assert relay_client.get("/parks").status_code == 401


def test_relay_turn_credentials_has_a_single_cors_header(relay_client):
    r = relay_client.get(
        "/relay/turn-credentials?token=otok&name=op-a",
        headers={"Origin": "https://axalonsystems.com"},
    )

    assert r.status_code == 200
    assert r.headers.get_list("access-control-allow-origin") == ["https://axalonsystems.com"]
