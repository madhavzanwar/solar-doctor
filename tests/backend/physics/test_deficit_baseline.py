"""Deficit baselines agree with solar.expected_power and fail clearly where they must."""
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest
from fastapi import HTTPException

from solardoctor.physics import baseline, irradiance as irr, solar
from solardoctor.physics import registry
from solardoctor.physics.tracker import TRACKER_MARKER

PLANT = SimpleNamespace(id=1, name="p", lat=18.52, lon=73.86, altitude_m=560.0, tilt=20.0, azimuth=180.0,
                        dc_kw=100.0, ac_kw=80.0, temp_coeff=-0.004, location="Pune")
TIMES = pd.date_range("2026-03-19", periods=96, freq="15min", tz="UTC")


def _weather(ghi_scale=0.7, poa=None):
    cs = irr.resolve_weather(PLANT, TIMES, None, now=TIMES[0] - pd.Timedelta(days=1),
                             nasa_fetch=pytest.fail, openmeteo_fetch=lambda *a, **k: (_ for _ in ()).throw(OSError()))
    w = cs.copy()
    w["ghi"] = cs["ghi_clearsky"] * ghi_scale
    w["temp_air"], w["wind_speed"] = 30.0, 2.0
    if poa is not None:
        w["poa"] = poa
    return w


def test_pvwatts_matches_solar_expected_power_within_3pct():
    w = _weather()
    new = baseline.expected_power(PLANT, w, "pvwatts")
    old = solar.expected_power(PLANT, TIMES, ghi=w["ghi"], temp_air=w["temp_air"], wind_speed=w["wind_speed"])
    day = old["p_ac_kw"] > 5
    assert day.any()
    assert abs(new.loc[day, "p_ac_kw"].sum() / old.loc[day, "p_ac_kw"].sum() - 1) < 0.03
    assert (new.loc[~(old["solar_elevation"] > 0), "p_ac_kw"] == 0).all()
    assert new["p_ac_kw"].max() <= PLANT.ac_kw + 1e-9  # clipped


def test_clearsky_is_ceiling_and_site_poa_is_used_directly():
    w = _weather(0.6)
    assert baseline.expected_power(PLANT, w, "clearsky")["p_ac_kw"].sum() > baseline.expected_power(PLANT, w, "pvwatts")["p_ac_kw"].sum()
    half = _weather(0.6, poa=pd.Series(300.0, index=TIMES))
    out = baseline.expected_power(PLANT, half, "pvwatts")
    sun = out["solar_zenith"] < 80
    assert (out.loc[sun, "poa_global"] == 300.0).all()


def test_hybrid_unavailable_without_artifact_and_tracker_refused(tmp_path):
    from ml.forecast.serving.model_registry import ModelRegistry
    registry.reset_registry(ModelRegistry(artifact_dir=tmp_path))
    try:
        with pytest.raises(HTTPException) as e:
            baseline.expected_power(PLANT, _weather(), "hybrid")
        assert e.value.status_code == 422 and e.value.detail["status"] == "hybrid_model_unavailable"
    finally:
        registry.reset_registry(None)
    tr = SimpleNamespace(**{**PLANT.__dict__, "location": f"x {TRACKER_MARKER}"})
    with pytest.raises(HTTPException) as e:
        baseline.expected_power(tr, _weather(), "pvwatts")
    assert e.value.detail["status"] == "baseline_unsupported_for_trackers"
