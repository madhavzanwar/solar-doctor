# drone/tests/test_relay_proxy_hosting.py
"""Relay behaviour needed behind a TLS-terminating proxy (Hugging Face Space,
Cloudflare tunnel, Fly): readiness probe, browser CORS, idle-connection
keepalive, and a usable ICE fallback when no coturn is reachable."""
import json

import pytest
from fastapi.testclient import TestClient

from drone.relay.server import create_app
from drone.relay.turn import PUBLIC_STUN_URL, ice_servers


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv("DRONE_TOKENS", "sitl-01:dtok")
    monkeypatch.setenv("OPS_TOKEN", "otok")
    monkeypatch.delenv("RELAY_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("RELAY_PING_INTERVAL_S", raising=False)
    monkeypatch.delenv("TURN_HOST", raising=False)
    monkeypatch.delenv("TURN_SECRET", raising=False)
    return monkeypatch


# --- readiness ---------------------------------------------------------------

def test_root_answers_for_proxy_readiness_probe(env):
    client = TestClient(create_app())
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_supports_head(env):
    client = TestClient(create_app())
    assert client.head("/health").status_code == 200


# --- CORS --------------------------------------------------------------------

def test_cors_allows_production_site_by_default(env):
    client = TestClient(create_app())
    r = client.get("/turn-credentials?token=otok&name=op-a",
                   headers={"Origin": "https://axalonsystems.com"})
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "https://axalonsystems.com"


def test_cors_preflight_for_production_site(env):
    client = TestClient(create_app())
    r = client.options("/turn-credentials", headers={
        "Origin": "https://www.axalonsystems.com",
        "Access-Control-Request-Method": "GET",
    })
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "https://www.axalonsystems.com"


def test_cors_rejects_unlisted_origin(env):
    client = TestClient(create_app())
    r = client.get("/turn-credentials?token=otok",
                   headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_cors_origins_configurable_via_env(env):
    env.setenv("RELAY_CORS_ORIGINS", "http://localhost:3000, https://preview.example.com")
    client = TestClient(create_app())
    r = client.get("/health", headers={"Origin": "https://preview.example.com"})
    assert r.headers["access-control-allow-origin"] == "https://preview.example.com"
    r = client.get("/health", headers={"Origin": "https://axalonsystems.com"})
    assert "access-control-allow-origin" not in r.headers


# --- application-level keepalive ---------------------------------------------

def test_idle_ops_socket_receives_application_ping(env):
    env.setenv("RELAY_PING_INTERVAL_S", "0.05")
    client = TestClient(create_app())
    with client.websocket_connect("/ws/ops/sitl-01?token=otok&operator=op-a") as ops:
        frame = json.loads(ops.receive_text())
        assert frame["type"] == "ping"
        assert isinstance(frame["ts"], float)


def test_ping_does_not_break_normal_traffic(env):
    env.setenv("RELAY_PING_INTERVAL_S", "0.05")
    client = TestClient(create_app())
    with client.websocket_connect("/ws/ops/sitl-01?token=otok&operator=op-a") as ops:
        ops.send_text(json.dumps({"type": "control",
                                  "control": {"action": "acquire", "operator_id": "op-a"}}))
        types = set()
        for _ in range(10):
            types.add(json.loads(ops.receive_text())["type"])
            if "control" in types and "ping" in types:
                break
        assert {"control", "ping"} <= types


def test_ping_interval_default_is_below_proxy_idle_timeout():
    from drone.relay.config import ping_interval_s
    assert 0 < ping_interval_s() < 60


def test_ping_interval_invalid_value_falls_back_to_default(env):
    from drone.relay.config import DEFAULT_PING_INTERVAL_S, ping_interval_s
    env.setenv("RELAY_PING_INTERVAL_S", "not-a-number")
    assert ping_interval_s() == DEFAULT_PING_INTERVAL_S


# --- ICE fallback when coturn is unavailable (HF cannot host TURN) ----------------

def test_ice_servers_fall_back_to_public_stun_without_turn_host(env):
    servers = ice_servers(name="op-a")
    assert servers == [{"urls": PUBLIC_STUN_URL}]


def test_turn_endpoint_never_returns_empty_ice_list(env):
    client = TestClient(create_app())
    body = client.get("/turn-credentials?token=otok&name=op-a").json()
    assert body["iceServers"], "empty iceServers leaves WebRTC with host candidates only"
