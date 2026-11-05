"""Forecast summary kWh must use the real timestep (SolarPulse assumed 1-minute spacing)."""
from datetime import datetime, timedelta, timezone

import pytest

from solardoctor.physics.forecast_service import energy_kwh, infer_timestep_hours

T0 = datetime(2026, 3, 20, 6, 0, tzinfo=timezone.utc)


def _times(offsets_min):
    return [T0 + timedelta(minutes=m) for m in offsets_min]


@pytest.mark.parametrize("step_min", [1, 5, 15, 60])
def test_infer_regular_spacing(step_min):
    assert infer_timestep_hours(_times(range(0, step_min * 10, step_min))) == pytest.approx(step_min / 60.0)


def test_infer_irregular_uses_median_and_ignores_duplicates():
    # gaps: 5, 5, 5, 30 -> median 5 min; the duplicate timestamp adds no zero gap
    assert infer_timestep_hours(_times([0, 5, 5, 10, 15, 45])) == pytest.approx(5 / 60.0)


def test_infer_fallback_is_one_minute():
    assert infer_timestep_hours([]) == pytest.approx(1 / 60.0)
    assert infer_timestep_hours(_times([0])) == pytest.approx(1 / 60.0)
    assert infer_timestep_hours(_times([0, 0])) == pytest.approx(1 / 60.0)


def test_one_minute_matches_solarpulse_divide_by_60():
    powers = [10.0, 20.0, 30.0, 40.0]
    assert energy_kwh(powers, infer_timestep_hours(_times(range(4)))) == pytest.approx(sum(powers) / 60.0)


def test_hand_computed_example():
    # Four 15-minute samples of 40, 80, 60, 20 kW: (40+80+60+20) * 0.25 h = 50 kWh
    # (SolarPulse's /60 would have reported 3.3333 kWh).
    assert energy_kwh([40, 80, 60, 20], infer_timestep_hours(_times([0, 15, 30, 45]))) == pytest.approx(50.0)


def _seed(db, pid, offsets_min, powers, actuals=None):
    from solardoctor.physics.models import Forecast
    for i, (m, p) in enumerate(zip(offsets_min, powers)):
        db.add(Forecast(plant_id=pid, forecast_time=T0 + timedelta(minutes=m), predicted_power_kw=p,
                        actual_power_kw=None if actuals is None else actuals[i], model_name="physics_baseline"))
    db.commit()


@pytest.fixture
def plant_id(client):
    r = client.post("/api/v1/plants", json=dict(name="P", latitude=18.5, longitude=73.8, capacity_kw=120,
                                                inverter_capacity_kw=100))
    return r.json()["id"]


@pytest.mark.parametrize("step_min,expected", [(1, 200.0 / 60.0), (5, 200.0 * 5 / 60.0), (15, 50.0), (60, 200.0)])
def test_summary_endpoint_regular_spacing(client, db_session, plant_id, step_min, expected):
    _seed(db_session, plant_id, [i * step_min for i in range(4)], [40, 80, 60, 20])
    s = client.get(f"/api/v1/forecast/{plant_id}/summary").json()
    assert s["total_predicted_kwh"] == pytest.approx(expected, abs=1e-3)
    assert s["total_actual_kwh"] is None and s["record_count"] == 4


def test_summary_endpoint_irregular_spacing_and_actuals(client, db_session, plant_id):
    # gaps 10, 10, 10, 60 -> median 10 min; actual kWh uses the same timestep
    _seed(db_session, plant_id, [0, 10, 20, 30, 90], [60, 60, 60, 60, 60], actuals=[30, 30, 30, 30, 30])
    s = client.get(f"/api/v1/forecast/{plant_id}/summary").json()
    assert s["total_predicted_kwh"] == pytest.approx(300 * 10 / 60.0, abs=1e-3)   # 50 kWh
    assert s["total_actual_kwh"] == pytest.approx(150 * 10 / 60.0, abs=1e-3)      # 25 kWh
    assert s["mean_absolute_error_kw"] == pytest.approx(30.0)


def test_summary_single_record_falls_back_to_one_minute(client, db_session, plant_id):
    _seed(db_session, plant_id, [0], [60])
    assert client.get(f"/api/v1/forecast/{plant_id}/summary").json()["total_predicted_kwh"] == pytest.approx(1.0)
