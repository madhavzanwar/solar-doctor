"""SolarPulse-shaped endpoints under /api/v1 (TestClient, temp SQLite, no network)."""
from datetime import datetime, timedelta, timezone

import pytest

PUNE = dict(
    name="PCCoE Rooftop", location="Pune, Maharashtra", latitude=18.5204, longitude=73.8567,
    timezone="Asia/Kolkata", capacity_kw=120.0, inverter_capacity_kw=100.0, module_count=300,
    tilt=18.0, azimuth=180.0, tariff_inr_kwh=6.5, altitude_m=560.0,
)


@pytest.fixture(autouse=True)
def _no_weather_key_and_isolated_registry(monkeypatch, tmp_path):
    monkeypatch.delenv("SOLARDOCTOR_WEATHER_API_KEY", raising=False)
    monkeypatch.delenv("WEATHER_API_KEY", raising=False)
    monkeypatch.setenv("SOLARDOCTOR_FORECAST_ARTIFACTS", str(tmp_path / "artifacts"))
    from solardoctor.physics.registry import reset_registry
    reset_registry()
    yield
    reset_registry()


@pytest.fixture
def plant(client):
    r = client.post("/api/v1/plants", json=PUNE)
    assert r.status_code == 201, r.text
    return r.json()


def test_plants_crud_shape(client, plant):
    assert plant["capacity_kw"] == 120.0 and plant["inverter_capacity_kw"] == 100.0
    assert plant["latitude"] == 18.5204 and plant["timezone"] == "Asia/Kolkata"
    assert client.get("/api/v1/plants").json()[0]["id"] == plant["id"]
    cfg = client.get(f"/api/v1/plants/{plant['id']}/config").json()
    assert cfg["tilt"] == 18.0 and cfg["plant_id"] == plant["id"]
    r = client.put(f"/api/v1/plants/{plant['id']}/config", json={"tilt": 22.0})
    assert r.json()["tilt"] == 22.0
    assert client.get("/api/v1/plants/9999").status_code == 404
    assert client.delete(f"/api/v1/plants/{plant['id']}").status_code == 200
    assert client.get("/api/v1/plants").json() == []


def test_park_link_is_one_to_one(client, db_session):
    from solardoctor.db.models import Park
    db_session.add(Park(id="PARK_A", name="A"))
    db_session.commit()
    a = client.post("/api/v1/plants", json={**PUNE, "park_id": "PARK_A"})
    assert a.status_code == 201 and a.json()["park_id"] == "PARK_A"
    b = client.post("/api/v1/plants", json={**PUNE, "park_id": "PARK_A"})
    assert b.status_code == 409
    assert client.post("/api/v1/plants", json={**PUNE, "park_id": "NOPE"}).status_code == 404
    db_session.expire_all()
    from solardoctor.physics.models import Plant
    park = db_session.get(Park, "PARK_A")
    assert park.plant.id == a.json()["id"] and db_session.get(Plant, a.json()["id"]).park is park


def test_forecast_generate_list_summary(client, plant):
    pid = plant["id"]
    assert client.get(f"/api/v1/forecast/{pid}/summary").status_code == 404
    r = client.post(f"/api/v1/forecast/{pid}/generate?horizon_minutes=60")
    assert r.status_code == 200, r.text
    rec = r.json()
    assert rec["model_name"] == "physics_baseline"  # no trained artifact -> honest label
    assert 0.0 <= rec["predicted_power_kw"] <= plant["inverter_capacity_kw"]
    assert rec["confidence_lower"] <= rec["predicted_power_kw"] <= rec["confidence_upper"]
    assert len(client.get(f"/api/v1/forecast/{pid}").json()) == 1
    s = client.get(f"/api/v1/forecast/{pid}/summary").json()
    assert s["record_count"] == 1 and s["plant_id"] == pid


def test_probabilistic_shape_and_label(client, plant):
    r = client.get(f"/api/v1/forecast/{plant['id']}/probabilistic?horizon_minutes=120&interval_minutes=30")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["model_name"] == "physics_scenario_simulated"
    assert len(body["points"]) == 5
    for p in body["points"]:
        assert p["p10_kw"] <= p["p50_kw"] <= p["p90_kw"] <= plant["inverter_capacity_kw"] + 1e-6
    assert {"ramp_risk_score", "primary_action_advisory"} <= set(body["summary"])


def test_online_status(client, plant):
    s = client.get(f"/api/v1/forecast/{plant['id']}/online-status").json()
    assert s["status"] == "BASELINE_OPTIMAL" and s["scaling_factor"] == 1.0
    assert s["samples_observed_today"] == 0


def test_alerts_resolve_and_axalon_alert_test_still_routed(client, plant, db_session):
    from solardoctor.physics.models import PlantAlert
    now = datetime.now(tz=timezone.utc)
    a = PlantAlert(plant_id=plant["id"], timestamp=now, alert_type="shortfall", severity="CRITICAL",
                   message="x", expected_power_kw=100, actual_power_kw=60, deviation_percent=40)
    db_session.add(a)
    db_session.commit()
    lst = client.get(f"/api/v1/alerts?plant_id={plant['id']}").json()
    assert len(lst) == 1 and lst[0]["is_resolved"] is False
    r = client.patch(f"/api/v1/alerts/{a.id}/resolve")
    assert r.status_code == 200 and r.json()["is_resolved"] is True and r.json()["resolved_at"]
    assert client.patch("/api/v1/alerts/9999/resolve").status_code == 404
    # Axalon's own alerts router still owns POST /alerts/test
    assert client.post("/api/v1/alerts/test").status_code == 200


def test_diagnosis_endpoints(client, plant, db_session):
    tax = client.get("/api/v1/diagnosis/taxonomy").json()
    assert {t["category"] for t in tax} >= {"INVERTER_TRIP_OVERTEMP", "SOILING_DEGRADATION"}
    r = client.post("/api/v1/diagnosis/diagnose", json={
        "plant_id": plant["id"], "inverter_error_code": "F056", "expected_power_kw": 80, "actual_power_kw": 40})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["root_cause_category"] == "INVERTER_TRIP_OVERTEMP" and d["id"] and d["technician_steps"]
    assert d["currency"] == "INR"  # plant has a tariff -> INR
    assert d["financial_impact_per_day"] == round(40 * 5.5 * 6.5, 2)
    lst = client.get(f"/api/v1/diagnosis/plant/{plant['id']}").json()
    assert len(lst) == 1 and lst[0]["id"] == d["id"]
    assert client.get("/api/v1/diagnosis/alert/9999").status_code == 404

    from solardoctor.physics.models import PlantAlert
    a = PlantAlert(plant_id=plant["id"], timestamp=datetime.now(tz=timezone.utc), alert_type="soiling",
                   severity="WARNING", message="Dust soiling deficit", expected_power_kw=100, actual_power_kw=88)
    db_session.add(a)
    db_session.commit()
    first = client.get(f"/api/v1/diagnosis/alert/{a.id}").json()
    assert first["root_cause_category"] == "SOILING_DEGRADATION"
    assert client.get(f"/api/v1/diagnosis/alert/{a.id}").json()["id"] == first["id"]  # cached, not re-created


def test_weather_mock_is_labelled(client, plant):
    cur = client.get(f"/api/v1/weather/{plant['id']}/current").json()
    assert cur["source"] == "mock" and "Simulated" in cur["current"]["condition"]
    fc = client.get(f"/api/v1/weather/{plant['id']}/forecast?days=2").json()
    assert fc["source"] == "mock" and len(fc["hourly_forecast"]) == 72


def test_scada_ingest_and_ws(client, plant):
    ts = datetime.now(tz=timezone.utc).isoformat()
    r = client.post("/api/v1/scada/readings", json={
        "plant_id": plant["id"], "timestamp": ts, "power_kw": 42.0, "irradiance_w_m2": 700.0,
        "temperature_c": 31.0, "source": "SIMULATED"})
    assert r.status_code == 201, r.text
    assert client.post("/api/v1/scada/readings", json={"plant_id": 999, "timestamp": ts}).status_code == 404
    rows = client.get(f"/api/v1/scada/{plant['id']}/readings").json()
    assert rows[0]["power_kw"] == 42.0
    assert client.get(f"/api/v1/scada/{plant['id']}/stats").json()["total_readings"] == 1
    with client.websocket_connect(f"/api/v1/ws/scada/{plant['id']}") as ws:
        assert ws.receive_json()["_source"] == "stream_init"
    with pytest.raises(Exception):
        with client.websocket_connect("/api/v1/ws/scada/9999"):
            pass


def test_openapi_contains_ported_paths(client):
    paths = client.get("/openapi.json").json()["paths"]
    for p in ("/api/v1/plants", "/api/v1/plants/{plant_id}/config", "/api/v1/forecast/{plant_id}",
              "/api/v1/forecast/{plant_id}/summary", "/api/v1/forecast/{plant_id}/probabilistic",
              "/api/v1/forecast/{plant_id}/online-status", "/api/v1/alerts",
              "/api/v1/alerts/{alert_id}/resolve", "/api/v1/diagnosis/taxonomy",
              "/api/v1/diagnosis/diagnose", "/api/v1/weather/{plant_id}/current",
              "/api/v1/weather/{plant_id}/forecast", "/api/v1/alerts/test"):
        assert p in paths, p
