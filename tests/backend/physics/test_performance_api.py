"""/performance and /strings/{id}/peers on SIMULATED telemetry (network mocked: site GHI covers every row)."""
import pytest

from solardoctor.physics import irradiance
from solardoctor.physics import weather_service as ws
from solardoctor.physics.tracker import TRACKER_MARKER

from . import deficit_synth as ds

Q = "start=2026-03-18T00:00:00Z&end=2026-03-21T00:00:00Z"  # the 3 simulated days


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network used")
    monkeypatch.setattr(ws, "fetch_nasa_power_hourly", boom)
    monkeypatch.setattr(irradiance, "fetch_openmeteo_hourly", boom)


@pytest.fixture
def seeded(client, db_session):
    plant, invs, strs = ds.make_plant(db_session)
    ds.populate(db_session, plant, invs, strs, "string_10", 0)
    return plant, strs


def test_performance_shape(client, seeded):
    plant, strs = seeded
    r = client.get(f"/api/v1/performance/{plant.id}?{Q}")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["status"] == "ok" and b["baseline"] == "pvwatts" and b["data_source"] == "SIMULATED"
    pt = next(p for p in b["series"] if p["usable"])
    assert pt["source"] == "site_sensor" and 0.5 < pt["pi"] < 1.2 and pt["clear"]
    assert [e["scope"] for e in b["events"]] == ["string"] and b["events"][0]["severity"] in ("WARNING", "CRITICAL")
    assert b["open_alerts"] == [] and b["soiling"] is None and "plant" in b["qc"]


def test_scan_persists_then_performance_lists_open_alert_with_evidence(client, seeded):
    plant, _ = seeded
    r = client.post(f"/api/v1/performance/{plant.id}/scan?{Q}")
    assert r.status_code == 200 and r.json()["status"] == "ok" and len(r.json()["alert_ids"]) == 1
    client.post(f"/api/v1/performance/{plant.id}/scan?{Q}")  # idempotent
    alerts = client.get(f"/api/v1/performance/{plant.id}?{Q}").json()["open_alerts"]
    assert len(alerts) == 1 and alerts[0]["scope"] == "string" and alerts[0]["evidence"]["baseline"] == "pvwatts"
    legacy = client.get(f"/api/v1/alerts?plant_id={plant.id}").json()  # additive fields on the existing schema
    assert legacy[0]["string_id"] == alerts[0]["string_id"] and legacy[0]["evidence"]["data_source"] == "SIMULATED"


def test_window_validation(client, seeded):
    plant, _ = seeded
    base = f"/api/v1/performance/{plant.id}"
    assert client.get(f"{base}?start=2026-01-01T00:00:00Z&end=2026-06-01T00:00:00Z").status_code == 422  # > 92 days
    assert client.get(f"{base}?start=2026-03-02T00:00:00Z&end=2026-03-01T00:00:00Z").status_code == 422
    assert client.get(f"{base}?baseline=bogus").status_code == 422
    assert client.get(f"{base}?{Q}&baseline=hybrid").status_code == 422  # no trained artifact
    assert client.get("/api/v1/performance/9999").status_code == 404


def test_no_telemetry_window(client, seeded):
    plant, _ = seeded
    b = client.get(f"/api/v1/performance/{plant.id}?start=2025-01-01T00:00:00Z&end=2025-01-02T00:00:00Z").json()
    assert b["status"] == "no_telemetry" and b["series"] == []


@pytest.mark.parametrize("body,ok", [
    ({"pi_warning": 0.97, "pi_critical": 0.92, "deficit_min_clear_hours": 2}, True),
    ({"pi_warning": 0.9, "pi_critical": 0.95, "deficit_min_clear_hours": 3}, False),
    ({"pi_warning": 1.01, "pi_critical": 0.9, "deficit_min_clear_hours": 3}, False),
    ({"pi_warning": 0.95, "pi_critical": 0.0, "deficit_min_clear_hours": 3}, False),
    ({"pi_warning": 0.95, "pi_critical": 0.9, "deficit_min_clear_hours": 0}, False),
    ({"pi_warning": 0.95, "pi_critical": 0.9, "deficit_min_clear_hours": 25}, False),
])
def test_thresholds(client, db_session, seeded, body, ok):
    plant, _ = seeded
    r = client.put(f"/api/v1/performance/{plant.id}/thresholds", json=body)
    assert (r.status_code == 200) == ok, r.text
    db_session.expire_all()
    assert db_session.get(type(plant), plant.id).pi_warning == (body["pi_warning"] if ok else 0.95)


def test_peers(client, seeded):
    plant, strs = seeded
    bad = client.get(f"/api/v1/performance/{plant.id}?{Q}").json()["events"][0]["scope_id"]
    r = client.get(f"/api/v1/strings/{bad}/peers?{Q}")
    assert r.status_code == 200, r.text
    b = r.json()
    assert b["status"] == "ok" and b["peer_z"] <= -3 and b["normalised_yield"] == pytest.approx(0.9, abs=0.02)
    assert len(b["peers"]) == 8 and b["plant_median"] > b["normalised_yield"]
    assert client.get("/api/v1/strings/99999/peers").status_code == 404


def test_tracker_plant_is_422_except_thresholds(client, db_session, seeded):
    plant, strs = seeded
    plant.location = f"Pune {TRACKER_MARKER}"
    db_session.commit()
    for method, url, kw in [("get", f"/api/v1/performance/{plant.id}", {}), ("post", f"/api/v1/performance/{plant.id}/scan", {}),
                            ("put", f"/api/v1/performance/{plant.id}/thresholds",
                             {"json": {"pi_warning": 0.95, "pi_critical": 0.9, "deficit_min_clear_hours": 3}}),
                            ("get", f"/api/v1/strings/{strs[0].id}/peers", {})]:
        r = getattr(client, method)(url, **kw)
        if method == "put":  # thresholds are plain settings, allowed for trackers
            assert r.status_code == 200, url
            continue
        assert r.status_code == 422 and r.json()["detail"]["status"] == "baseline_unsupported_for_trackers", url


def test_rbac(client, users_mode, make_user, login, seeded, two_projects, db_session):
    plant, strs = seeded
    plant.park_id = "PARK_A"  # a plant with no park is admin-only (test_performance_scoping)
    db_session.commit()
    make_user("v@x.test", "viewer", project_ids=[two_projects["p1"]])
    make_user("o@x.test", "operator", project_ids=[two_projects["p1"]])
    v, o = login("v@x.test"), login("o@x.test")
    body = {"pi_warning": 0.95, "pi_critical": 0.9, "deficit_min_clear_hours": 3}
    p = f"/api/v1/performance/{plant.id}"
    assert client.get(p).status_code == 401
    assert client.get(f"{p}?{Q}", headers=v).status_code == 200
    assert client.get(f"/api/v1/strings/{strs[0].id}/peers?{Q}", headers=v).status_code == 200
    assert client.post(f"{p}/scan?{Q}", headers=v).status_code == 403
    assert client.put(f"{p}/thresholds", json=body, headers=v).status_code == 403
    assert client.post(f"{p}/scan?{Q}", headers=o).status_code == 200
    assert client.put(f"{p}/thresholds", json=body, headers=o).status_code == 200
