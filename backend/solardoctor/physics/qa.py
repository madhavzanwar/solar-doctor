"""Data QA for the deficit detector (pvanalytics + irradiance/geometry gates).

A sample is ``usable`` only if it is present, not stale/outlying/clipped/curtailed, in daylight at a
high enough sun (zenith < 75 deg, POA > 200 W/m2) and in a clear-sky period. Clear-sky periods need
verifiable irradiance: with only the clear-sky model nothing can be checked, so nothing is usable.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pvanalytics.features import clearsky as pva_clearsky, clipping as pva_clipping
from pvanalytics.quality import gaps as pva_gaps, outliers as pva_outliers

from solardoctor.physics.irradiance import MEASURED_SOURCES, SITE

POA_MIN_WM2 = 200.0
ZENITH_MAX_DEG = 75.0
CLEARSKY_INDEX_RANGE = (0.8, 1.2)
CLIP_FRACTION = 0.98
FLAGS = ["gap", "stale", "outlier", "clipped", "daytime", "clearsky", "irradiance_ok", "zenith_ok", "curtailed"]


def _step(index: pd.DatetimeIndex) -> pd.Timedelta:
    return pd.Series(index).diff().median() if len(index) > 1 else pd.Timedelta(hours=1)


def qc_flags(power: pd.Series, weather: pd.DataFrame, expected: pd.DataFrame, plant,
             curtailed: pd.Series | None = None) -> tuple[pd.DataFrame, dict]:
    """Boolean QC flags on ``weather.index`` (+ ``usable``) and a stats dict. ``power`` is the series
    under test (any scope); ``expected`` is ``baseline.expected_power`` output on the same index."""
    idx = weather.index
    p = power.reindex(idx)
    step = _step(idx)
    fine = step <= pd.Timedelta(minutes=15)
    day = expected["solar_zenith"] < 90
    f = pd.DataFrame(index=idx)
    f["gap"] = p.isna()
    win = 4 if fine else 3  # about an hour of identical values
    f["stale"] = pva_gaps.stale_values_round(p.fillna(0.0), window=win, decimals=3, mark="tail") & day & ~f["gap"]
    f["outlier"] = pva_outliers.hampel(p.fillna(0.0), window=5) & ~f["gap"]
    clip_by_level = (p >= CLIP_FRACTION * plant.ac_kw) | (expected["p_ac_kw"] >= CLIP_FRACTION * plant.ac_kw)
    clip_geo = pd.Series(False, index=idx)
    if fine and day.sum() > 12:
        try:
            clip_geo = pva_clipping.geometric(p.fillna(0.0).clip(lower=0.0), freq=f"{int(step.total_seconds() // 60)}min")
        except Exception:  # pvanalytics needs enough regular daylight data; the level test still applies
            pass
    f["clipped"] = (clip_by_level | clip_geo) & day
    f["daytime"] = day
    verifiable = weather["source"].isin(MEASURED_SOURCES)
    site = weather["source"] == SITE
    if fine and site.mean() > 0.5:
        method = "reno"
        cs = pva_clearsky.reno(weather["ghi"].fillna(0.0), weather["ghi_clearsky"])
    else:
        method = "clear_sky_index"
        kc = weather["ghi"] / weather["ghi_clearsky"].clip(lower=1.0)
        cs = (kc >= CLEARSKY_INDEX_RANGE[0]) & (kc <= CLEARSKY_INDEX_RANGE[1])
    f["clearsky"] = cs & verifiable
    f["irradiance_ok"] = expected["poa_global"] > POA_MIN_WM2
    f["zenith_ok"] = expected["solar_zenith"] < ZENITH_MAX_DEG
    f["curtailed"] = (curtailed.reindex(idx).fillna(False).astype(bool) if curtailed is not None
                      else pd.Series(False, index=idx))
    good = f[["daytime", "clearsky", "irradiance_ok", "zenith_ok"]].all(axis=1)
    bad = f[["gap", "stale", "outlier", "clipped", "curtailed"]].any(axis=1)
    f["usable"] = good & ~bad
    f = f.astype(bool)
    stats = {"samples": int(len(f)), "clearsky_method": method, **{k: int(f[k].sum()) for k in FLAGS + ["usable"]}}
    if not verifiable.any():
        stats["no_irradiance_for_clearsky_check"] = True
    return f, stats


CLOCK_OFFSET_MIN = 30.0   # |offset| at or above this marks the scan time_offset_suspected
CLOCK_MAX_LAG = pd.Timedelta(hours=3)


def clock_offset_minutes(weather: pd.DataFrame) -> float | None:
    """Estimated clock offset (minutes, + = timestamps late) from the lag that best aligns site-measured GHI with the
    clear-sky curve; None without enough site GHI at fine resolution. Resolution is one sampling step."""
    idx = weather.index
    step = _step(idx)
    site = weather["source"] == SITE
    if len(idx) < 2 or step > pd.Timedelta(minutes=30) or site.mean() <= 0.5:
        return None
    ghi, cs = weather["ghi"].where(site), weather["ghi_clearsky"]
    kmax = int(CLOCK_MAX_LAG / step)
    best = max(range(-kmax, kmax + 1), key=lambda k: np.nan_to_num(ghi.shift(k).corr(cs), nan=-1.0))
    return float(-best * step.total_seconds() / 60)
