"""AXALON_AUTH_MODE middleware behaviour: off | apikey | users (+ legacy fallback)."""
import pytest


# ── mode resolution ───────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("flag", "api_key", "expected"),
    [
        (None, None, "off"),          # today's production: keyless
        (None, "k", "apikey"),        # today's shared-key deployments
        ("off", "k", "off"),
        ("apikey", "k", "apikey"),
        ("users", None, "users"),
        ("USERS ", None, "users"),
        ("bogus", None, "users"),     # typo must fail closed, never open
    ],
)
def test_auth_mode_resolution(monkeypatch, flag, api_key, expected):
    from axalon.core.auth import auth_mode

    monkeypatch.delenv("AXALON_AUTH_MODE", raising=False)
    monkeypatch.delenv("AXALON_API_KEY", raising=False)
    if flag is not None:
        monkeypatch.setenv("AXALON_AUTH_MODE", flag)
    if api_key is not None:
        monkeypatch.setenv("AXALON_API_KEY", api_key)
    assert auth_mode() == expected


def test_auth_mode_endpoint_is_public_and_reports_mode(client, monkeypatch):
    assert client.get("/auth/mode").json() == {"mode": "off"}
    monkeypatch.setenv("AXALON_API_KEY", "secret123")
    r = client.get("/auth/mode")
    assert r.status_code == 200
    assert r.json() == {"mode": "apikey"}
    monkeypatch.setenv("AXALON_AUTH_MODE", "users")
    assert client.get("/auth/mode").json() == {"mode": "users"}


# ── off ───────────────────────────────────────────────────────────────────────

def test_off_mode_is_keyless(client):
    assert client.get("/parks").status_code == 200
    assert client.post("/projects", json={"name": "Open"}).status_code == 201


def test_explicit_off_ignores_api_key(client, monkeypatch):
    monkeypatch.setenv("AXALON_AUTH_MODE", "off")
    monkeypatch.setenv("AXALON_API_KEY", "secret123")
    assert client.get("/parks").status_code == 200


# ── apikey ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("flag", [None, "apikey"])
def test_apikey_mode_requires_shared_key(client, monkeypatch, flag):
    monkeypatch.setenv("AXALON_API_KEY", "secret123")
    if flag:
        monkeypatch.setenv("AXALON_AUTH_MODE", flag)
    assert client.get("/parks").status_code == 401
    assert client.get("/parks", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/parks", headers={"Authorization": "Bearer secret123"}).status_code == 200
    assert client.get("/parks?api_key=secret123").status_code == 200
    assert client.get("/health").status_code == 200


def test_apikey_mode_rejects_user_endpoints_gracefully(client, monkeypatch):
    monkeypatch.setenv("AXALON_API_KEY", "secret123")
    # Login is a users-mode feature; in apikey mode it is just another protected route.
    assert client.post("/auth/login", json={"email": "a@b.co", "password": "x"}).status_code == 401


def test_explicit_apikey_without_key_fails_closed(client, monkeypatch):
    monkeypatch.setenv("AXALON_AUTH_MODE", "apikey")
    monkeypatch.delenv("AXALON_API_KEY", raising=False)
    assert client.get("/parks").status_code == 401


# ── users ─────────────────────────────────────────────────────────────────────

def test_users_mode_requires_session(client, users_mode):
    r = client.get("/parks")
    assert r.status_code == 401
    assert client.get("/parks", headers={"Authorization": "Bearer not-a-token"}).status_code == 401


def test_users_mode_public_paths(client, users_mode, monkeypatch):
    assert client.get("/health").status_code == 200
    assert client.get("/auth/mode").status_code == 200
    monkeypatch.setenv("AXALON_TRACK_PASSWORD", "track-pw")
    assert client.post("/track/login", json={"password": "track-pw"}).status_code == 200


def test_users_mode_does_not_accept_shared_api_key(client, monkeypatch, users_mode):
    monkeypatch.setenv("AXALON_API_KEY", "secret123")
    assert client.get("/parks", headers={"Authorization": "Bearer secret123"}).status_code == 401


def test_users_mode_session_token_accepted_as_query_param(client, users_mode, make_user, login):
    """<img>/download URLs cannot send headers; the console appends ?api_key=."""
    make_user("admin@axalon.test", "admin")
    token = login("admin@axalon.test")["Authorization"].split(" ", 1)[1]
    assert client.get(f"/parks?api_key={token}").status_code == 200


def test_unknown_flag_fails_closed(client, monkeypatch):
    monkeypatch.setenv("AXALON_AUTH_MODE", "user")  # typo
    assert client.get("/parks").status_code == 401
