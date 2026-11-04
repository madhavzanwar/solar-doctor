"""Users mode: login/logout/me, sessions, rate limiting, bootstrap, user admin, role matrix."""
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

PASSWORD = "correct-horse-battery"


# ── login / me / logout ───────────────────────────────────────────────────────

def test_login_me_logout_roundtrip(client, users_mode, make_user):
    make_user("Op@Axalon.test", "operator")
    r = client.post("/auth/login", json={"email": "  op@axalon.TEST ", "password": PASSWORD})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["email"] == "op@axalon.test"
    assert body["user"]["role"] == "operator"
    assert body["expires_at"]
    headers = {"Authorization": f"Bearer {body['token']}"}

    me = client.get("/auth/me", headers=headers)
    assert me.status_code == 200
    assert me.json()["kind"] == "user"
    assert me.json()["user"]["email"] == "op@axalon.test"

    assert client.post("/auth/logout", headers=headers).status_code == 204
    assert client.get("/auth/me", headers=headers).status_code == 401


def test_session_token_is_stored_hashed(client, users_mode, make_user, db_session):
    from axalon.db.models import UserSession

    make_user("a@axalon.test", "viewer")
    token = client.post("/auth/login", json={"email": "a@axalon.test", "password": PASSWORD}).json()["token"]
    stored = [s.token_hash for s in db_session.query(UserSession).all()]
    assert len(stored) == 1
    assert token not in stored[0]
    assert len(stored[0]) == 64


def test_wrong_password_and_unknown_email_look_identical(client, users_mode, make_user):
    make_user("a@axalon.test", "viewer")
    wrong = client.post("/auth/login", json={"email": "a@axalon.test", "password": "nope-nope-nope"})
    unknown = client.post("/auth/login", json={"email": "ghost@axalon.test", "password": PASSWORD})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json()


def test_login_rejects_missing_fields(client, users_mode):
    assert client.post("/auth/login", json={}).status_code == 401


def test_disabled_user_cannot_login_and_loses_sessions(client, users_mode, make_user, login):
    make_user("admin@axalon.test", "admin")
    uid = make_user("v@axalon.test", "viewer")
    admin = login("admin@axalon.test")
    viewer = login("v@axalon.test")

    r = client.patch(f"/users/{uid}", json={"disabled": True}, headers=admin)
    assert r.status_code == 200, r.text
    assert client.get("/parks", headers=viewer).status_code == 401
    r = client.post("/auth/login", json={"email": "v@axalon.test", "password": PASSWORD})
    assert r.status_code == 401


def test_expired_session_is_rejected(client, users_mode, make_user, login, db_session):
    from axalon.db.models import UserSession

    make_user("a@axalon.test", "viewer")
    headers = login("a@axalon.test")
    db_session.query(UserSession).update({UserSession.expires_at: datetime.utcnow() - timedelta(seconds=1)})
    db_session.commit()
    assert client.get("/parks", headers=headers).status_code == 401


# ── rate limiting ─────────────────────────────────────────────────────────────

def test_login_rate_limited_per_email(client, users_mode, make_user):
    from axalon.core.auth import LOGIN_MAX_FAILURES_PER_EMAIL

    make_user("a@axalon.test", "viewer")
    for _ in range(LOGIN_MAX_FAILURES_PER_EMAIL):
        r = client.post("/auth/login", json={"email": "a@axalon.test", "password": "wrong-password"})
        assert r.status_code == 401
    # Even the right password is refused while locked out.
    r = client.post("/auth/login", json={"email": "a@axalon.test", "password": PASSWORD})
    assert r.status_code == 429
    assert int(r.headers["Retry-After"]) > 0
    # A different account from the same client is unaffected by the per-email lock.
    make_user("b@axalon.test", "viewer")
    assert client.post("/auth/login", json={"email": "b@axalon.test", "password": PASSWORD}).status_code == 200


def test_login_rate_limited_per_client_ip(client, users_mode):
    from axalon.core.auth import LOGIN_MAX_FAILURES_PER_IP

    for i in range(LOGIN_MAX_FAILURES_PER_IP):
        client.post("/auth/login", json={"email": f"spray{i}@axalon.test", "password": "x" * 10})
    r = client.post("/auth/login", json={"email": "fresh@axalon.test", "password": "x" * 10})
    assert r.status_code == 429


def test_rate_limiter_window_expires():
    from axalon.core.auth import LoginRateLimiter

    now = [1000.0]
    limiter = LoginRateLimiter(max_failures=2, window_s=60, clock=lambda: now[0])
    limiter.record_failure("k")
    limiter.record_failure("k")
    assert limiter.retry_after("k") > 0
    now[0] += 61
    assert limiter.retry_after("k") == 0


# ── bootstrap admin ───────────────────────────────────────────────────────────

def _lifespan_client():
    from axalon.api.app import app
    return TestClient(app)


def test_bootstrap_admin_created_on_startup(temp_db, users_mode, monkeypatch):
    monkeypatch.setenv("AXALON_BOOTSTRAP_ADMIN_EMAIL", "Root@Axalon.test")
    monkeypatch.setenv("AXALON_BOOTSTRAP_ADMIN_PASSWORD", PASSWORD)
    with _lifespan_client() as c:
        r = c.post("/auth/login", json={"email": "root@axalon.test", "password": PASSWORD})
        assert r.status_code == 200, r.text
        assert r.json()["user"]["role"] == "admin"


def test_bootstrap_is_noop_when_users_exist(temp_db, users_mode, monkeypatch, make_user, db_session):
    from axalon.db.models import User

    make_user("existing@axalon.test", "admin")
    monkeypatch.setenv("AXALON_BOOTSTRAP_ADMIN_EMAIL", "root@axalon.test")
    monkeypatch.setenv("AXALON_BOOTSTRAP_ADMIN_PASSWORD", PASSWORD)
    with _lifespan_client():
        pass
    assert [u.email for u in db_session.query(User).all()] == ["existing@axalon.test"]


def test_bootstrap_skipped_outside_users_mode(temp_db, monkeypatch, db_session):
    from axalon.db.models import User

    monkeypatch.setenv("AXALON_BOOTSTRAP_ADMIN_EMAIL", "root@axalon.test")
    monkeypatch.setenv("AXALON_BOOTSTRAP_ADMIN_PASSWORD", PASSWORD)
    with _lifespan_client():
        pass
    assert db_session.query(User).count() == 0


def test_bootstrap_rejects_weak_password(temp_db, users_mode, monkeypatch, db_session):
    from axalon.db.models import User

    monkeypatch.setenv("AXALON_BOOTSTRAP_ADMIN_EMAIL", "root@axalon.test")
    monkeypatch.setenv("AXALON_BOOTSTRAP_ADMIN_PASSWORD", "short")
    with _lifespan_client():
        pass
    assert db_session.query(User).count() == 0


# ── user administration ───────────────────────────────────────────────────────

def test_admin_user_crud(client, users_mode, make_user, login, two_projects):
    make_user("admin@axalon.test", "admin")
    admin = login("admin@axalon.test")

    r = client.post(
        "/users",
        json={"email": "New@Axalon.test", "password": PASSWORD, "role": "operator",
              "project_ids": [two_projects["p1"]]},
        headers=admin,
    )
    assert r.status_code == 201, r.text
    created = r.json()
    assert created["email"] == "new@axalon.test"
    assert created["project_ids"] == [two_projects["p1"]]

    assert client.post(
        "/users", json={"email": "new@axalon.test", "password": PASSWORD, "role": "viewer"}, headers=admin,
    ).status_code == 409

    r = client.patch(
        f"/users/{created['id']}",
        json={"role": "viewer", "project_ids": [two_projects["p1"], two_projects["p2"]]},
        headers=admin,
    )
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "viewer"
    assert sorted(r.json()["project_ids"]) == sorted([two_projects["p1"], two_projects["p2"]])

    listed = client.get("/users", headers=admin).json()
    assert {u["email"] for u in listed} == {"admin@axalon.test", "new@axalon.test"}

    assert client.delete(f"/users/{created['id']}", headers=admin).status_code == 204
    assert client.patch(f"/users/{created['id']}", json={"role": "admin"}, headers=admin).status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {"email": "not-an-email", "password": PASSWORD, "role": "viewer"},
        {"email": "a@axalon.test", "password": "short", "role": "viewer"},
        {"email": "a@axalon.test", "password": PASSWORD, "role": "superuser"},
        {"email": "a@axalon.test", "password": PASSWORD, "role": "viewer", "project_ids": [9999]},
    ],
)
def test_user_create_validation(client, users_mode, make_user, login, payload):
    make_user("admin@axalon.test", "admin")
    r = client.post("/users", json=payload, headers=login("admin@axalon.test"))
    assert r.status_code == 400, r.text


def test_cannot_remove_last_active_admin(client, users_mode, make_user, login, db_session):
    from axalon.db.models import User

    make_user("admin@axalon.test", "admin")
    admin = login("admin@axalon.test")
    uid = db_session.query(User).filter_by(email="admin@axalon.test").one().id
    assert client.patch(f"/users/{uid}", json={"role": "operator"}, headers=admin).status_code == 400
    assert client.patch(f"/users/{uid}", json={"disabled": True}, headers=admin).status_code == 400
    assert client.delete(f"/users/{uid}", headers=admin).status_code == 400


def test_password_change_revokes_sessions(client, users_mode, make_user, login):
    make_user("admin@axalon.test", "admin")
    uid = make_user("v@axalon.test", "viewer")
    admin = login("admin@axalon.test")
    viewer = login("v@axalon.test")
    new_pw = "another-long-password"
    assert client.patch(f"/users/{uid}", json={"password": new_pw}, headers=admin).status_code == 200
    assert client.get("/parks", headers=viewer).status_code == 401
    assert client.post("/auth/login", json={"email": "v@axalon.test", "password": new_pw}).status_code == 200


def test_password_is_never_returned(client, users_mode, make_user, login, db_session):
    from axalon.db.models import User

    make_user("admin@axalon.test", "admin")
    r_login = client.post("/auth/login", json={"email": "admin@axalon.test", "password": PASSWORD})
    admin = {"Authorization": f"Bearer {r_login.json()['token']}"}
    r_create = client.post(
        "/users", json={"email": "v@axalon.test", "password": PASSWORD, "role": "viewer"}, headers=admin,
    )
    uid = r_create.json()["id"]
    responses = [
        r_login,
        r_create,
        client.get("/auth/me", headers=admin),
        client.get("/users", headers=admin),
        client.patch(f"/users/{uid}", json={"password": "rotated-password-1"}, headers=admin),
    ]
    hashes = [u.password_hash for u in db_session.query(User).all()]
    for r in responses:
        assert r.status_code < 300, r.text
        text = r.text
        assert "password" not in text.lower()
        assert PASSWORD not in text
        assert "rotated-password-1" not in text
        for h in hashes:
            assert h not in text


def test_user_password_hash_uses_kdf(users_mode, make_user, db_session):
    from axalon.db.models import User

    make_user("a@axalon.test", "viewer")
    stored = db_session.query(User).one().password_hash
    assert stored.startswith("pbkdf2_sha256$")
    assert PASSWORD not in stored


# ── role matrix ───────────────────────────────────────────────────────────────

def _headers_for(role, make_user, login, project_ids):
    email = f"{role}@axalon.test"
    make_user(email, role, project_ids=project_ids)
    return login(email)


def test_viewer_is_read_only(client, users_mode, make_user, login, two_projects):
    h = _headers_for("viewer", make_user, login, [two_projects["p1"]])
    assert client.get("/parks", headers=h).status_code == 200
    assert client.get("/inventory/components", headers=h).status_code == 200
    blocked = [
        client.post("/missions", json={"name": "m", "park_id": "PARK_A"}, headers=h),
        client.patch(f"/faults/{two_projects['fault_a']}", json={"status": "resolved"}, headers=h),
        client.post(f"/faults/{two_projects['fault_a']}/comments", json={"body": "x"}, headers=h),
        client.delete(f"/missions/{two_projects['mission_a']}", headers=h),
        client.post("/inventory/components", json={"name": "motor"}, headers=h),
        client.put("/settings", json={"settings": {}}, headers=h),
        client.get("/users", headers=h),
    ]
    assert [r.status_code for r in blocked] == [403] * len(blocked)


def test_operator_can_mutate_but_not_admin_users(client, users_mode, make_user, login, two_projects):
    h = _headers_for("operator", make_user, login, [two_projects["p1"]])
    assert client.post("/missions", json={"name": "m", "park_id": "PARK_A"}, headers=h).status_code == 201
    assert client.patch(
        f"/faults/{two_projects['fault_a']}", json={"status": "resolved"}, headers=h,
    ).status_code == 200
    assert client.post("/inventory/components", json={"name": "motor"}, headers=h).status_code == 201
    assert client.get("/users", headers=h).status_code == 403
    assert client.post(
        "/users", json={"email": "x@axalon.test", "password": PASSWORD, "role": "admin"}, headers=h,
    ).status_code == 403
    assert client.post("/projects", json={"name": "Mine"}, headers=h).status_code == 403
    assert client.get("/agents/sessions", headers=h).status_code == 403


def test_admin_has_full_access(client, users_mode, make_user, login, two_projects):
    h = _headers_for("admin", make_user, login, [])
    assert client.get("/users", headers=h).status_code == 200
    assert client.post("/projects", json={"name": "Admin project"}, headers=h).status_code == 201
    assert client.get("/park/PARK_X", headers=h).status_code == 200
