"""Weather / irradiance provider chain for the deficit detector.

Per row, in priority order: site sensor (telemetry) -> NASA POWER hourly (past) -> Open-Meteo hourly
forecast (next 3 days) -> pvlib Ineichen clear-sky model. The ``source`` column records which provider
supplied the irradiance of each row. NASA POWER lags real time by days: missing/fill values or a failed
request make those rows fall through to the next provider, never raise.
"""
from __future__ import annotations

import json
from io import StringIO
import logging
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import numpy as np
import pandas as pd
import pvlib

from solardoctor.physics import weather_service as ws

logger = logging.getLogger("solardoctor.physics.irradiance")

SITE, NASA, OPENMETEO, CLEARSKY = "site_sensor", "nasa_power", "openmeteo", "clearsky_model"
MEASURED_SOURCES = (SITE, NASA, OPENMETEO)  # everything except the model
OPENMETEO_URL = "https://api.open-meteo.com/v1/forecast"
OPENMETEO_HORIZON = timedelta(days=3)
_OM_VARS = ["shortwave_radiation", "temperature_2m", "wind_speed_10m",
            "precipitation_probability", "precipitation"]
_DEFAULT_T_AIR, _DEFAULT_WIND = 25.0, 1.0  # only under the clear-sky model, which has no weather


def _utc(times) -> pd.DatetimeIndex:
    idx = pd.DatetimeIndex(times)
    return idx.tz_localize("UTC") if idx.tz is None else idx.tz_convert("UTC")


def fetch_openmeteo_hourly(lat: float, lon: float, db=None, client=None) -> pd.DataFrame:
    """Open-Meteo hourly forecast (3 days) via the official client, cached 30 min in weather_cache."""
    if db is not None and (hit := ws._cache_get(db, lat, lon, "openmeteo")):
        df = pd.read_json(StringIO(hit), orient="split")
        df.index = pd.DatetimeIndex(df.index).tz_localize("UTC") if df.index.tz is None else df.index
        return df
    if client is None:
        import openmeteo_requests
        client = openmeteo_requests.Client()
    ws.harden_http_logging()
    resp = client.weather_api(OPENMETEO_URL, params={
        "latitude": lat, "longitude": lon, "hourly": _OM_VARS, "forecast_days": 3,
        "wind_speed_unit": "ms", "timezone": "GMT"})[0]
    h = resp.Hourly()
    idx = pd.date_range(pd.to_datetime(h.Time(), unit="s", utc=True), pd.to_datetime(h.TimeEnd(), unit="s", utc=True),
                        freq=pd.Timedelta(seconds=h.Interval()), inclusive="left")
    df = pd.DataFrame({n: h.Variables(i).ValuesAsNumpy() for i, n in enumerate(_OM_VARS)}, index=idx)
    if db is not None:
        ws._cache_put(db, lat, lon, "openmeteo", "openmeteo", df.to_json(orient="split", date_format="iso"))
    return df


def _from_hourly(hourly: pd.DataFrame, centre_offset: pd.Timedelta, times: pd.DatetimeIndex,
                 ghi_col: str, cols: dict[str, str], cs_ghi: pd.Series, location) -> pd.DataFrame:
    """Hourly means -> ``times``. GHI via the clear-sky index (so the diurnal shape stays right),
    other columns linearly; nothing is extrapolated or interpolated across a missing hour."""
    hourly = hourly.copy()
    hourly.index = hourly.index + centre_offset
    out = pd.DataFrame(index=times, columns=["ghi", *cols], dtype=float)
    if ghi_col in hourly:
        cs_h = location.get_clearsky(hourly.index, model="ineichen")["ghi"]
        hourly["k"] = hourly[ghi_col] / cs_h.clip(lower=20.0)
    for out_col, in_col in {**cols, "ghi": "k"}.items():
        if in_col not in hourly:
            continue
        s = hourly[in_col]
        grid = s.index.union(times)
        v = s.reindex(grid).interpolate("time", limit_area="inside").reindex(times)
        for c in s.index[s.isna()]:  # gap hour: its neighbours' interpolation spans it
            v[(times > c - pd.Timedelta(hours=1)) & (times < c + pd.Timedelta(hours=1))] = np.nan
        out[out_col] = v * cs_ghi if in_col == "k" else v
    return out


def resolve_weather(plant, times, telemetry: Optional[pd.DataFrame] = None, db=None, now: Optional[datetime] = None,
                    nasa_fetch: Callable = ws.fetch_nasa_power_hourly,
                    openmeteo_fetch: Callable = fetch_openmeteo_hourly) -> pd.DataFrame:
    """Weather for ``plant`` at UTC ``times``: ghi, poa (NaN unless a site POA sensor reports),
    temp_air, wind_speed, precip_mm (mm in the containing hour), ghi_clearsky, source.

    ``telemetry`` is indexed by UTC time with optional columns poa_wm2, ghi_wm2, t_amb, wind_ms.
    """
    idx = _utc(times)
    now = pd.Timestamp(now or datetime.now(timezone.utc))
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    loc = pvlib.location.Location(plant.lat, plant.lon, altitude=plant.altitude_m or 0.0)
    cs = loc.get_clearsky(idx, model="ineichen")["ghi"]

    site = pd.DataFrame(index=idx, columns=["ghi_wm2", "poa_wm2", "t_amb", "wind_ms"], dtype=float)
    if telemetry is not None and len(telemetry):
        t = telemetry[[c for c in site.columns if c in telemetry]]
        site.update(t.groupby(t.index).mean().reindex(idx))
    nan = pd.Series(np.nan, index=idx)
    ghi, temp, wind, precip = site["ghi_wm2"].copy(), site["t_amb"].copy(), site["wind_ms"].copy(), nan.copy()
    source = pd.Series(np.where(ghi.notna(), SITE, ""), index=idx, dtype=object)

    def absorb(frame: pd.DataFrame, name: str) -> None:
        nonlocal ghi, temp, wind, precip
        fill = source == ""
        got = frame["ghi"].notna() & fill
        source[got] = name
        ghi = ghi.where(~got, frame["ghi"])
        temp, wind = temp.fillna(frame["temp_air"]), wind.fillna(frame["wind_speed"])
        precip = precip.fillna(frame["precip_mm"])

    past = idx <= now
    if past.any():
        try:
            # a day of margin each side so rows before the first / after the last hourly centre are covered
            lo, hi = idx[past].min() - pd.Timedelta(days=1), min(idx[past].max() + pd.Timedelta(days=1), now)
            hourly = nasa_fetch(plant.lat, plant.lon, lo.to_pydatetime(), hi.to_pydatetime(), db=db)
            absorb(_from_hourly(hourly, pd.Timedelta(minutes=30), idx, "ghi", {
                "temp_air": "temp_air", "wind_speed": "wind_speed", "precip_mm": "precip_mm"}, cs, loc), NASA)
        except Exception as exc:  # latency / outage: fall through to the next provider
            logger.warning("NASA POWER unavailable (%s: %s); falling back", type(exc).__name__, exc)
    future = (idx > now) & (idx <= now + OPENMETEO_HORIZON)
    if future.any():
        try:
            hourly = openmeteo_fetch(plant.lat, plant.lon, db=db)
            # Open-Meteo radiation is the mean of the preceding hour
            absorb(_from_hourly(hourly.rename(columns={"shortwave_radiation": "ghi"}), -pd.Timedelta(minutes=30), idx,
                                "ghi", {"temp_air": "temperature_2m", "wind_speed": "wind_speed_10m",
                                        "precip_mm": "precipitation"}, cs, loc), OPENMETEO)
        except Exception as exc:
            logger.warning("Open-Meteo unavailable (%s: %s); falling back", type(exc).__name__, exc)
    rest = source == ""
    source[rest] = CLEARSKY
    ghi = ghi.where(~rest, cs)
    return pd.DataFrame({
        "ghi": ghi, "poa": site["poa_wm2"], "temp_air": temp.fillna(_DEFAULT_T_AIR),
        "wind_speed": wind.fillna(_DEFAULT_WIND), "precip_mm": precip, "ghi_clearsky": cs, "source": source,
    })
