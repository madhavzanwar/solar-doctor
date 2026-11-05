"""Auth surface for the SolarPulse-shaped frontend: register, form token login,
refresh rotation + expiry, logout, role matrix incl. technician, prefixed paths."""
from datetime import datetime, timedelta

import pytest

PASSWORD = "correct-horse-battery"
PREFIXES = ["", "/api/v1"]


@pytest.fixture(autouse=True)
def _reset_register_limiter():
    from solardoctor.core import auth as _auth
    _auth.register_limiter.reset()
    yield
    _auth.register_limiter.reset()


def _login(client, email, prefix=""):
    r = client.post(f"{prefix}/auth/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.parametrize("prefix", PREFIXES)
def test_register_then_token_login_then_me(client, users_mode, prefix):
    r = client.post(f"{prefix}/auth/register", json={
        "username": "newbie", "email": "New@Example.test", "password": PASSWORD, "full_name": "N",
    })
    assert r.status_code == 201, r.text
    assert r.json()["email"] == "new@example.test"
    assert r.json()["role"] == "viewer"          # never self-assigned higher
    assert "password" not in r.text and "hash" not in r.text

    f = client.post(f"{prefix}/auth/token", data={"username": "new@example.test", "password": PASSWORD})
    assert f.status_code == 200, f.text
    body = f.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"] == body["token"]
    assert body["refresh_token"] and body["expires_in"] > 0

    me = client.get(f"{prefix}/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200 and me.json()["user"]["email"] == "new@example.test"


def test_register_validation_duplicate_and_toggle(client, users_mode, make_user, monkeypatch):
    make_user("dup@example.test", "viewer")
    assert client.post("/auth/register", json={"email": "dup@example.test", "password": PASSWORD}).status_code == 409
    assert client.post("/auth/register", json={"email": "bad", "password": PASSWORD}).status_code == 400
    assert client.post("/auth/register", json={"email": "x@example.test", "password": "short"}).status_code == 400
    # a role in the payload is ignored
    r = client.post("/auth/register", json={"email": "r@example.test", "password": PASSWORD, "role": "admin"})
    assert r.status_code == 201 and r.json()["role"] == "viewer"
    monkeypatch.setenv("SOLARDOCTOR_ALLOW_REGISTRATION", "0")
    assert client.post("/auth/register", json={"email": "z@example.test", "password": PASSWORD}).status_code == 403


def test_register_rate_limited(client, users_mode):
    from solardoctor.core.auth import REGISTER_MAX_PER_IP
    for i in range(REGISTER_MAX_PER_IP):
        assert client.post("/auth/register", json={"email": f"u{i}@example.test", "password": PASSWORD}).status_code == 201
    r = client.post("/auth/register", json={"email": "late@example.test", "password": PASSWORD})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0


@pytest.mark.parametrize("prefix", PREFIXES)
def test_refresh_rotates_and_old_token_is_dead(client, users_mode, make_user, prefix):
    make_user("a@example.test", "operator")
    first = _login(client, "a@example.test", prefix)
    r = client.post(f"{prefix}/auth/refresh", json={"refresh_token": first["refresh_token"]})
    assert r.status_code == 200, r.text
    second = r.json()
    assert second["refresh_token"] != first["refresh_token"]
    assert second["access_token"] != first["access_token"]
    assert client.get("/auth/me", headers={"Authorization": f"Bearer {second['access_token']}"}).status_code == 200
    # single use
    assert client.post(f"{prefix}/auth/refresh", json={"refresh_token": first["refresh_token"]}).status_code == 401
    # chain continues
    assert client.post(f"{prefix}/auth/refresh", json={"refresh_token": second["refresh_token"]}).status_code == 200


def test_refresh_rejects_garbage_and_token_type_confusion(client, users_mode, make_user):
    make_user("a@example.test", "viewer")
    body = _login(client, "a@example.test")
    assert client.post("/auth/refresh", json={"refresh_token": "nope"}).status_code == 401
    assert client.post("/auth/refresh", json={}).status_code == 401
    # an access token is not a refresh token, and vice versa
    assert client.post("/auth/refresh", json={"refresh_token": body["access_token"]}).status_code == 401
    r = client.get("/auth/me", headers={"Authorization": f"Bearer {body['refresh_token']}"})
    assert r.status_code == 401


def test_refresh_expiry_and_disabled_user(client, users_mode, make_user, db_session):
    from solardoctor.db.models import User, UserSession
    make_user("a@example.test", "viewer")
    body = _login(client, "a@example.test")
    for row in db_session.query(UserSession).all():
        row.expires_at = datetime.utcnow() - timedelta(seconds=1)
    db_session.commit()
    assert client.post("/auth/refresh", json={"refresh_token": body["refresh_token"]}).status_code == 401

    body = _login(client, "a@example.test")
    db_session.query(User).update({User.disabled: True})
    db_session.commit()
    assert client.post("/auth/refresh", json={"refresh_token": body["refresh_token"]}).status_code == 401


def test_logout_revokes_refresh_token_when_sent(client, users_mode, make_user):
    make_user("a@example.test", "viewer")
    body = _login(client, "a@example.test")
    h = {"Authorization": f"Bearer {body['access_token']}"}
    assert client.post("/auth/logout", json={"refresh_token": body["refresh_token"]}, headers=h).status_code == 204
    assert client.get("/auth/me", headers=h).status_code == 401
    assert client.post("/auth/refresh", json={"refresh_token": body["refresh_token"]}).status_code == 401


def test_logout_with_refresh_token_only_and_without_credentials(client, users_mode, make_user):
    make_user("a@example.test", "viewer")
    body = _login(client, "a@example.test")
    assert client.post("/api/v1/auth/logout", json={"refresh_token": body["refresh_token"]}).status_code == 204
    assert client.post("/auth/refresh", json={"refresh_token": body["refresh_token"]}).status_code == 401
    assert client.post("/auth/logout").status_code == 204


def test_bad_bearer_token_rejected_on_both_mounts(client, users_mode):
    h = {"Authorization": "Bearer not-a-real-token"}
    for prefix in PREFIXES:
        assert client.get(f"{prefix}/auth/me", headers=h).status_code == 401
        assert client.get(f"{prefix}/parks", headers=h).status_code == 401
        assert client.get(f"{prefix}/parks").status_code == 401


@pytest.mark.parametrize("prefix", PREFIXES)
def test_public_paths_open_without_credentials(client, users_mode, prefix):
    assert client.get(f"{prefix}/auth/mode").json() == {"mode": "users"}
    assert client.get(f"{prefix}/health").status_code == 200
    assert client.post(f"{prefix}/auth/login", json={}).status_code == 401  # reached the handler


def test_login_rate_limit_applies_to_form_endpoint(client, users_mode, make_user):
    from solardoctor.core.auth import LOGIN_MAX_FAILURES_PER_EMAIL
    make_user("a@example.test", "viewer")
    for _ in range(LOGIN_MAX_FAILURES_PER_EMAIL):
        assert client.post("/auth/token", data={"username": "a@example.test", "password": "wrong-wrong"}).status_code == 401
    assert client.post("/auth/token", data={"username": "a@example.test", "password": PASSWORD}).status_code == 429


@pytest.mark.parametrize("mode", ["off", "apikey"])
def test_register_refresh_unavailable_outside_users_mode(client, monkeypatch, mode):
    monkeypatch.setenv("SOLARDOCTOR_AUTH_MODE", mode)
    monkeypatch.setenv("SOLARDOCTOR_API_KEY", "k" * 20)
    h = {"Authorization": "Bearer " + "k" * 20}
    assert client.post("/auth/register", json={"email": "a@example.test", "password": PASSWORD}, headers=h).status_code == 404
    assert client.post("/auth/refresh", json={"refresh_token": "x"}, headers=h).status_code == 404
    assert client.get("/auth/mode").json() == {"mode": mode}


# ── roles ─────────────────────────────────────────────────────────────────────

def test_roles_include_technician(client, users_mode, make_user, login):
    make_user("admin@example.test", "admin")
    h = login("admin@example.test")
    r = client.post("/users", json={"email": "t@example.test", "password": PASSWORD, "role": "technician"}, headers=h)
    assert r.status_code == 201 and r.json()["role"] == "technician"
    assert client.post("/users", json={"email": "q@example.test", "password": PASSWORD, "role": "root"}, headers=h).status_code == 400


def test_technician_read_only_and_not_admin(client, users_mode, make_user, login, two_projects):
    make_user("t@example.test", "technician", project_ids=[two_projects["p1"]])
    h = login("t@example.test")
    assert client.get("/parks", headers=h).status_code == 200
    blocked = [
        client.post("/missions", json={"name": "m", "park_id": "PARK_A"}, headers=h),
        client.patch(f"/faults/{two_projects['fault_a']}", json={"status": "resolved"}, headers=h),
        client.get("/users", headers=h),
    ]
    assert [r.status_code for r in blocked] == [403] * 3


def test_technician_sees_only_assigned_work_orders(client, users_mode, make_user, login, db_session, two_projects):
    from solardoctor.db.models import PanelFault
    mine = db_session.query(PanelFault).get(two_projects["fault_a"])
    mine.assignee, mine.status = "T@Example.test", "assigned"
    other = PanelFault(park_id=mine.park_id, panel_id="R9-C9", class_="cell", severity="HIGH",
                       assignee="someone@else.test", status="assigned")
    unassigned = PanelFault(park_id=mine.park_id, panel_id="R8-C8", class_="cell", severity="LOW", status="open")
    db_session.add_all([other, unassigned])
    db_session.commit()
    make_user("t@example.test", "technician", project_ids=[two_projects["p1"]])
    make_user("op@example.test", "operator", project_ids=[two_projects["p1"]])

    def panels(h, qs=""):
        r = client.get(f"/parks/PARK_A/work-orders?format=csv{qs}", headers=h)
        assert r.status_code == 200, r.text
        return sorted(line.split(",")[1] for line in r.text.strip().splitlines()[1:])

    t = login("t@example.test")
    assert panels(t) == ["R1-C1"]
    # cannot widen via the assignee filter
    assert panels(t, "&assignee=someone@else.test") == ["R1-C1"]
    # an operator sees all actionable ones
    assert len(panels(login("op@example.test"))) == 3
    # and a technician cannot reach a park outside their project
    assert client.get("/parks/PARK_B/work-orders?format=csv", headers=t).status_code in (403, 404)


def test_role_rank_and_operator_cannot_manage_users(client, users_mode, make_user, login):
    from solardoctor.api.support.principal import KIND_USER, Principal
    assert Principal(kind=KIND_USER, role="technician").has_role("viewer")
    assert not Principal(kind=KIND_USER, role="technician").has_role("operator")
    assert Principal(kind=KIND_USER, role="operator").has_role("technician")
    make_user("op@example.test", "operator")
    assert client.get("/users", headers=login("op@example.test")).status_code == 403
