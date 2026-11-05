"""Irradiance input for the seed: NASA POWER hourly (cached), or a labelled synthetic fallback.

NASA POWER hourly values are hour averages.  To get 15-minute data without inventing structure
we interpolate the *clear-sky index* (NASA GHI / pvlib Ineichen clear-sky GHI) in time and
multiply it back by the clear-sky GHI at each 15-minute step.  Temperature and wind are
linearly interpolated.

If the network is unavailable (or NASA returns too many gaps) the fallback is pvlib clear-sky
multiplied by a **synthetic cloud model** (seeded AR(1) daily clearness + intra-day noise).  Rows
generated that way carry ``irradiance_source == "SYNTHETIC_CLEARSKY"``; it is never measured data.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np
import pandas as pd

from solardoctor.physics import solar

log = logging.getLogger("solardoctor.seed")

SRC_NASA = "NASA_POWER"
SRC_SYNTH = "SYNTHETIC_CLEARSKY"

Fetcher = Callable[[float, float, pd.Timestamp, pd.Timestamp], pd.DataFrame]


@dataclass
class Irradiance:
    """15-min series on the window index (UTC): ghi (W/m2), temp_air (C), wind_speed (m/s)."""
    frame: pd.DataFrame
    source: str
    note: str


def fetch_nasa_power(lat: float, lon: float, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Hourly UTC frame with columns ghi, temp_air, wind_speed from NASA POWER (via pvlib)."""
    import pvlib

    data, _meta = pvlib.iotools.get_nasa_power(
        lat, lon, start, end, ["ghi", "temp_air", "wind_speed"], map_variables=True)
    return data[["ghi", "temp_air", "wind_speed"]]


def cached_fetch(fetcher: Fetcher, cache_dir: Path, tag: str, lat: float, lon: float,
                 start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Read ``data/cache/nasa_power_<tag>_<start>_<end>.csv`` or fetch and write it."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"nasa_power_{tag}_{start:%Y%m%d}_{end:%Y%m%d}.csv"
    if path.exists():
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        df.index = pd.DatetimeIndex(df.index).tz_convert("UTC") if df.index.tz else df.index.tz_localize("UTC")
        return df
    df = fetcher(lat, lon, start, end)
    df = df.copy()
    df.index = pd.DatetimeIndex(df.index).tz_convert("UTC") if df.index.tz else df.index.tz_localize("UTC")
    df.to_csv(path)
    return df


def discover_window(fetcher: Fetcher, cache_dir: Path, probe_lat: float, probe_lon: float,
                    days: int = 30, today: Optional[pd.Timestamp] = None) -> tuple[pd.Timestamp, str]:
    """Return (window start midnight UTC, note).

    NASA POWER GHI lags real time, so we probe the last ~100 days and end the window on the most
    recent day with a complete (>= 23 h) GHI record.  On any failure the window ends yesterday
    and the caller will use the synthetic fallback.
    """
    today = (today or pd.Timestamp.now(tz="UTC")).normalize()
    try:
        probe = cached_fetch(fetcher, cache_dir, f"probe{today:%Y%m%d}", probe_lat, probe_lon,
                             today - pd.Timedelta(days=100), today - pd.Timedelta(days=1))
        per_day = probe["ghi"].notna().groupby(probe.index.normalize()).sum()
        full = per_day[per_day >= 23]
        if len(full) < days:
            raise RuntimeError("NASA POWER returned fewer than %d complete days" % days)
        last = full.index.max()
        return (last - pd.Timedelta(days=days - 1)).normalize(), f"window ends {last:%Y-%m-%d} (latest complete NASA POWER GHI day)"
    except Exception as exc:  # network down, API change, ...
        log.warning("NASA POWER probe failed (%s); using a synthetic-irradiance window", exc)
        return today - pd.Timedelta(days=days), f"NASA POWER unavailable ({type(exc).__name__}); window ends yesterday"


def _clearsky(lat, lon, alt, times) -> pd.DataFrame:
    return solar.clearsky_irradiance(lat, lon, times, alt)


def from_hourly(hourly: pd.DataFrame, lat: float, lon: float, alt: float,
                times: pd.DatetimeIndex) -> pd.DataFrame:
    """Resample NASA hourly (hour-average, stamped at hour start) to ``times`` via clear-sky index."""
    center = hourly.index + pd.Timedelta(minutes=30)
    cs_h = _clearsky(lat, lon, alt, center)["ghi"].to_numpy()
    k_h = pd.Series(np.where(cs_h > 25.0, hourly["ghi"].to_numpy() / np.maximum(cs_h, 1e-9), np.nan), index=center)
    k_h = k_h.clip(0.0, 1.15)
    union = k_h.index.union(times)
    k = k_h.reindex(union).interpolate("time", limit_area=None).ffill(limit=8).bfill(limit=8).reindex(times)
    cs = _clearsky(lat, lon, alt, times)["ghi"]
    out = pd.DataFrame(index=times)
    out["ghi"] = (k.fillna(0.0) * cs).clip(lower=0.0)
    for col in ("temp_air", "wind_speed"):
        s = hourly[col].copy()
        s.index = center
        out[col] = s.reindex(s.index.union(times)).interpolate("time").ffill().bfill().reindex(times)
    return out


def synthetic(lat: float, lon: float, alt: float, times: pd.DatetimeIndex, seed: int) -> pd.DataFrame:
    """Clear-sky x synthetic cloud model.  SYNTHETIC, NOT MEASURED."""
    rng = np.random.default_rng(seed)
    cs = _clearsky(lat, lon, alt, times)["ghi"]
    days = times.normalize()
    ndays = len(days.unique())
    x = np.zeros(ndays)
    for d in range(1, ndays):
        x[d] = 0.6 * x[d - 1] + rng.normal(0.0, 0.12)
    kday = np.clip(0.92 + x, 0.35, 1.0)
    day_idx = np.searchsorted(days.unique(), days)
    noise = np.zeros(len(times))
    for i in range(1, len(times)):
        noise[i] = 0.9 * noise[i - 1] + rng.normal(0.0, 0.03)
    k = np.clip(kday[day_idx] * (1.0 + noise), 0.05, 1.05)
    out = pd.DataFrame(index=times)
    out["ghi"] = cs * k
    local_hour = (times.tz_convert("Asia/Kolkata").hour + times.tz_convert("Asia/Kolkata").minute / 60.0).to_numpy()
    out["temp_air"] = 27.0 + 7.0 * np.cos(2 * np.pi * (local_hour - 15.0) / 24.0) - 4.0 * (1.0 - k)
    out["wind_speed"] = 2.5
    return out


def apply_cloudy_spell(frame: pd.DataFrame, start: pd.Timestamp, days: tuple[int, ...], factor: float) -> pd.DataFrame:
    """Scale GHI on the given window days (injected, labelled cloudy spell)."""
    out = frame.copy()
    day_no = ((out.index.normalize() - start.normalize()) / pd.Timedelta(days=1)).astype(int)
    mask = np.isin(np.asarray(day_no), list(days))
    out.loc[mask, "ghi"] = out.loc[mask, "ghi"] * factor
    return out


def get_irradiance(lat: float, lon: float, alt: float, tag: str, times: pd.DatetimeIndex, seed: int,
                   fetcher: Fetcher, cache_dir: Path, allow_network: bool = True) -> Irradiance:
    """NASA POWER if possible, else the labelled synthetic fallback."""
    start, end = times[0].normalize(), times[-1].normalize()
    if allow_network:
        try:
            hourly = cached_fetch(fetcher, cache_dir, tag, lat, lon, start, end + pd.Timedelta(days=0))
            win = hourly.loc[(hourly.index >= start) & (hourly.index < end + pd.Timedelta(days=1))]
            if win["ghi"].isna().mean() > 0.05 or len(win) < 24 * 25:
                raise RuntimeError("NASA POWER GHI has too many gaps (%.0f %% NaN)" % (100 * win["ghi"].isna().mean()))
            frame = from_hourly(win.interpolate("time", limit=3), lat, lon, alt, times)
            return Irradiance(frame, SRC_NASA, "NASA POWER hourly ALLSKY_SFC_SW_DWN/T2M/WS10M, clear-sky-index interpolated to 15 min")
        except Exception as exc:
            log.warning("NASA POWER unavailable for %s (%s): using SYNTHETIC clear-sky x cloud model", tag, exc)
            reason = f"NASA POWER unavailable ({type(exc).__name__}: {str(exc)[:120]})"
    else:
        reason = "network disabled (--offline)"
    return Irradiance(synthetic(lat, lon, alt, times, seed), SRC_SYNTH,
                      f"SYNTHETIC clear-sky x AR(1) cloud model, not measured data; {reason}")
