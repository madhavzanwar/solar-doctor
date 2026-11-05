"""weather router: SolarPulse /weather/{plant_id}/current|forecast.

``source`` is "weatherapi.com" for real data and "mock" (synthetic, condition text marked
"(Simulated)") when no SOLARDOCTOR_WEATHER_API_KEY is configured.
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from solardoctor.physics import plant_service, weather_service
from solardoctor.physics.deps import get_db

router = APIRouter(prefix="/weather", tags=["Weather"])


def _point_to_dict(pt: weather_service.WeatherPoint) -> Dict[str, Any]:
    return {
        "timestamp": pt.timestamp.isoformat(),
        "temperature_c": round(pt.temperature_c, 2),
        "humidity_pct": round(pt.humidity_pct, 1),
        "wind_speed_kph": round(pt.wind_speed_kph, 1),
        "cloud_cover_pct": round(pt.cloud_cover_pct, 1),
        "uv_index": round(pt.uv_index, 1),
        "irradiance_w_m2": round(pt.irradiance_w_m2, 1),
        "condition": pt.condition_text,
        "is_day": pt.is_day,
    }


def _weather_data_to_dict(wd: weather_service.WeatherData, include_hourly: bool = False) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "latitude": wd.latitude, "longitude": wd.longitude, "location_name": wd.location_name,
        "timezone_id": wd.timezone_id, "fetched_at": wd.fetched_at.isoformat(), "source": wd.source,
        "current": _point_to_dict(wd.current),
    }
    if include_hourly:
        payload["hourly_forecast"] = [_point_to_dict(p) for p in wd.hourly_forecast]
    return payload


@router.get("/{plant_id}/current", summary="Current weather conditions at a plant location")
def get_current_weather(plant_id: int, db: Session = Depends(get_db)) -> Dict[str, Any]:
    plant = plant_service.get_plant(db, plant_id)
    return _weather_data_to_dict(weather_service.get_current_weather(plant.lat, plant.lon, db=db))


@router.get("/{plant_id}/forecast", summary="Multi-day hourly weather forecast at a plant location")
def get_forecast_weather(plant_id: int, days: int = Query(default=3, ge=1, le=3, description="Forecast days (1-3)"),
                         db: Session = Depends(get_db)) -> Dict[str, Any]:
    plant = plant_service.get_plant(db, plant_id)
    return _weather_data_to_dict(
        weather_service.get_forecast_weather(plant.lat, plant.lon, days=days, db=db), include_hourly=True)
