"""Physical sanity tests for the pvlib baseline and ported post-processing. No network."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import numpy as np
import pandas as pd
import pytest

from solardoctor.physics import solar

PUNE = SimpleNamespace(id=1, name="Pune", lat=18.5204, lon=73.8567, altitude_m=560.0, tilt=18.0,
                       azimuth=180.0, dc_kw=120.0, ac_kw=100.0, temp_coeff=-0.004)


def test_clear_sky_ghi_pune_march_solar_noon():
    # Equinox solar noon in Pune ~ 12:30 IST (73.86 E vs the 82.5 E IST meridian).
    t = pd.date_range("2026-03-20 11:30", "2026-03-20 13:30", freq="10min", tz="Asia/Kolkata")
    cs = solar.clearsky_irradiance(PUNE.lat, PUNE.lon, t, PUNE.altitude_m)
    peak = float(cs["ghi"].max())
    assert 900.0 <= peak <= 1100.0, peak


def test_expected_power_zero_at_night_and_nonnegative():
    t = pd.date_range("2026-03-20 00:00", periods=24 * 4, freq="15min", tz="Asia/Kolkata")
    d = solar.expected_power(PUNE, t)
    night = d["solar_elevation"] <= 0
    assert night.any() and (d.loc[night, "p_dc_kw"] == 0).all() and (d.loc[night, "p_ac_kw"] == 0).all()
    assert (d["p_dc_kw"] >= 0).all() and (d["p_ac_kw"] >= 0).all()
    assert d["p_ac_kw"].max() > 0.5 * PUNE.ac_kw  # a clear March day should reach well into the rating


def test_ac_never_exceeds_rating_over_a_year_even_when_oversized():
    oversized = SimpleNamespace(**{**PUNE.__dict__, "dc_kw": 300.0, "ac_kw": 100.0})
    t = pd.date_range("2026-01-01", periods=365 * 24, freq="h", tz="UTC")
    d = solar.expected_power(oversized, t)
    assert d["p_ac_kw"].max() <= 100.0 + 1e-9
    assert d["p_ac_kw"].max() == pytest.approx(100.0)  # 2.5x DC/AC definitely clips


def test_hot_cells_lower_output_and_soiling_scales_linearly():
    t = pd.DatetimeIndex(["2026-03-20 07:00"], tz="UTC")
    ghi = pd.Series([800.0], index=t)
    cool = solar.expected_power(PUNE, t, ghi=ghi, temp_air=pd.Series([10.0], index=t))["p_dc_kw"].iloc[0]
    hot = solar.expected_power(PUNE, t, ghi=ghi, temp_air=pd.Series([45.0], index=t))["p_dc_kw"].iloc[0]
    assert hot < cool
    soiled = solar.expected_power(PUNE, t, ghi=ghi, temp_air=pd.Series([10.0], index=t), soiling_loss=0.1)["p_dc_kw"].iloc[0]
    assert soiled == pytest.approx(cool * 0.9, rel=1e-9)


def test_measured_ghi_zero_means_zero_power():
    t = pd.DatetimeIndex(["2026-03-20 07:00"], tz="UTC")  # midday sun, but overcast sensor reading 0
    d = solar.expected_power(PUNE, t, ghi=pd.Series([0.0], index=t))
    assert d["p_ac_kw"].iloc[0] == 0.0


def test_clipping_helpers_never_exceed_limit():
    from ml.forecast.postprocessing.clipping import apply_clipping
    from solardoctor.physics.clipping import calculate_clipping
    rng = np.random.RandomState(1)
    g = rng.uniform(0, 5000, 1000)
    assert apply_clipping(g, 800.0).max() <= 800.0
    for dc in (0, 10, 500, 5000):
        r = calculate_clipping(dc, 800.0, 0.96)
        assert 0 <= r.clipped_ac_power_kw <= 800.0


def test_time_since_rain_soiling_grows_dry_and_resets_on_rain():
    from ml.forecast.postprocessing.soiling import calculate_dynamic_soiling
    ts = pd.date_range("2026-01-01", periods=60, freq="1D", tz="UTC")
    rain = np.zeros(60)
    rain[30] = 20.0
    s = calculate_dynamic_soiling(ts, rain, soiling_rate_per_day=0.004).values
    assert np.all(np.diff(s[:30]) >= 0) and s[29] > 0.1
    assert s[30] == 0.0 and s[59] > s[31]
    assert s.max() <= 0.25 + 1e-12  # capped


def test_online_adapter_safety_gates_and_bounds():
    from ml.forecast.models.online_residual_adapter import OnlineResidualAdapter
    a = OnlineResidualAdapter("x")
    assert a.update(50, 100, ghi=5.0) is False          # night/dark
    assert a.update(50, 100, ghi=600, has_active_anomaly=True) is False
    assert a.update(50, 100, ghi=600, is_curtailed=True) is False
    for _ in range(200):
        a.update(1000, 100, ghi=600)                    # absurd outperformance
    assert a.state.scaling_factor <= 1.30 + 1e-9
    out = a.adjust_forecast(np.array([100.0]), np.array([0.0]))
    assert out[0] <= 130.0 + 1e-6


def _weatherapi_transport(calls):
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent))
    from golden_cases import WEATHERAPI_RAW

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json=WEATHERAPI_RAW)
    return httpx.MockTransport(handler)


def test_weatherapi_mocked_transport_and_db_cache(monkeypatch, db_session):
    from solardoctor.physics import weather_service as ws
    monkeypatch.setenv("SOLARDOCTOR_WEATHER_API_KEY", "dummy")
    calls: list[str] = []
    tr = _weatherapi_transport(calls)
    wd = ws.get_current_weather(18.52, 73.86, db=db_session, transport=tr)
    assert wd.source == "weatherapi.com" and wd.location_name == "Pune" and len(calls) == 1
    again = ws.get_current_weather(18.52, 73.86, db=db_session, transport=tr)
    assert len(calls) == 1 and again.current.temperature_c == wd.current.temperature_c  # served from cache
    assert len(again.hourly_forecast) == len(wd.hourly_forecast) == 8


def test_weatherapi_failure_falls_back_to_labelled_mock(monkeypatch):
    from solardoctor.physics import weather_service as ws
    monkeypatch.setenv("SOLARDOCTOR_WEATHER_API_KEY", "dummy")
    boom = httpx.MockTransport(lambda r: httpx.Response(500, text="nope"))
    wd = ws.get_current_weather(18.52, 73.86, transport=boom)
    assert wd.source == "mock" and "Simulated" in wd.current.condition_text


def test_nasa_power_parse_cache_and_no_network(db_session):
    from solardoctor.physics import weather_service as ws
    payload = {"properties": {"parameter": {
        "ALLSKY_SFC_SW_DWN": {"2026031906": 120.5, "2026031907": 310.0, "2026031908": -999.0},
        "T2M": {"2026031906": 22.0, "2026031907": 24.5, "2026031908": 26.0},
        "WS10M": {"2026031906": 1.0, "2026031907": 2.0, "2026031908": 3.0},
    }}}
    calls = []

    def handler(req: httpx.Request):
        calls.append(req.url.params["start"])
        return httpx.Response(200, json=payload)

    tr = httpx.MockTransport(handler)
    start, end = datetime(2026, 3, 19, tzinfo=timezone.utc), datetime(2026, 3, 19, tzinfo=timezone.utc)
    df = ws.fetch_nasa_power_hourly(18.52, 73.86, start, end, db=db_session, transport=tr)
    assert list(df.columns) == ["ghi", "temp_air", "wind_speed"]
    assert df["ghi"].iloc[0] == 120.5 and np.isnan(df["ghi"].iloc[2])  # -999 fill -> NaN
    assert str(df.index.tz) == "UTC" and df.index[0].hour == 6
    ws.fetch_nasa_power_hourly(18.52, 73.86, start, end, db=db_session, transport=tr)
    assert calls == ["20260319"]  # second call served from weather_cache


def test_alert_worker_flags_shortfall_against_pvlib_baseline(db_session):
    from solardoctor.physics import alert_worker
    from solardoctor.physics.models import Plant, PlantAlert, Telemetry
    p = Plant(name="P", lat=18.52, lon=73.86, dc_kw=120, ac_kw=100, tilt=18, azimuth=180, altitude_m=560)
    db_session.add(p)
    db_session.commit()
    now = datetime.now(tz=timezone.utc).replace(microsecond=0)
    # Measured irradiance 800 W/m2 but only 10 kW delivered: a gross shortfall vs expected power.
    db_session.add(Telemetry(plant_id=p.id, ts=now, p_ac_kw=10.0, ghi_wm2=800.0, source="SIMULATED"))
    db_session.commit()
    sent = []

    class Spy(alert_worker.NotificationAdapter):
        def send(self, message, severity, plant_id):
            sent.append((severity, plant_id))

    assert alert_worker.run_alert_check(db_session, p.id, adapter=Spy()) == 1
    alert = db_session.query(PlantAlert).one()
    assert alert.severity == "CRITICAL" and alert.source == "SIMULATED" and sent == [("CRITICAL", p.id)]
