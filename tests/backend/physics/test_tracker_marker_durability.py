"""Marker durability: tolerant detection; plants API cannot strip or add the tracker marker."""
from datetime import datetime, timezone
from types import SimpleNamespace as NS

import pytest

from solardoctor.physics.tracker import TRACKER_MARKER, is_tracker_plant, with_marker

PLANT = dict(name="P", latitude=18.5, longitude=73.8, timezone="Asia/Kolkata",
             capacity_kw=120.0, inverter_capacity_kw=100.0)


@pytest.fixture(autouse=True)
def _iso(monkeypatch, tmp_path):
    monkeypatch.delenv("SOLARDOCTOR_WEATHER_API_KEY", raising=False)
    monkeypatch.setenv("SOLARDOCTOR_FORECAST_ARTIFACTS", str(tmp_path / "a"))
    from solardoctor.physics.registry import reset_registry
    reset_registry()
    yield
    reset_registry()


def _orm_tracker(db, name="T"):
    """Created like the PVDAQ importer does: directly through the ORM, not the plants API."""
    from solardoctor.physics.models import Plant
    p = Plant(name=name, lat=18.52, lon=73.86, dc_kw=120, ac_kw=100, location=f"Kersey, CO {TRACKER_MARKER}")
    db.add(p)
    db.commit()
    return p


@pytest.mark.parametrize("loc", [
    TRACKER_MARKER,
    TRACKER_MARKER.upper(),
    "Kersey [Single-Axis Tracker, Fixed-Tilt Baseline Invalid]",
    "Kersey [single  axis   tracker ,  fixed tilt  baseline invalid ]",
    "Kersey single axis tracker - fixed tilt baseline invalid",
    "Kersey (single_axis tracker; fixed-tilt baseline invalid)",
])
def test_detection_tolerates_variants(loc):
    assert is_tracker_plant(NS(location=loc))


@pytest.mark.parametrize("loc", ["Tracker Farm, single-axis tracker site", "Kersey", "", None,
                                 "fixed-tilt baseline"])
def test_detection_prose_is_not_flagged(loc):
    assert not is_tracker_plant(NS(location=loc))


def test_with_marker_canonical_and_bounded():
    assert with_marker("Kersey") == f"Kersey {TRACKER_MARKER}"
    assert with_marker(None) == TRACKER_MARKER
    assert with_marker(f"A {TRACKER_MARKER.upper()}") == f"A {TRACKER_MARKER}"
    assert len(with_marker("x" * 512)) <= 512 and with_marker("x" * 512).endswith(TRACKER_MARKER)


def test_put_cannot_strip_marker_and_forecast_still_422(client, db_session):
    t = _orm_tracker(db_session)
    r = client.put(f"/api/v1/plants/{t.id}", json={"location": "Kersey"})
    assert r.status_code == 200, r.text
    assert r.json()["location"] == f"Kersey {TRACKER_MARKER}"
    g = client.post(f"/api/v1/forecast/{t.id}/generate")
    assert g.status_code == 422 and g.json()["detail"]["status"] == "baseline_unsupported_for_trackers"
    for loc in ("", None, "Kersey [SINGLE AXIS TRACKER fixed tilt baseline invalid]"):
        assert client.put(f"/api/v1/plants/{t.id}", json={"location": loc}).status_code == 200
        assert client.post(f"/api/v1/forecast/{t.id}/generate").status_code == 422


def test_put_other_fields_leave_tracker_location_alone(client, db_session):
    t = _orm_tracker(db_session)
    r = client.put(f"/api/v1/plants/{t.id}", json={"name": "Renamed"})
    assert r.status_code == 200 and r.json()["location"] == f"Kersey, CO {TRACKER_MARKER}"


def test_post_and_put_cannot_add_marker_to_normal_plant(client):
    r = client.post("/api/v1/plants", json={**PLANT, "location": f"x {TRACKER_MARKER}"})
    assert r.status_code == 422 and "reserved" in r.json()["detail"]
    r = client.post("/api/v1/plants", json={**PLANT, "location": "x SINGLE-AXIS TRACKER fixed tilt baseline invalid"})
    assert r.status_code == 422
    p = client.post("/api/v1/plants", json={**PLANT, "location": "Pune"}).json()
    r = client.put(f"/api/v1/plants/{p['id']}", json={"location": f"Pune {TRACKER_MARKER}"})
    assert r.status_code == 422
    assert client.get(f"/api/v1/plants/{p['id']}").json()["location"] == "Pune"
    assert client.post(f"/api/v1/forecast/{p['id']}/generate").status_code == 200  # still a fixed plant
    assert client.put(f"/api/v1/plants/{p['id']}", json={"location": "Mumbai"}).status_code == 200


def test_importer_path_still_sets_marker():
    from solardoctor.seed.pvdaq import _location
    assert is_tracker_plant(NS(location=_location({"location": "Kersey, CO"}, {"tracking": "t"})))


def _alert(db, plant_id):
    from solardoctor.physics.models import PlantAlert
    a = PlantAlert(plant_id=plant_id, timestamp=datetime.now(tz=timezone.utc), alert_type="shortfall",
                   severity="CRITICAL", message="m", expected_power_kw=100.0, actual_power_kw=10.0,
                   deviation_percent=90.0, source="USER")
    db.add(a)
    db.commit()
    return a.id


def test_diagnosis_alert_refused_for_tracker(client, db_session):
    from solardoctor.physics.models import Diagnosis
    t = _orm_tracker(db_session)
    aid = _alert(db_session, t.id)
    r = client.get(f"/api/v1/diagnosis/alert/{aid}")
    assert r.status_code == 422 and r.json()["detail"]["status"] == "baseline_unsupported_for_trackers"
    assert db_session.query(Diagnosis).count() == 0


def test_diagnosis_alert_unchanged_for_fixed_plant(client, db_session):
    p = client.post("/api/v1/plants", json={**PLANT, "location": "Pune"}).json()
    aid = _alert(db_session, p["id"])
    assert client.get(f"/api/v1/diagnosis/alert/{aid}").status_code == 200
