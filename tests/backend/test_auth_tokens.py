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
    # duplicate signup is indistinguishable from a fresh one (no account enumeration)
    dup = client.post("/auth/register", json={"email": "dup@example.test", "password": PASSWORD})
    fresh = client.post("/auth/register", json={"email": "fresh@example.test", "password": PASSWORD})
    assert dup.status_code == fresh.status_code == 201
    assert set(dup.json()) == set(fresh.json())
    # ...and does not touch the existing account's password
    assert client.post("/auth/login", json={"email": "dup@example.test", "password": PASSWORD}).status_code == 200
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
    third = client.post(f"{prefix}/auth/refresh", json={"refresh_token": second["refresh_token"]})
    assert third.status_code == 200          # chain continues
    # single use: replaying the first token is refused...
    assert client.post(f"{prefix}/auth/refresh", json={"refresh_token": first["refresh_token"]}).status_code == 401
    # ...and is treated as theft: the whole family, including the newest token, is revoked.
    assert client.post(f"{prefix}/auth/refresh", json={"refresh_token": third.json()["refresh_token"]}).status_code == 401


def test_reuse_detection_spares_other_logins(client, users_mode, make_user):
    make_user("a@example.test", "viewer")
    one = _login(client, "a@example.test")
    two = _login(client, "a@example.test")      # separate login = separate family
    rotated = client.post("/auth/refresh", json={"refresh_token": one["refresh_token"]}).json()
    assert client.post("/auth/refresh", json={"refresh_token": one["refresh_token"]}).status_code == 401
    assert client.post("/auth/refresh", json={"refresh_token": rotated["refresh_token"]}).status_code == 401
    assert client.post("/auth/refresh", json={"refresh_token": two["refresh_token"]}).status_code == 200


def test_bearer_only_logout_kills_refresh_token(client, users_mode, make_user):
    make_user("a@example.test", "viewer")
    body = _login(client, "a@example.test")
    other = _login(client, "a@example.test")    # different family: unaffected
    h = {"Authorization": f"Bearer {body['access_token']}"}
    assert client.post("/api/v1/auth/logout", headers=h).status_code == 204
    assert client.get("/auth/me", headers=h).status_code == 401
    assert client.post("/auth/refresh", json={"refresh_token": body["refresh_token"]}).status_code == 401
    assert client.post("/auth/refresh", json={"refresh_token": other["refresh_token"]}).status_code == 200


def test_bearer_logout_after_rotation_kills_new_refresh_token(client, users_mode, make_user):
    make_user("a@example.test", "viewer")
    first = _login(client, "a@example.test")
    second = client.post("/auth/refresh", json={"refresh_token": first["refresh_token"]}).json()
    h = {"Authorization": f"Bearer {second['access_token']}"}
    assert client.post("/auth/logout", headers=h).status_code == 204
    assert client.post("/auth/refresh", json={"refresh_token": second["refresh_token"]}).status_code == 401


@pytest.mark.parametrize("password", ["aaaaaaaaaaaa", "1111111111", "weakuser", "WeakUser  "])
def test_trivially_weak_passwords_rejected(client, users_mode, password):
    r = client.post("/auth/register", json={"email": "weakuser@example.test", "password": password})
    assert r.status_code == 400, password


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
        client.post("/inventory/components", json={"name": "motor"}, headers=h),
        client.delete(f"/missions/{two_projects['mission_a']}", headers=h),
        client.get("/users", headers=h),
    ]
    assert [r.status_code for r in blocked] == [403] * 4
    # a fault not assigned to them does not exist for them (404, not 403)
    assert client.patch(f"/faults/{two_projects['fault_a']}", json={"status": "in_progress"}, headers=h).status_code == 404


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


# ── technician: assigned faults only (every fault route) ─────────────────────

@pytest.fixture
def tech_world(client, users_mode, make_user, login, db_session, two_projects):
    """Technician T with one assigned fault; same park holds a colleague's and an unassigned fault."""
    from solardoctor.db.models import PanelFault
    mine = db_session.get(PanelFault, two_projects["fault_a"])
    mine.assignee, mine.status = "T@Example.test", "assigned"
    other = PanelFault(park_id=mine.park_id, panel_id="R9-C9", class_="cell", severity="HIGH",
                       assignee="someone@else.test", status="assigned")
    unassigned = PanelFault(park_id=mine.park_id, panel_id="R8-C8", class_="cell", severity="LOW", status="open")
    db_session.add_all([other, unassigned])
    db_session.commit()
    make_user("t@example.test", "technician", project_ids=[two_projects["p1"]])
    return {"h": login("t@example.test"), "mine": mine.id, "other": other.id, "unassigned": unassigned.id}


@pytest.mark.parametrize("prefix", PREFIXES)
def test_technician_fault_list_only_own(client, tech_world, prefix):
    r = client.get(f"{prefix}/parks/PARK_A/faults", headers=tech_world["h"])
    assert r.status_code == 200
    body = r.json()
    assert [f["id"] for f in body["faults"]] == [tech_world["mine"]]
    assert body["total"] == 1 and sum(body["counts_by_status"].values()) == 1
    assert "someone@else.test" not in r.text


def test_technician_other_faults_are_404_on_every_read(client, tech_world):
    h = tech_world["h"]
    for fid in (tech_world["other"], tech_world["unassigned"], 999999):
        assert client.get(f"/faults/{fid}/comments", headers=h).status_code == 404
        assert client.get(f"/faults/{fid}/photos", headers=h).status_code == 404
        assert client.get(f"/faults/{fid}/photos/1", headers=h).status_code == 404
    mine = tech_world["mine"]
    assert client.get(f"/faults/{mine}/comments", headers=h).status_code == 200
    assert client.get(f"/faults/{mine}/photos", headers=h).status_code == 200


def test_technician_can_work_own_fault(client, tech_world):
    h, fid = tech_world["h"], tech_world["mine"]
    r = client.patch(f"/faults/{fid}", json={"status": "in_progress", "notes": "on site"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "in_progress"
    c = client.post(f"/api/v1/faults/{fid}/comments", json={"body": "replaced string fuse", "author": "spoof"}, headers=h)
    assert c.status_code == 201 and c.json()["author"] == "t@example.test"
    png = b"\x89PNG\r\n\x1a\n" + b"\0" * 32
    # upload is permitted by policy and ownership; image validation is the faults router's business
    p = client.post(f"/faults/{fid}/photos", files={"file": ("p.png", png, "image/png")}, headers=h)
    assert p.status_code not in (403, 404), p.text
    r = client.patch(f"/faults/{fid}", json={"status": "resolved", "resolution_note": "fixed"}, headers=h)
    assert r.status_code == 200 and r.json()["status"] == "resolved"


def test_technician_cannot_touch_others_faults(client, tech_world):
    h = tech_world["h"]
    png = b"\x89PNG\r\n\x1a\n" + b"\0" * 32
    for fid in (tech_world["other"], tech_world["unassigned"]):
        assert client.patch(f"/faults/{fid}", json={"status": "in_progress"}, headers=h).status_code == 404
        assert client.post(f"/faults/{fid}/comments", json={"body": "x"}, headers=h).status_code == 404
        assert client.post(f"/faults/{fid}/photos", files={"file": ("p.png", png, "image/png")}, headers=h).status_code == 404


def test_technician_forbidden_changes_on_own_fault(client, tech_world):
    h, fid = tech_world["h"], tech_world["mine"]
    for body in ({"assignee": "t2@example.test"}, {"assignee": None}, {"priority": "low"},
                 {"due_date": "2030-01-01"}, {"status": "open"}, {"status": "assigned"},
                 {"status": "in_progress", "priority": "low"}):
        assert client.patch(f"/faults/{fid}", json=body, headers=h).status_code == 403, body
    assert client.delete(f"/faults/{fid}/photos/1", headers=h).status_code == 403
    assert client.post("/missions", json={"name": "m", "park_id": "PARK_A"}, headers=h).status_code == 403
    assert client.get("/users", headers=h).status_code == 403


def test_technician_works_only_in_own_projects(client, users_mode, make_user, login, db_session, two_projects):
    """Assigned by email but the fault lives in a project the technician is not a member of."""
    from solardoctor.db.models import PanelFault
    f = db_session.get(PanelFault, two_projects["fault_b"])
    f.assignee, f.status = "t@example.test", "assigned"
    db_session.commit()
    make_user("t@example.test", "technician", project_ids=[two_projects["p1"]])
    h = login("t@example.test")
    assert client.patch(f"/faults/{f.id}", json={"status": "in_progress"}, headers=h).status_code == 404
    assert client.get(f"/faults/{f.id}/comments", headers=h).status_code == 404


def test_operator_and_viewer_unchanged_on_faults(client, users_mode, make_user, login, two_projects):
    make_user("op@example.test", "operator", project_ids=[two_projects["p1"]])
    make_user("v@example.test", "viewer", project_ids=[two_projects["p1"]])
    op, v = login("op@example.test"), login("v@example.test")
    fid = two_projects["fault_a"]
    assert client.patch(f"/faults/{fid}", json={"assignee": "x@y.test", "status": "assigned"}, headers=op).status_code == 200
    assert client.patch(f"/faults/{fid}", json={"status": "resolved"}, headers=v).status_code == 403
    assert client.post(f"/faults/{fid}/comments", json={"body": "x"}, headers=v).status_code == 403
