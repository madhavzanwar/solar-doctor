# Adapted from SolarPulseAI app/services/weather_service.py
# (https://github.com/anugrahpatil-creator/SolarPulseAI), MIT License,
# Copyright (c) 2026 anugrahpatil-creator. See THIRD_PARTY_NOTICES.md.
# Modified for SolarDoctor: sync httpx, env-based key, DB cache (weather_cache), NASA POWER hourly fetch.
"""
app/services/weather_service.py

WeatherAPI.com integration service.

Responsibilities
----------------
- Fetch **current** weather conditions (irradiance proxy, temperature, humidity,
  wind speed, cloud cover) for a given lat/lon.
- Fetch a **forecast** horizon (up to 3 days) from WeatherAPI.com.
- Expose a ``WeatherData`` dataclass that the forecast pipeline consumes.
- Fall back gracefully to synthetic mock data when ``WEATHER_API_KEY`` is not
  configured, so local development works out of the box.

WeatherAPI.com free-tier endpoints used
----------------------------------------
  Current : GET /v1/current.json?key=...&q={lat},{lon}&aqi=no
  Forecast: GET /v1/forecast.json?key=...&q={lat},{lon}&days={days}&aqi=no

Irradiance estimation
---------------------
WeatherAPI does not expose a direct GHI field on its free tier.  We derive a
best-effort estimate from:
  GHI_est = max_solar_irradiance * (1 - cloud_cover / 100) * cos_correction
where ``cos_correction`` uses the current UV index as a daylight proxy.
For precise physics the forecast pipeline still passes this through pvlib or its
own physics layer -- the weather data just replaces the pvlib clear-sky baseline.
"""

from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List

import httpx

logger = logging.getLogger("solardoctor.physics.weather")

# -- Constants ----------------------------------------------------------------

WEATHERAPI_BASE = "https://api.weatherapi.com/v1"
MAX_SOLAR_IRRADIANCE_W_M2 = 1000.0   # approximate peak clear-sky GHI
REQUEST_TIMEOUT_S = 10.0


# -- Data models --------------------------------------------------------------


@dataclass
class WeatherPoint:
    """A single weather observation or forecast hour."""

    timestamp: datetime
    temperature_c: float
    humidity_pct: float
    wind_speed_kph: float
    cloud_cover_pct: float
    uv_index: float
    condition_text: str
    is_day: bool = True
    # Derived -- populated by __post_init__
    irradiance_w_m2: float = 0.0

    def __post_init__(self) -> None:
        """Derive irradiance estimate if not supplied explicitly."""
        if self.irradiance_w_m2 == 0.0:
            self.irradiance_w_m2 = _estimate_irradiance(
                cloud_cover_pct=self.cloud_cover_pct,
                uv_index=self.uv_index,
                is_day=self.is_day,
            )


@dataclass
class WeatherData:
    """Full weather payload returned by the service."""

    latitude: float
    longitude: float
    location_name: str
    timezone_id: str
    current: WeatherPoint
    hourly_forecast: List[WeatherPoint] = field(default_factory=list)
    fetched_at: datetime = field(default_factory=lambda: datetime.now(tz=timezone.utc))
    source: str = "weatherapi.com"   # "mock" when API key is absent


# -- Irradiance estimation helper ---------------------------------------------


def _estimate_irradiance(
    cloud_cover_pct: float,
    uv_index: float,
    is_day: bool,
) -> float:
    """
    Derive a rough GHI estimate from cloud cover and UV index.

    This is intentionally simple -- the physics layer in forecast_service will
    further refine the value using pvlib geometry if available.
    """
    if not is_day:
        return 0.0

    # UV index 0-11+; use as a proxy for solar elevation (capped at 1)
    uv_factor = min(uv_index / 8.0, 1.0)

    clear_sky_ghi = MAX_SOLAR_IRRADIANCE_W_M2 * uv_factor
    cloud_factor = 1.0 - (cloud_cover_pct / 100.0) * 0.75  # clouds reduce but not eliminate
    return max(0.0, clear_sky_ghi * cloud_factor)


# -- Parsers ------------------------------------------------------------------


def _parse_current(raw: dict) -> WeatherPoint:
    """Parse the ``current`` block from WeatherAPI response."""
    cur = raw["current"]
    return WeatherPoint(
        timestamp=datetime.now(tz=timezone.utc),
        temperature_c=float(cur.get("temp_c", 25.0)),
        humidity_pct=float(cur.get("humidity", 50.0)),
        wind_speed_kph=float(cur.get("wind_kph", 0.0)),
        cloud_cover_pct=float(cur.get("cloud", 0.0)),
        uv_index=float(cur.get("uv", 4.0)),
        condition_text=cur.get("condition", {}).get("text", "Unknown"),
        is_day=bool(cur.get("is_day", 1)),
    )


def _parse_hourly_forecast(raw: dict) -> List[WeatherPoint]:
    """Parse hourly blocks from a WeatherAPI forecast response."""
    points: List[WeatherPoint] = []
    for day_block in raw.get("forecast", {}).get("forecastday", []):
        for hour in day_block.get("hour", []):
            try:
                ts = datetime.fromtimestamp(hour["time_epoch"], tz=timezone.utc)
                points.append(
                    WeatherPoint(
                        timestamp=ts,
                        temperature_c=float(hour.get("temp_c", 25.0)),
                        humidity_pct=float(hour.get("humidity", 50.0)),
                        wind_speed_kph=float(hour.get("wind_kph", 0.0)),
                        cloud_cover_pct=float(hour.get("cloud", 0.0)),
                        uv_index=float(hour.get("uv", 0.0)),
                        condition_text=hour.get("condition", {}).get("text", "Unknown"),
                        is_day=bool(hour.get("is_day", 1)),
                    )
                )
            except Exception as exc:
                logger.debug(f"Skipping malformed hourly entry: {exc}")
    return points


# -- Mock fallback ------------------------------------------------------------


def _mock_weather_data(lat: float, lon: float) -> WeatherData:
    """
    Return physics-informed synthetic weather data when WeatherAPI is unavailable.

    Differentiates conditions based on geographic coordinates:
    - Longitude determines solar time offset (local daylight cycle)
    - Latitude & region model climate (arid desert vs. coastal humid vs. plateau)
    """
    now = datetime.now(tz=timezone.utc)

    # Local solar time derived from longitude (15 deg longitude = 1 hour)
    solar_offset_hours = lon / 15.0
    local_solar_hour = (now.hour + (now.minute / 60.0) + solar_offset_hours) % 24.0

    is_day = 6.0 <= local_solar_hour <= 18.0
    if is_day:
        sun_fraction = math.sin(math.pi * (local_solar_hour - 6.0) / 12.0)
        uv = max(0.0, round(8.0 * sun_fraction, 1))
    else:
        sun_fraction = 0.0
        uv = 0.0

    # Regional climate profiling from coordinates
    # Arid / Desert northwest (e.g. Rajasthan / Gujarat)
    if lat >= 23.0 and lon <= 74.0:
        base_temp = 31.0
        base_humidity = 20.0
        base_cloud = 8.0
        base_wind = 14.0
        cond_text = "Clear / Sunny (Simulated)" if is_day else "Clear Night (Simulated)"
        loc_desc = f"Desert Sector ({lat:.2f}N, {lon:.2f}E)"
    # Southern / Coastal humid (e.g. Tamil Nadu, Kerala, Andhra coast)
    elif lat <= 15.0:
        base_temp = 28.5
        base_humidity = 68.0
        base_cloud = 42.0
        base_wind = 18.0
        cond_text = "Partly Cloudy (Simulated)" if is_day else "Passing Clouds (Simulated)"
        loc_desc = f"Southern Coast ({lat:.2f}N, {lon:.2f}E)"
    # Central / Deccan Plateau (e.g. MP, Maharashtra, Karnataka interior)
    else:
        base_temp = 26.5
        base_humidity = 50.0
        base_cloud = 22.0
        base_wind = 12.0
        cond_text = "Fair / Clear (Simulated)" if is_day else "Clear (Simulated)"
        loc_desc = f"Plateau Array ({lat:.2f}N, {lon:.2f}E)"

    # Diurnal temperature swing
    temp_swing = 6.0 * (sun_fraction if is_day else -0.3)
    curr_temp = round(base_temp + temp_swing, 1)

    current = WeatherPoint(
        timestamp=now,
        temperature_c=curr_temp,
        humidity_pct=round(base_humidity - 5.0 * sun_fraction, 1),
        wind_speed_kph=round(base_wind + 2.0 * math.sin(local_solar_hour), 1),
        cloud_cover_pct=round(base_cloud, 1),
        uv_index=uv,
        condition_text=cond_text,
        is_day=is_day,
    )

    hourly: List[WeatherPoint] = []
    for delta_h in range(72):
        fh = (local_solar_hour + delta_h) % 24.0
        fday = 6.0 <= fh <= 18.0
        fsun = math.sin(math.pi * (fh - 6.0) / 12.0) if fday else 0.0
        fuv = max(0.0, round(8.0 * fsun, 1)) if fday else 0.0
        ftemp = round(base_temp + 6.0 * (fsun if fday else -0.3), 1)

        hourly.append(
            WeatherPoint(
                timestamp=now + timedelta(hours=delta_h),
                temperature_c=ftemp,
                humidity_pct=round(base_humidity - 5.0 * fsun, 1),
                wind_speed_kph=round(base_wind, 1),
                cloud_cover_pct=round(base_cloud, 1),
                uv_index=fuv,
                condition_text=cond_text,
                is_day=fday,
            )
        )

    return WeatherData(
        latitude=lat,
        longitude=lon,
        location_name=loc_desc,
        timezone_id="Asia/Kolkata",
        current=current,
        hourly_forecast=hourly,
        source="mock",
    )


# -- API client (sync) ---------------------------------------------------------


def _api_key() -> str:
    return os.getenv("SOLARDOCTOR_WEATHER_API_KEY") or os.getenv("WEATHER_API_KEY", "")


class WeatherAPIClient:
    """Sync HTTP client for WeatherAPI.com."""

    def __init__(self, api_key: str, base_url: str = WEATHERAPI_BASE,
                 transport: httpx.BaseTransport | None = None) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._transport = transport

    def get_forecast(self, lat: float, lon: float, days: int = 1) -> dict:
        days = max(1, min(days, 3))  # free tier: max 3 days
        params = {"key": self._api_key, "q": f"{lat},{lon}", "days": days, "aqi": "no", "alerts": "no"}
        with httpx.Client(timeout=REQUEST_TIMEOUT_S, transport=self._transport) as client:
            resp = client.get(f"{self._base_url}/forecast.json", params=params)
            resp.raise_for_status()
            return resp.json()


def _fetch(lat: float, lon: float, days: int, transport=None) -> WeatherData:
    """WeatherAPI.com when a key is configured, otherwise (or on any failure) the labelled mock."""
    key = _api_key()
    if not key:
        return _mock_weather_data(lat, lon)
    try:
        raw = WeatherAPIClient(key, transport=transport).get_forecast(lat, lon, days=days)
        location = raw.get("location", {})
        return WeatherData(
            latitude=lat, longitude=lon,
            location_name=location.get("name", "Unknown"),
            timezone_id=location.get("tz_id", "UTC"),
            current=_parse_current(raw),
            hourly_forecast=_parse_hourly_forecast(raw),
            source="weatherapi.com",
        )
    except Exception as exc:  # HTTP errors, timeouts, malformed payloads
        logger.warning("WeatherAPI request failed for (%s, %s): %s; falling back to mock.", lat, lon, exc)
        return _mock_weather_data(lat, lon)


# -- Cache (weather_cache table) ----------------------------------------------

CACHE_TTL_MINUTES = 30


def _wp_to_dict(p: WeatherPoint) -> dict:
    return {
        "timestamp": p.timestamp.isoformat(), "temperature_c": p.temperature_c,
        "humidity_pct": p.humidity_pct, "wind_speed_kph": p.wind_speed_kph,
        "cloud_cover_pct": p.cloud_cover_pct, "uv_index": p.uv_index,
        "condition_text": p.condition_text, "is_day": p.is_day, "irradiance_w_m2": p.irradiance_w_m2,
    }


def _wp_from_dict(d: dict) -> WeatherPoint:
    return WeatherPoint(
        timestamp=datetime.fromisoformat(d["timestamp"]), temperature_c=d["temperature_c"],
        humidity_pct=d["humidity_pct"], wind_speed_kph=d["wind_speed_kph"],
        cloud_cover_pct=d["cloud_cover_pct"], uv_index=d["uv_index"],
        condition_text=d["condition_text"], is_day=d["is_day"], irradiance_w_m2=d["irradiance_w_m2"],
    )


def _wd_to_json(wd: WeatherData) -> str:
    return json.dumps({
        "latitude": wd.latitude, "longitude": wd.longitude, "location_name": wd.location_name,
        "timezone_id": wd.timezone_id, "source": wd.source, "fetched_at": wd.fetched_at.isoformat(),
        "current": _wp_to_dict(wd.current), "hourly_forecast": [_wp_to_dict(p) for p in wd.hourly_forecast],
    })


def _wd_from_json(raw: str) -> WeatherData:
    d = json.loads(raw)
    return WeatherData(
        latitude=d["latitude"], longitude=d["longitude"], location_name=d["location_name"],
        timezone_id=d["timezone_id"], current=_wp_from_dict(d["current"]),
        hourly_forecast=[_wp_from_dict(p) for p in d["hourly_forecast"]],
        fetched_at=datetime.fromisoformat(d["fetched_at"]), source=d["source"],
    )


def _cache_get(db, lat: float, lon: float, kind: str) -> str | None:
    from sqlalchemy import select
    from solardoctor.physics.models import WeatherCache
    row = db.execute(select(WeatherCache).where(
        WeatherCache.lat_key == round(lat, 1), WeatherCache.lon_key == round(lon, 1),
        WeatherCache.kind == kind)).scalar_one_or_none()
    if row is None or row.expires_at <= datetime.now(tz=timezone.utc):
        return None
    return row.payload_json


def _cache_put(db, lat: float, lon: float, kind: str, source: str, payload: str,
               ttl: timedelta = timedelta(minutes=CACHE_TTL_MINUTES)) -> None:
    from sqlalchemy import select
    from solardoctor.physics.models import WeatherCache
    now = datetime.now(tz=timezone.utc)
    row = db.execute(select(WeatherCache).where(
        WeatherCache.lat_key == round(lat, 1), WeatherCache.lon_key == round(lon, 1),
        WeatherCache.kind == kind)).scalar_one_or_none()
    if row is None:
        row = WeatherCache(lat_key=round(lat, 1), lon_key=round(lon, 1), kind=kind)
        db.add(row)
    row.source, row.payload_json, row.fetched_at, row.expires_at = source, payload, now, now + ttl
    db.commit()


# -- Public service functions -------------------------------------------------


def get_current_weather(lat: float, lon: float, db=None, transport=None) -> WeatherData:
    """Current weather. Mock data (labelled source="mock") when no API key is configured.

    The mock is synthetic: it is NOT measured weather and must never be shown as such.
    """
    if db is not None and _api_key():
        cached = _cache_get(db, lat, lon, "current")
        if cached:
            return _wd_from_json(cached)
    wd = _fetch(lat, lon, 1, transport)
    if db is not None and wd.source != "mock":
        _cache_put(db, lat, lon, "current", wd.source, _wd_to_json(wd))
    return wd


def get_forecast_weather(lat: float, lon: float, days: int = 3, db=None, transport=None) -> WeatherData:
    """Hourly forecast (<= 3 days). Mock when no key is configured (see get_current_weather)."""
    if db is not None and _api_key():
        cached = _cache_get(db, lat, lon, f"forecast{days}")
        if cached:
            return _wd_from_json(cached)
    wd = _fetch(lat, lon, days, transport)
    if db is not None and wd.source != "mock":
        _cache_put(db, lat, lon, f"forecast{days}", wd.source, _wd_to_json(wd))
    return wd


# -- NASA POWER (real hourly irradiance, no key required) ----------------------

NASA_POWER_URL = "https://power.larc.nasa.gov/api/temporal/hourly/point"
_NASA_FILL = -999.0


def parse_nasa_power_hourly(payload: dict):
    """Parse a NASA POWER hourly JSON payload into a UTC-indexed DataFrame.

    Columns: ghi (ALLSKY_SFC_SW_DWN, W/m2), temp_air (T2M, C), wind_speed (WS10M, m/s).
    Fill values (-999) become NaN.
    """
    import pandas as pd
    params = payload["properties"]["parameter"]
    cols = {"ghi": "ALLSKY_SFC_SW_DWN", "temp_air": "T2M", "wind_speed": "WS10M"}
    data = {}
    for out, name in cols.items():
        if name in params:
            data[out] = pd.Series(params[name], dtype="float64")
    df = pd.DataFrame(data)
    df.index = pd.to_datetime(df.index, format="%Y%m%d%H", utc=True)
    return df.sort_index().where(df != _NASA_FILL)


def fetch_nasa_power_hourly(lat: float, lon: float, start: datetime, end: datetime,
                            db=None, transport=None):
    """NASA POWER hourly irradiance (cached in weather_cache when ``db`` is given)."""
    params = {
        "parameters": "ALLSKY_SFC_SW_DWN,T2M,WS10M", "community": "RE", "format": "JSON",
        "latitude": round(lat, 4), "longitude": round(lon, 4), "time-standard": "UTC",
        "start": start.strftime("%Y%m%d"), "end": end.strftime("%Y%m%d"),
    }
    kind = f"nasa_power:{params['start']}-{params['end']}"
    if db is not None:
        cached = _cache_get(db, lat, lon, kind)
        if cached:
            return parse_nasa_power_hourly(json.loads(cached))
    with httpx.Client(timeout=60.0, transport=transport) as client:
        resp = client.get(NASA_POWER_URL, params=params)
        resp.raise_for_status()
        payload = resp.json()
    if db is not None:
        _cache_put(db, lat, lon, kind, "nasa_power", json.dumps(payload), ttl=timedelta(days=30))
    return parse_nasa_power_hourly(payload)
