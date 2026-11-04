# drone/tests/test_turn.py
import base64
import hashlib
import hmac
import time

import pytest
from drone.relay.turn import make_turn_credentials, ice_servers


def _urls_text(s):
    return s["urls"] if isinstance(s["urls"], str) else " ".join(s["urls"])


def test_credentials_have_expiring_username():
    user, pwd = make_turn_credentials(secret="s3cr3t", ttl_s=3600, name="op-a")
    expiry_str, _, name = user.partition(":")
    assert name == "op-a"
    assert int(expiry_str) > time.time()


def test_password_is_hmac_of_username():
    user, pwd = make_turn_credentials(secret="s3cr3t", ttl_s=3600, name="op-a")
    expected = base64.b64encode(
        hmac.new(b"s3cr3t", user.encode(), hashlib.sha1).digest()
    ).decode()
    assert pwd == expected


def test_ice_servers_includes_stun_and_turn(monkeypatch):
    monkeypatch.setenv("TURN_SECRET", "s3cr3t")
    monkeypatch.setenv("TURN_HOST", "turn.example.com")
    servers = ice_servers(name="op-a")
    urls = " ".join(_urls_text(s) for s in servers)
    assert "stun:" in urls
    assert "turn:" in urls
    turn = next(s for s in servers if "turn:" in _urls_text(s))
    assert "username" in turn and "credential" in turn


def test_ice_servers_stun_only_when_no_secret(monkeypatch):
    monkeypatch.delenv("TURN_SECRET", raising=False)
    monkeypatch.setenv("TURN_HOST", "turn.example.com")
    servers = ice_servers(name="op-a")
    assert all("turn:" not in _urls_text(s) for s in servers)


def test_turn_endpoint_requires_token(monkeypatch):
    from fastapi.testclient import TestClient
    from drone.relay.server import create_app
    monkeypatch.setenv("DRONE_TOKENS", "sitl-01:dtok")
    monkeypatch.setenv("OPS_TOKEN", "otok")
    monkeypatch.setenv("TURN_HOST", "turn.example.com")
    client = TestClient(create_app())

    assert client.get("/turn-credentials?token=WRONG").status_code == 403
    ok = client.get("/turn-credentials?token=otok&name=op-a")
    assert ok.status_code == 200
    assert "iceServers" in ok.json()
