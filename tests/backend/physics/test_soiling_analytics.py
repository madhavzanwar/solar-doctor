"""Soiling / degradation analytics on SIMULATED daily series with known injected rates."""
from datetime import date, datetime, timezone
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from solardoctor.physics import soiling_analytics as sa

PLANT = SimpleNamespace(id=1)


def _daily(days, since_clean, rate, seed=0, start="2024-03-01", drift_per_year=0.0, noise=0.005):
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start, periods=days, freq="D", tz="UTC")
    n = np.arange(days)
    ratio = (1 - rate * since_clean(n)) * (1 + drift_per_year * n / 365) * (1 + rng.normal(0, noise, days))
    expected = pd.Series(30.0 + rng.normal(0, 2.0, days), index=idx)
    return pd.DataFrame({"expected_kwh": expected, "actual_kwh": expected * ratio, "insolation": expected / 6.0})


def test_srr_recovers_injected_rate_and_cleanings():
    since = lambda n: np.where(n < 25, n, np.where(n < 50, n - 25, n - 50))  # cleanings on day 25 and 50
    res = sa.soiling_analysis(PLANT, _daily(70, since, 0.004), reps=100)
    assert res["status"] == "ok" and res["method"] == "rdtools_srr" and res["label"] == "measured"
    assert res["soiling_loss_rate_per_day"] == pytest.approx(0.004, abs=0.001)  # injected 0.4 %/day, tolerance 0.1 %/day
    assert res["soiling_loss_rate_ci_per_day"][0] <= res["soiling_loss_rate_per_day"] <= res["soiling_loss_rate_ci_per_day"][1]
    assert res["soiling_ratio_ci"][0] <= res["soiling_ratio_p50"] <= res["soiling_ratio_ci"][1]
    assert res["cleaning_events"] == ["2024-03-26", "2024-04-20"]


def test_short_series_with_rain_uses_kimber_modelled():
    rain = pd.Series(0.0, index=pd.date_range("2024-03-01", periods=45 * 24, freq="h", tz="UTC"))
    rain.iloc[10 * 24 + 6] = 8.0  # one rain event above the 6 mm cleaning threshold
    res = sa.soiling_analysis(PLANT, _daily(45, lambda n: 0 * n, 0.0), rain)
    assert res["method"] == "pvlib_kimber" and res["label"] == "modelled" and res["status"] == "ok"
    assert res["parameters"]["cleaning_threshold"] == 6.0 and res["cleaning_events"] == ["2024-03-11"]
    assert 0.0 < 1 - res["soiling_ratio_latest"] < 0.3


def test_no_rain_short_series_is_insufficient_and_empty_is_unavailable():
    res = sa.soiling_analysis(PLANT, _daily(30, lambda n: 0 * n, 0.0), None)
    assert res["status"] == "insufficient_data" and "30 days" in res["reason"]
    res = sa.soiling_analysis(PLANT, pd.DataFrame(columns=["actual_kwh", "expected_kwh", "insolation"]), None)
    assert res["status"] == "unavailable" and res["method"] == "unavailable" and "Solar Data Tools" in res["reason"]


def test_degradation_yoy_recovers_rate():
    res = sa.degradation_analysis(PLANT, _daily(int(2.2 * 365), lambda n: 0 * n, 0.0, drift_per_year=-0.007, noise=0.01))
    assert res["status"] == "ok" and res["method"] == "rdtools_yoy"
    assert res["rate_pct_per_year"] == pytest.approx(-0.7, abs=0.3)  # injected -0.7 %/yr
    assert res["ci_pct_per_year"][0] <= res["rate_pct_per_year"] <= res["ci_pct_per_year"][1]


def test_degradation_needs_two_years():
    res = sa.degradation_analysis(PLANT, _daily(400, lambda n: 0 * n, 0.0))
    assert res["status"] == "insufficient_data" and res["days_available"] == 400


def test_save_is_idempotent_upsert(db_session):
    from solardoctor.physics.models import Plant, PlantAnalytics
    p = Plant(name="p", lat=18.5, lon=73.8, dc_kw=100, ac_kw=90)
    db_session.add(p)
    db_session.commit()
    day = date(2024, 5, 1)
    sa.save(db_session, p.id, "soiling", day, {"method": "pvlib_kimber", "label": "modelled", "x": 1})
    sa.save(db_session, p.id, "soiling", day, {"method": "pvlib_kimber", "label": "modelled", "x": 2},
            now=datetime(2024, 5, 1, tzinfo=timezone.utc))
    assert db_session.query(PlantAnalytics).count() == 1
    assert sa.latest(db_session, p.id, "soiling")["x"] == 2 and sa.latest(db_session, p.id, "degradation") is None
