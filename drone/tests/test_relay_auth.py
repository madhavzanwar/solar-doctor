# drone/tests/test_relay_auth.py
import pytest
from drone.relay.auth import verify_drone_token, verify_operator_token, AuthError


def test_valid_drone_token_returns_drone_id(monkeypatch):
    monkeypatch.setenv("DRONE_TOKENS", "sitl-01:secrettok,real-02:othertok")
    assert verify_drone_token("sitl-01", "secrettok") == "sitl-01"


def test_wrong_drone_token_raises(monkeypatch):
    monkeypatch.setenv("DRONE_TOKENS", "sitl-01:secrettok")
    with pytest.raises(AuthError):
        verify_drone_token("sitl-01", "nope")


def test_unknown_drone_id_raises(monkeypatch):
    monkeypatch.setenv("DRONE_TOKENS", "sitl-01:secrettok")
    with pytest.raises(AuthError):
        verify_drone_token("ghost", "secrettok")


def test_operator_token_matches_shared_secret(monkeypatch):
    monkeypatch.setenv("OPS_TOKEN", "opspass")
    assert verify_operator_token("opspass") is True


def test_operator_token_rejects_bad(monkeypatch):
    monkeypatch.setenv("OPS_TOKEN", "opspass")
    with pytest.raises(AuthError):
        verify_operator_token("bad")
