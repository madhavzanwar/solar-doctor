"""Tests for Area C asset management: Projects → Sites (parks) → Missions/Inspections."""
from axalon.db.models import Inspection, Mission, Park


def _make_project(client, **overrides) -> dict:
    payload = {"name": "Rajasthan 40MW", "client": "SunCo", "status": "active"}
    payload.update(overrides)
    resp = client.post("/projects", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_project_crud(client):
    proj = _make_project(client)
    assert proj["name"] == "Rajasthan 40MW"
    assert proj["status"] == "active"

    listed = client.get("/projects").json()
    assert len(listed) == 1

    resp = client.patch(f"/projects/{proj['id']}", json={"status": "archived", "client": "SunCo Ltd"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "archived"

    assert client.delete(f"/projects/{proj['id']}").status_code == 204
    assert client.get("/projects").json() == []


def test_project_requires_name(client):
    assert client.post("/projects", json={"name": ""}).status_code == 400


def test_project_rejects_bad_status(client):
    assert client.post("/projects", json={"name": "X", "status": "paused-ish"}).status_code == 400


def test_assign_park_to_project(client, db_session):
    db_session.add(Park(id="PARK_X", name="Site X"))
    db_session.commit()
    proj = _make_project(client)

    resp = client.patch("/park/PARK_X", json={"project_id": proj["id"]})
    assert resp.status_code == 200
    assert resp.json()["project_id"] == proj["id"]

    # unassign
    resp = client.patch("/park/PARK_X", json={"project_id": None})
    assert resp.status_code == 200
    assert resp.json()["project_id"] is None


def test_assign_park_404s(client, db_session):
    db_session.add(Park(id="PARK_Y", name="Site Y"))
    db_session.commit()
    assert client.patch("/park/NOPE", json={"project_id": None}).status_code == 404
    assert client.patch("/park/PARK_Y", json={"project_id": 999}).status_code == 404


def test_project_detail_embeds_sites_with_counts(client, db_session):
    proj = _make_project(client)
    db_session.add(Park(id="PARK_Z", name="Site Z", project_id=proj["id"], total_panels=400))
    db_session.flush()
    db_session.add(Inspection(id="INSP-Z-1", park_id="PARK_Z", flight_date="2026-06-02"))
    db_session.add(Mission(name="Grid Z", park_id="PARK_Z", mission_type="grid"))
    db_session.commit()

    detail = client.get(f"/projects/{proj['id']}").json()
    assert detail["name"] == "Rajasthan 40MW"
    assert len(detail["sites"]) == 1
    site = detail["sites"][0]
    assert site["id"] == "PARK_Z"
    assert site["inspection_count"] == 1
    assert site["mission_count"] == 1
    assert site["last_inspection_date"] == "2026-06-02"


def test_delete_project_unassigns_parks(client, db_session):
    proj = _make_project(client)
    db_session.add(Park(id="PARK_W", name="Site W", project_id=proj["id"]))
    db_session.commit()

    assert client.delete(f"/projects/{proj['id']}").status_code == 204
    db_session.expire_all()
    park = db_session.query(Park).filter_by(id="PARK_W").one()
    assert park.project_id is None
