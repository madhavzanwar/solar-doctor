"""QA flags: each gate fires on the data it should and clear-sky needs verifiable irradiance."""
from types import SimpleNamespace

import numpy as np
import pandas as pd

from solardoctor.physics import baseline, irradiance as irr, qa

PLANT = SimpleNamespace(id=1, name="p", lat=18.52, lon=73.86, altitude_m=560.0, tilt=20.0, azimuth=180.0,
                        dc_kw=100.0, ac_kw=80.0, temp_coeff=-0.004, location="Pune")
TIMES = pd.date_range("2026-03-19", periods=96, freq="15min", tz="UTC")


def _setup(source=irr.SITE):
    w = irr.resolve_weather(PLANT, TIMES, None, now=TIMES[0] - pd.Timedelta(days=1), nasa_fetch=lambda *a, **k: 1 / 0,
                            openmeteo_fetch=lambda *a, **k: 1 / 0)
    w["source"] = source
    exp = baseline.expected_power(PLANT, w, "pvwatts")
    return w, exp, exp["p_ac_kw"] * 0.97


def test_clear_healthy_day_is_mostly_usable_midday_only():
    w, exp, power = _setup()
    f, stats = qa.qc_flags(power, w, exp, PLANT)
    use = f["usable"]
    assert use.sum() > 20 and not use[exp["solar_zenith"] >= 75].any() and not use[exp["poa_global"] <= 200].any()
    assert stats["clearsky_method"] == "reno" and stats["usable"] == use.sum()


def test_gap_stale_outlier_curtailment_flags():
    w, exp, power = _setup()
    power = power.copy()
    noon = int(exp["p_ac_kw"].to_numpy().argmax())
    power.iloc[noon - 8] = np.nan
    power.iloc[noon - 4] = power.iloc[noon - 4] * 3  # spike
    power.iloc[noon + 2: noon + 8] = 33.333  # frozen logger
    curt = pd.Series(False, index=TIMES)
    curt.iloc[noon + 10: noon + 14] = True
    f, _ = qa.qc_flags(power, w, exp, PLANT, curtailed=curt)
    assert f["gap"].iloc[noon - 8] and f["outlier"].iloc[noon - 4]
    assert f["stale"].iloc[noon + 2: noon + 8].any()
    assert f["curtailed"].iloc[noon + 10: noon + 14].all() and not f["usable"].iloc[noon + 10: noon + 14].any()
    assert not f["usable"].iloc[noon - 8] and not f["usable"].iloc[noon - 4]


def test_clipping_level_flag():
    w, exp, _ = _setup()
    f, _ = qa.qc_flags(exp["p_ac_kw"].clip(upper=PLANT.ac_kw), w, exp, PLANT)
    hit = exp["p_ac_kw"] >= 0.98 * PLANT.ac_kw
    assert (not hit.any()) or f.loc[hit, "clipped"].all()


def test_cloudy_index_not_clearsky_and_modelled_irradiance_unusable():
    w, exp, power = _setup()
    cloudy = w.copy()
    cloudy["ghi"] = w["ghi_clearsky"] * 0.4
    f, _ = qa.qc_flags(power, cloudy, exp, PLANT)
    assert not f["usable"].any()
    w2, exp2, power2 = _setup(source=irr.CLEARSKY)
    f2, stats2 = qa.qc_flags(power2, w2, exp2, PLANT)
    assert not f2["usable"].any() and stats2["no_irradiance_for_clearsky_check"]


def test_hourly_uses_clear_sky_index_method():
    times = pd.date_range("2026-03-19", periods=24, freq="h", tz="UTC")
    w = irr.resolve_weather(PLANT, times, None, now=times[0] - pd.Timedelta(days=1), nasa_fetch=lambda *a, **k: 1 / 0)
    w["source"] = irr.NASA
    exp = baseline.expected_power(PLANT, w, "pvwatts")
    f, stats = qa.qc_flags(exp["p_ac_kw"], w, exp, PLANT)
    assert stats["clearsky_method"] == "clear_sky_index"
