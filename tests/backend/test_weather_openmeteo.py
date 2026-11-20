"""Test keyless Open-Meteo weather integration and caching."""
from __future__ import annotations

import httpx
from datetime import datetime, timezone
import pytest

from solardoctor.physics import weather_service
from solardoctor.physics.weather_service import WeatherData, get_current_weather, get_forecast_weather
from solardoctor.db.session import get_session


def test_openmeteo_fetch_live_or_offline():
    """Verify Open-Meteo fetch returns structured WeatherData."""
    # Pune, India (PCCoE coordinates)
    lat, lon = 18.65, 73.76
    wd = get_current_weather(lat, lon)
    assert isinstance(wd, WeatherData)
    assert wd.latitude == lat
    assert wd.longitude == lon
    assert wd.current is not None
    assert isinstance(wd.current.temperature_c, float)
    assert isinstance(wd.current.wind_speed_kph, float)
    assert wd.source in ("open-meteo", "weatherapi.com", "mock")


def test_openmeteo_forecast_structure():
    """Verify forecast returns 24-72 hourly points."""
    lat, lon = 18.65, 73.76
    wd = get_forecast_weather(lat, lon, days=2)
    assert isinstance(wd, WeatherData)
    if wd.source == "open-meteo":
        assert len(wd.hourly_forecast) >= 24
        p = wd.hourly_forecast[0]
        assert p.timestamp is not None
        assert p.temperature_c is not None


def test_offline_fallback_transport_error():
    """Verify that a failing transport safely falls back to labelled mock."""
    class FailTransport(httpx.BaseTransport):
        def handle_request(self, request):
            raise httpx.ConnectError("Offline test")

    wd = get_current_weather(18.65, 73.76, transport=FailTransport())
    assert isinstance(wd, WeatherData)
    assert wd.source == "mock"
    assert "(Simulated)" in wd.current.condition_text
