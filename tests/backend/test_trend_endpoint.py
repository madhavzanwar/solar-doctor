import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path):
    from axalon.db.models import Detection, Inspection, Park
    from axalon.db.session import get_engine, init_db, session_scope
    from axalon.api.app import app

    init_db(f"sqlite:///{tmp_path / 'trend_endpoint.db'}")
    with session_scope(get_engine()) as s:
        s.add(Park(id="TREND_PARK", name="Trend Park", mode="auto", rows=1, cols=2, total_panels=2))
    with session_scope(get_engine()) as s:
        s.add(Inspection(id="i1", park_id="TREND_PARK", flight_date="2026-05-01", total_images=1, total_detections=2, summary=json.dumps({})))
        s.add(Inspection(id="i2", park_id="TREND_PARK", flight_date="2026-05-15", total_images=1, total_detections=2, summary=json.dumps({})))
    with session_scope(get_engine()) as s:
        s.add(Detection(inspection_id="i1", panel_id="R1-C1", class_="cell", severity="CRITICAL"))
        s.add(Detection(inspection_id="i1", panel_id="R1-C2", class_="soiling", severity="LOW"))
        s.add(Detection(inspection_id="i2", panel_id="R1-C1", class_="cell", severity="HIGH"))
        s.add(Detection(inspection_id="i2", panel_id="R1-C2", class_="soiling", severity="LOW"))

    with TestClient(app) as c:
        yield c


def test_park_trend_endpoint(client):
    r = client.get("/park/TREND_PARK/trend")
    assert r.status_code == 200
    body = r.json()
    assert [p["inspection_id"] for p in body] == ["i1", "i2"]
    assert body[0]["CRITICAL"] == 1
    assert body[1]["HIGH"] == 1


def test_park_recurring_endpoint(client):
    r = client.get("/park/TREND_PARK/recurring")
    assert r.status_code == 200
    body = r.json()
    panel_ids = {p["panel_id"] for p in body}
    assert {"R1-C1", "R1-C2"}.issubset(panel_ids)


def test_park_trend_unknown_park_404(client):
    assert client.get("/park/NOPE/trend").status_code == 404
