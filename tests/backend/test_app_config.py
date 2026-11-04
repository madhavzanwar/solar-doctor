"""Tests for DB-backed /track password (Supabase app_config)."""
import pytest

from axalon.core.app_config import (
    hash_password,
    verify_hash,
    set_track_password,
    verify_track_password,
    OK,
    WRONG,
    UNCONFIGURED,
)


def test_hash_roundtrip():
    encoded = hash_password("axalon1234")
    assert encoded.startswith("pbkdf2_sha256$")
    assert verify_hash("axalon1234", encoded) is True
    assert verify_hash("nope", encoded) is False


def test_hash_is_salted():
    assert hash_password("x") != hash_password("x")


def test_verify_unconfigured(db_session, monkeypatch):
    monkeypatch.delenv("AXALON_TRACK_PASSWORD", raising=False)
    assert verify_track_password(db_session, "anything") == UNCONFIGURED


def test_verify_against_db(db_session, monkeypatch):
    monkeypatch.delenv("AXALON_TRACK_PASSWORD", raising=False)
    set_track_password(db_session, "axalon1234")
    assert verify_track_password(db_session, "axalon1234") == OK
    assert verify_track_password(db_session, "wrong") == WRONG


def test_env_override_wins(db_session, monkeypatch):
    set_track_password(db_session, "db-password")
    monkeypatch.setenv("AXALON_TRACK_PASSWORD", "env-password")
    assert verify_track_password(db_session, "env-password") == OK
    assert verify_track_password(db_session, "db-password") == WRONG


# ── endpoints ─────────────────────────────────────────────────────────────────

def test_login_unconfigured_503(client, monkeypatch):
    monkeypatch.delenv("AXALON_TRACK_PASSWORD", raising=False)
    assert client.post("/track/login", json={"password": "x"}).status_code == 503


def test_set_password_then_login(client, monkeypatch):
    monkeypatch.delenv("AXALON_TRACK_PASSWORD", raising=False)
    # first-time setup: no current password required
    r = client.post("/track/password", json={"new_password": "axalon1234"})
    assert r.status_code == 200

    assert client.post("/track/login", json={"password": "axalon1234"}).status_code == 200
    assert client.post("/track/login", json={"password": "nope"}).status_code == 401


def test_set_password_rejects_short(client, monkeypatch):
    monkeypatch.delenv("AXALON_TRACK_PASSWORD", raising=False)
    assert client.post("/track/password", json={"new_password": "abc"}).status_code == 400


def test_rotate_password_requires_current(client, monkeypatch):
    monkeypatch.delenv("AXALON_TRACK_PASSWORD", raising=False)
    client.post("/track/password", json={"new_password": "axalon1234"})
    # wrong current password is rejected
    assert client.post(
        "/track/password", json={"current_password": "nope", "new_password": "newsecret"}
    ).status_code == 401
    # correct current password rotates
    assert client.post(
        "/track/password", json={"current_password": "axalon1234", "new_password": "newsecret"}
    ).status_code == 200
    assert client.post("/track/login", json={"password": "newsecret"}).status_code == 200
