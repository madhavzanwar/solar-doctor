"""Forecast service paths: trained-artifact use, online-adapter feedback from SCADA ingestion.

The model trained here is a TEST FIXTURE fitted on synthetic data (a function of GHI). It only proves
the artifact path works; it is not a claim about real-world accuracy.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).parent))
from golden_cases import _train_data  # noqa: E402


@pytest.fixture
def plant(db_session):
    from solardoctor.physics.models import Plant
    p = Plant(name="P", lat=18.52, lon=73.86, dc_kw=120, ac_kw=100, tilt=18, azimuth=180, altitude_m=560)
    db_session.add(p)
    db_session.commit()
    return p


@pytest.fixture(autouse=True)
def _artifacts(monkeypatch, tmp_path):
    monkeypatch.setenv("SOLARDOCTOR_FORECAST_ARTIFACTS", str(tmp_path / "art"))
    from solardoctor.physics.registry import reset_registry
    reset_registry()
    yield tmp_path / "art"
    reset_registry()


def _weather_transport(now: datetime):
    def handler(request):
        hours = []
        base = int(now.replace(minute=0, second=0, microsecond=0).timestamp())
        for h in range(-1, 72):
            ts = base + 3600 * h
            hr = datetime.fromtimestamp(ts, tz=timezone.utc).hour
            hours.append({"time_epoch": ts, "temp_c": 30.0, "humidity": 40, "wind_kph": 10.0, "cloud": 20,
                          "uv": 8.0 if 4 <= hr <= 12 else 0.0, "condition": {"text": "Sunny"},
                          "is_day": 1 if 1 <= hr <= 13 else 0})
        return httpx.Response(200, json={
            "location": {"name": "Pune", "tz_id": "Asia/Kolkata"},
            "current": {"temp_c": 30, "humidity": 40, "wind_kph": 10, "cloud": 20, "uv": 8,
                        "condition": {"text": "Sunny"}, "is_day": 1},
            "forecast": {"forecastday": [{"hour": hours}]}})
    return httpx.MockTransport(handler)


def test_real_weather_drives_physics_baseline(db_session, plant, monkeypatch):
    from solardoctor.physics import forecast_service as fs
    monkeypatch.setenv("SOLARDOCTOR_WEATHER_API_KEY", "dummy")
    rec = fs.generate_forecast(db_session, plant, horizon_minutes=5,
                               weather_transport=_weather_transport(datetime.now(tz=timezone.utc)))
    assert rec.model_name == "physics_baseline"
    assert 0.0 <= rec.predicted_power_kw <= plant.ac_kw


def test_trained_artifact_is_used_when_present(db_session, plant, monkeypatch, _artifacts):
    from ml.forecast.features.feature_pipeline import SolarFeaturePipeline
    from ml.forecast.models.lightgbm_model import LightGBMForecaster
    from ml.forecast.models.probabilistic_model import ProbabilisticForecaster
    from solardoctor.physics import forecast_service as fs, solar
    X, y = _train_data()
    Xf = SolarFeaturePipeline(solar.plant_config_from_orm(plant)).transform(X)
    params = {"n_estimators": 30, "n_jobs": 1, "num_leaves": 7, "min_child_samples": 3}
    LightGBMForecaster(params=params).fit(Xf, y).save(_artifacts / "models" / "lgbm_latest.pkl")
    ProbabilisticForecaster(base_params=params).fit(Xf, y).save(_artifacts / "models" / "prob_latest.pkl")

    monkeypatch.setenv("SOLARDOCTOR_WEATHER_API_KEY", "dummy")
    tr = _weather_transport(datetime.now(tz=timezone.utc))
    rec = fs.generate_forecast(db_session, plant, horizon_minutes=5, weather_transport=tr)
    assert rec.model_name == "lightgbm" and 0.0 <= rec.predicted_power_kw <= plant.ac_kw
    prob = fs.generate_probabilistic_forecast(db_session, plant, horizon_minutes=60, interval_minutes=15,
                                              weather_transport=tr)
    assert prob.model_name == "probabilistic_quantile"
    for p in prob.points:
        assert p.p10_kw <= p.p50_kw <= p.p90_kw <= plant.ac_kw + 1e-6


def test_mock_weather_is_never_fed_to_trained_model(db_session, plant, _artifacts, monkeypatch):
    from ml.forecast.features.feature_pipeline import SolarFeaturePipeline
    from ml.forecast.models.lightgbm_model import LightGBMForecaster
    from solardoctor.physics import forecast_service as fs, solar
    monkeypatch.delenv("SOLARDOCTOR_WEATHER_API_KEY", raising=False)
    monkeypatch.delenv("WEATHER_API_KEY", raising=False)
    X, y = _train_data()
    Xf = SolarFeaturePipeline(solar.plant_config_from_orm(plant)).transform(X)
    LightGBMForecaster(params={"n_estimators": 10, "n_jobs": 1}).fit(Xf, y).save(_artifacts / "models" / "lgbm_latest.pkl")
    rec = fs.generate_forecast(db_session, plant, horizon_minutes=5)
    assert rec.model_name == "physics_baseline"


def test_scada_ingestion_steps_online_adapter(client, db_session, plant):
    from solardoctor.physics.models import Forecast
    from solardoctor.physics.registry import get_registry
    now = datetime.now(tz=timezone.utc).replace(microsecond=0)
    db_session.add(Forecast(plant_id=plant.id, forecast_time=now, predicted_power_kw=80.0, ml_power_kw=80.0,
                            model_name="physics_baseline", physics_power_kw=80.0))
    db_session.commit()
    r = client.post("/api/v1/scada/readings", json={
        "plant_id": plant.id, "timestamp": now.isoformat(), "power_kw": 72.0, "irradiance_w_m2": 700.0})
    assert r.status_code == 201
    st = get_registry().get_online_adapter(str(plant.id)).get_status()
    assert st["samples_observed_today"] == 1
    assert st["scaling_factor"] < 1.0  # actual below forecast pulls gamma down
    s = client.get(f"/api/v1/forecast/{plant.id}/online-status").json()
    assert s["samples_observed_today"] == 1
