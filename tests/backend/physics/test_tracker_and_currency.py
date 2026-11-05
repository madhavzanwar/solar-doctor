"""Tracker plants (fixed-tilt baseline invalid) and currency-aware diagnosis text."""
from datetime import datetime, timedelta, timezone

import pytest

from solardoctor.physics.tracker import BASELINE_UNSUPPORTED_STATUS, TRACKER_MARKER, is_tracker_plant

PLANT = dict(name="P", latitude=18.5, longitude=73.8, timezone="Asia/Kolkata",
             capacity_kw=120.0, inverter_capacity_kw=100.0)
NOON = datetime(2026, 3, 20, 7, 0, tzinfo=timezone.utc)  # Pune solar noon


@pytest.fixture(autouse=True)
def _iso(monkeypatch, tmp_path):
    monkeypatch.delenv("SOLARDOCTOR_WEATHER_API_KEY", raising=False)
    monkeypatch.setenv("SOLARDOCTOR_FORECAST_ARTIFACTS", str(tmp_path / "a"))
    from solardoctor.physics.registry import reset_registry
    reset_registry()
    yield
    reset_registry()


def _mk(client, tracker=False, **kw):
    loc = f"Kersey, CO {TRACKER_MARKER}" if tracker else "Pune"
    r = client.post("/api/v1/plants", json={**PLANT, "location": loc, **kw})
    assert r.status_code == 201, r.text
    return r.json()


def _orm(db, tracker, tariff=None):
    from solardoctor.physics.models import Plant
    p = Plant(name="T" if tracker else "F", lat=18.52, lon=73.86, dc_kw=120, ac_kw=100, tilt=18, azimuth=180,
              altitude_m=560, tariff_inr_kwh=tariff,
              location=f"x {TRACKER_MARKER}" if tracker else "x")
    db.add(p)
    db.commit()
    return p


def _assert_unsupported(resp):
    assert resp.status_code == 422, resp.text
    assert resp.json()["detail"]["status"] == BASELINE_UNSUPPORTED_STATUS


# ── helper ──────────────────────────────────────────────────────────────────

def test_is_tracker_plant_marker_only():
    from types import SimpleNamespace as NS
    assert is_tracker_plant(NS(location=f"Kersey, CO {TRACKER_MARKER}"))
    assert not is_tracker_plant(NS(location="Kersey, CO"))
    assert not is_tracker_plant(NS(location=None))
    assert not is_tracker_plant(NS())  # no location attribute at all
    assert not is_tracker_plant(NS(location="single-axis tracker"))  # prose without the marker


def test_pvdaq_importer_marker_matches_helper():
    from solardoctor.seed.pvdaq import _location
    loc = _location({"location": "Kersey, CO"}, {"tracking": "t", "type": "single-axis tracker"})
    from types import SimpleNamespace as NS
    assert is_tracker_plant(NS(location=loc))
    assert not is_tracker_plant(NS(location=_location({"location": "X"}, {"tracking": "f", "type": "fixed"})))


# ── expected power / API baseline requests ──────────────────────────────────

def test_expected_power_raises_for_tracker_but_not_fixed(db_session):
    from solardoctor.physics import solar
    from solardoctor.physics.tracker import BaselineUnsupportedForTrackers
    with pytest.raises(BaselineUnsupportedForTrackers):
        solar.expected_power(_orm(db_session, True), [NOON])
    assert solar.expected_power(_orm(db_session, False), [NOON])["p_ac_kw"].iloc[0] > 0


def test_forecast_generate_and_probabilistic_422_for_tracker(client):
    t = _mk(client, tracker=True)
    _assert_unsupported(client.post(f"/api/v1/forecast/{t['id']}/generate"))
    _assert_unsupported(client.get(f"/api/v1/forecast/{t['id']}/probabilistic"))
    assert client.get(f"/api/v1/forecast/{t['id']}").json() == []  # nothing was persisted


def test_forecast_unchanged_for_fixed_plant(client):
    f = _mk(client)
    assert client.post(f"/api/v1/forecast/{f['id']}/generate").status_code == 200
    assert client.get(f"/api/v1/forecast/{f['id']}/probabilistic").status_code == 200


# ── anomaly / alerts ────────────────────────────────────────────────────────

def test_anomaly_service_never_alerts_for_tracker(db_session):
    from solardoctor.physics.anomaly_service import detect_and_persist_anomaly
    from solardoctor.physics.models import PlantAlert
    t, f = _orm(db_session, True), _orm(db_session, False)
    assert detect_and_persist_anomaly(db_session, t.id, NOON, 100.0, 10.0) is None
    assert detect_and_persist_anomaly(db_session, f.id, NOON, 100.0, 10.0) is not None
    assert [a.plant_id for a in db_session.query(PlantAlert)] == [f.id]


@pytest.mark.parametrize("with_forecast", [False, True])
def test_alert_worker_skips_tracker(db_session, with_forecast):
    from solardoctor.physics import alert_worker
    from solardoctor.physics.models import Forecast, PlantAlert, Telemetry
    t = _orm(db_session, True)
    db_session.add(Telemetry(plant_id=t.id, ts=NOON, p_ac_kw=10.0, ghi_wm2=800.0, source="USER"))
    if with_forecast:
        db_session.add(Forecast(plant_id=t.id, forecast_time=NOON, predicted_power_kw=90.0,
                                confidence_lower=80.0, confidence_upper=100.0, model_name="x", model_version="1"))
    db_session.commit()
    assert alert_worker.run_alert_check(db_session, t.id, now=NOON + timedelta(minutes=5)) == 0
    assert db_session.query(PlantAlert).count() == 0


# ── diagnosis ───────────────────────────────────────────────────────────────

def test_diagnose_from_telemetry_422_for_tracker_but_explicit_values_ok(client, db_session):
    from solardoctor.physics.models import Telemetry
    t = _mk(client, tracker=True)
    db_session.add(Telemetry(plant_id=t["id"], ts=datetime.now(tz=timezone.utc), p_ac_kw=10.0,
                             p_expected_kw=90.0, source="USER"))
    db_session.commit()
    _assert_unsupported(client.post("/api/v1/diagnosis/diagnose", json={"plant_id": t["id"]}))
    ok = client.post("/api/v1/diagnosis/diagnose",
                     json={"plant_id": t["id"], "expected_power_kw": 90.0, "actual_power_kw": 60.0})
    assert ok.status_code == 200, ok.text  # caller-supplied numbers are not baseline output


# ── currency-aware money text ───────────────────────────────────────────────

def _soiling_steps(client, plant_id):
    r = client.post("/api/v1/diagnosis/diagnose", json={
        "plant_id": plant_id, "expected_power_kw": 80.0, "actual_power_kw": 70.0,
        "irradiance_w_m2": 900.0, "days_since_cleaning": 30})
    assert r.status_code == 200, r.text
    return r.json()


def test_money_text_unset_and_inr(client):
    unset = _soiling_steps(client, _mk(client)["id"])
    assert unset["currency"] == "unset"
    assert "$" not in unset["summary"] and "not estimated" in unset["financial_assumption"]
    text = " ".join(s["action"] for s in unset["technician_steps"])
    assert "$" not in text and "USD" not in text

    inr = _soiling_steps(client, _mk(client, name="Q", tariff_inr_kwh=6.0)["id"])
    assert inr["currency"] == "INR"
    assert "$" not in inr["summary"] and (inr["financial_impact_per_day"] == 0 or "₹" in inr["summary"])
    assert "$" not in " ".join(s["action"] for s in inr["technician_steps"])


def test_localize_money_text_cases():
    from solardoctor.physics.diagnosis_service import localize_money_text as loc
    s = "compare cleaning cost ($/kW) against gain"
    assert loc(s, "USD") == s                        # SolarPulse text unchanged (golden parity)
    assert "(₹/kW)" in loc(s, "INR") and "$" not in loc(s, "INR")
    u = loc(s, "unset")
    assert "$" not in u and "not estimated" in u
    assert loc("no money here", "INR") == "no money here"


def test_stored_diagnosis_listing_reports_plant_currency(client):
    p = _mk(client, tariff_inr_kwh=6.0)
    _soiling_steps(client, p["id"])
    lst = client.get(f"/api/v1/diagnosis/plant/{p['id']}").json()
    assert lst and lst[0]["currency"] == "INR" and lst[0]["plant_name"] == "P"
    q = _mk(client, name="Q2")
    _soiling_steps(client, q["id"])
    assert client.get(f"/api/v1/diagnosis/plant/{q['id']}").json()[0]["currency"] == "unset"
