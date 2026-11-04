from axalon.db.models import Mission, Park


def test_mission_model_persists(db_session):
    park = Park(id="PARK_PLAN", name="Plan Park")
    db_session.add(park)
    db_session.flush()
    m = Mission(
        name="Grid #1",
        park_id="PARK_PLAN",
        mission_type="grid",
        camera_id="itl612r-pro",
        params='{"altitudeM": 20}',
        polygon='[{"lat": 18.5, "lon": 73.8}]',
        waypoints='[{"lat": 18.5, "lon": 73.8, "alt": 20}]',
        area_ha=4.2,
        image_count=312,
    )
    db_session.add(m)
    db_session.commit()
    fetched = db_session.query(Mission).filter_by(name="Grid #1").first()
    assert fetched.mission_type == "grid"
    assert fetched.camera_id == "itl612r-pro"
    assert fetched.area_ha == 4.2


def test_create_mission(client):
    payload = {
        "name": "API Grid #1",
        "park_id": "PARK_PLAN_API",
        "mission_type": "grid",
        "camera_id": "itl612r-pro",
        "params": {"altitudeM": 20, "frontOverlap": 0.8},
        "polygon": [{"lat": 18.52, "lon": 73.855}],
        "waypoints": [{"lat": 18.52, "lon": 73.855, "alt": 20}],
        "area_ha": 4.2,
        "image_count": 312,
    }
    resp = client.post("/missions", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "API Grid #1"
    assert "id" in data


def test_list_missions_filtered_by_park(client):
    for name in ["M1", "M2"]:
        client.post("/missions", json={
            "name": name, "park_id": "PARK_LIST", "mission_type": "grid",
            "camera_id": "itl612r-pro", "params": {}, "polygon": [], "waypoints": [],
            "area_ha": 1.0, "image_count": 10,
        })
    client.post("/missions", json={
        "name": "Other", "park_id": "PARK_OTHER", "mission_type": "grid",
        "camera_id": "itl612r-pro", "params": {}, "polygon": [], "waypoints": [],
        "area_ha": 1.0, "image_count": 10,
    })
    resp = client.get("/missions?park_id=PARK_LIST")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    assert {m["name"] for m in items} == {"M1", "M2"}
    # list response should NOT carry the heavy waypoints payload
    assert "waypoints" not in items[0]


def test_get_mission_returns_full_payload(client):
    created = client.post("/missions", json={
        "name": "Full", "park_id": "PARK_FULL", "mission_type": "perimeter",
        "camera_id": "dji-xt2", "params": {"altitudeM": 15},
        "polygon": [{"lat": 1, "lon": 2}], "waypoints": [{"lat": 1, "lon": 2, "alt": 15}],
        "area_ha": 2.0, "image_count": 50,
    }).json()
    resp = client.get(f"/missions/{created['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mission_type"] == "perimeter"
    assert data["params"] == {"altitudeM": 15}
    assert data["waypoints"] == [{"lat": 1, "lon": 2, "alt": 15}]


def test_get_mission_404(client):
    assert client.get("/missions/999999").status_code == 404


def test_delete_mission(client):
    created = client.post("/missions", json={
        "name": "ToDelete", "park_id": "PARK_DEL", "mission_type": "grid",
        "camera_id": "itl612r-pro", "params": {}, "polygon": [], "waypoints": [],
        "area_ha": 1.0, "image_count": 1,
    }).json()
    assert client.delete(f"/missions/{created['id']}").status_code == 204
    assert client.get(f"/missions/{created['id']}").status_code == 404


def test_create_mission_requires_name(client):
    resp = client.post("/missions", json={"mission_type": "grid"})
    assert resp.status_code == 400
