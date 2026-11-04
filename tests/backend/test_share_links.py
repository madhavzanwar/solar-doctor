"""Read-only share links: ?share=<token> grants viewer access to one project."""
from datetime import datetime, timedelta

import pytest


@pytest.fixture
def operator(client, users_mode, make_user, login, two_projects):
    make_user("op@axalon.test", "operator", project_ids=[two_projects["p1"]])
    return login("op@axalon.test")


@pytest.fixture
def share_token(client, operator, two_projects):
    r = client.post(
        "/share-links",
        json={"project_id": two_projects["p1"], "label": "Client preview", "expires_in_days": 7},
        headers=operator,
    )
    assert r.status_code == 201, r.text
    return r.json()["token"]


def test_share_link_grants_project_scoped_read(client, share_token, two_projects):
    parks = client.get(f"/parks?share={share_token}").json()
    assert [p["id"] for p in parks["parks"]] == ["PARK_A"]
    assert client.get(f"/park/PARK_A?share={share_token}").status_code == 200
    assert client.get(f"/park/PARK_B?share={share_token}").status_code == 404
    assert client.get(f"/park/PARK_X?share={share_token}").status_code == 404
    assert client.get(f"/status/{two_projects['job_b']}?share={share_token}").status_code == 404
    me = client.get(f"/auth/me?share={share_token}").json()
    assert me["kind"] == "share"
    assert me["role"] == "viewer"
    assert me["project_ids"] == [two_projects["p1"]]


def test_share_link_is_read_only(client, share_token, two_projects):
    assert client.post(
        f"/missions?share={share_token}", json={"name": "m", "park_id": "PARK_A"},
    ).status_code == 403
    assert client.patch(
        f"/faults/{two_projects['fault_a']}?share={share_token}", json={"status": "resolved"},
    ).status_code == 403


def test_share_link_cannot_reach_internal_areas(client, share_token):
    for url in ("/inventory/components", "/track/notes", "/users", "/settings", "/share-links"):
        assert client.get(f"{url}?share={share_token}").status_code == 403, url


def test_invalid_share_token_is_401(client, users_mode, two_projects):
    assert client.get("/parks?share=not-a-real-token").status_code == 401


def test_expired_share_link_is_401(client, share_token, db_session):
    from axalon.db.models import ShareLink

    db_session.query(ShareLink).update({ShareLink.expires_at: datetime.utcnow() - timedelta(seconds=1)})
    db_session.commit()
    assert client.get(f"/parks?share={share_token}").status_code == 401


def test_revoked_share_link_is_401(client, operator, share_token):
    links = client.get("/share-links", headers=operator).json()
    assert len(links) == 1
    assert "token" not in links[0]
    assert client.delete(f"/share-links/{links[0]['id']}", headers=operator).status_code == 204
    assert client.get(f"/parks?share={share_token}").status_code == 401
    assert client.get("/share-links", headers=operator).json()[0]["revoked"] is True


def test_share_token_stored_hashed(client, share_token, db_session):
    from axalon.db.models import ShareLink

    row = db_session.query(ShareLink).one()
    assert share_token not in row.token_hash


def test_operator_cannot_share_foreign_project(client, operator, two_projects):
    r = client.post("/share-links", json={"project_id": two_projects["p2"]}, headers=operator)
    assert r.status_code == 404


def test_viewer_cannot_create_share_links(client, users_mode, make_user, login, two_projects):
    make_user("v@axalon.test", "viewer", project_ids=[two_projects["p1"]])
    r = client.post("/share-links", json={"project_id": two_projects["p1"]}, headers=login("v@axalon.test"))
    assert r.status_code == 403


def test_operator_cannot_list_or_revoke_foreign_links(client, users_mode, make_user, login, two_projects):
    make_user("admin@axalon.test", "admin")
    admin = login("admin@axalon.test")
    r = client.post("/share-links", json={"project_id": two_projects["p2"]}, headers=admin)
    link_id = r.json()["id"]
    make_user("op@axalon.test", "operator", project_ids=[two_projects["p1"]])
    op = login("op@axalon.test")
    assert client.get("/share-links", headers=op).json() == []
    assert client.delete(f"/share-links/{link_id}", headers=op).status_code == 404


@pytest.mark.parametrize("days", [0, -1, 366])
def test_share_link_expiry_bounds(client, operator, two_projects, days):
    r = client.post(
        "/share-links", json={"project_id": two_projects["p1"], "expires_in_days": days}, headers=operator,
    )
    assert r.status_code == 400


def test_deleting_project_removes_its_share_links(client, users_mode, make_user, login, two_projects):
    make_user("admin@axalon.test", "admin")
    admin = login("admin@axalon.test")
    token = client.post("/share-links", json={"project_id": two_projects["p2"]}, headers=admin).json()["token"]
    assert client.delete(f"/projects/{two_projects['p2']}", headers=admin).status_code == 204
    assert client.get(f"/parks?share={token}").status_code == 401
    assert client.get("/share-links", headers=admin).json() == []
