"""Weather provider chain: site sensor -> NASA POWER -> Open-Meteo -> clear-sky model (all network mocked)."""
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pvlib
import pytest

from solardoctor.physics import irradiance as irr
from solardoctor.physics import weather_service as ws

PLANT = SimpleNamespace(lat=18.52, lon=73.86, altitude_m=560.0)
DAY = pd.Timestamp("2026-03-19", tz="UTC")
TIMES = pd.date_range(DAY, periods=96, freq="15min")
NOW = DAY + pd.Timedelta(days=5)  # the whole day is in the past


def _cs(times=TIMES):
    return pvlib.location.Location(PLANT.lat, PLANT.lon, altitude=PLANT.altitude_m).get_clearsky(times)["ghi"]


def _nasa(hours, k=0.8, missing_from=None):
    """Hourly NASA-like frame from the previous midnight-ish: GHI = k x clear-sky at the hour centre.
    Hours at/after ``missing_from`` (UTC hour of DAY) are fill values (NaN)."""
    idx = pd.date_range(DAY - pd.Timedelta(hours=2), periods=hours + 2, freq="h")
    cs = pvlib.location.Location(PLANT.lat, PLANT.lon, altitude=PLANT.altitude_m).get_clearsky(
        idx + pd.Timedelta(minutes=30))["ghi"].to_numpy()
    df = pd.DataFrame({"ghi": k * cs, "temp_air": 30.0, "wind_speed": 2.0, "precip_mm": 0.0}, index=idx)
    if missing_from is not None:
        df.loc[df.index >= DAY + pd.Timedelta(hours=missing_from), :] = np.nan
    return df


def test_nasa_parser_reads_clearsky_and_precip_columns():
    payload = {"properties": {"parameter": {
        "ALLSKY_SFC_SW_DWN": {"2026031906": 100.0, "2026031907": -999.0},
        "CLRSKY_SFC_SW_DWN": {"2026031906": 150.0, "2026031907": 300.0},
        "PRECTOTCORR": {"2026031906": 0.2, "2026031907": 0.0}}}}
    df = ws.parse_nasa_power_hourly(payload)
    assert list(df.columns) == ["ghi", "ghi_clear", "precip_mm"]
    assert np.isnan(df["ghi"].iloc[1]) and df["precip_mm"].iloc[0] == 0.2


def test_site_sensor_wins_then_nasa_fills_the_rest():
    tel = pd.DataFrame({"ghi_wm2": 555.0, "poa_wm2": 600.0, "t_amb": 31.0}, index=TIMES[40:48])
    w = irr.resolve_weather(PLANT, TIMES, tel, now=NOW, nasa_fetch=lambda *a, **k: _nasa(24),
                            openmeteo_fetch=pytest.fail)
    assert (w["source"].iloc[40:48] == irr.SITE).all() and (w["ghi"].iloc[40:48] == 555.0).all()
    assert (w["poa"].iloc[40:48] == 600.0).all() and w["poa"].iloc[:40].isna().all()
    assert (w["temp_air"].iloc[40:48] == 31.0).all() and (w["temp_air"].iloc[:40] == 30.0).all()
    assert (w["source"].iloc[:40] == irr.NASA).all()
    assert list(w.columns) == ["ghi", "poa", "temp_air", "wind_speed", "precip_mm", "ghi_clearsky", "source"]


def test_nasa_ghi_follows_clearsky_index():
    w = irr.resolve_weather(PLANT, TIMES, None, now=NOW, nasa_fetch=lambda *a, **k: _nasa(24, k=0.8))
    noon = (w["ghi_clearsky"] > 500)
    assert noon.any() and np.allclose(w.loc[noon, "ghi"] / w.loc[noon, "ghi_clearsky"], 0.8, atol=0.03)


def test_nasa_recent_days_missing_fall_through_to_clearsky_model():
    hourly = _nasa(24, missing_from=10)  # latency: last hours are fill values
    w = irr.resolve_weather(PLANT, TIMES, None, now=NOW, nasa_fetch=lambda *a, **k: hourly)
    assert (w["source"].iloc[:36] == irr.NASA).all()          # before the gap (plus half-hour margin)
    assert (w["source"].iloc[44:] == irr.CLEARSKY).all()
    assert np.allclose(w["ghi"].iloc[44:], w["ghi_clearsky"].iloc[44:])
    assert not w["ghi"].isna().any()


def test_nasa_failure_does_not_raise():
    def boom(*a, **k):
        raise TimeoutError("nasa down")
    w = irr.resolve_weather(PLANT, TIMES, None, now=NOW, nasa_fetch=boom)
    assert (w["source"] == irr.CLEARSKY).all()


def test_openmeteo_only_for_future_rows_within_three_days():
    now = DAY + pd.Timedelta(hours=12)
    om_idx = pd.date_range(DAY, periods=24 * 3 + 12, freq="h")
    om = pd.DataFrame({"shortwave_radiation": 400.0, "temperature_2m": 28.0, "wind_speed_10m": 3.0,
                       "precipitation_probability": 10.0, "precipitation": 0.1}, index=om_idx)
    times = pd.date_range(DAY, periods=24 * 4 * 5, freq="15min")  # 5 days from DAY
    w = irr.resolve_weather(PLANT, times, None, now=now, nasa_fetch=lambda *a, **k: _nasa(12),
                            openmeteo_fetch=lambda *a, **k: om)
    src = w["source"]
    assert (src[times <= now - pd.Timedelta(hours=1)] == irr.NASA).all()
    mid = (times > now + pd.Timedelta(hours=1)) & (times < now + pd.Timedelta(days=2))
    assert (src[mid] == irr.OPENMETEO).all() and (w.loc[mid, "temp_air"] == 28.0).all()
    assert (src[times > now + pd.Timedelta(days=3, hours=1)] == irr.CLEARSKY).all()


def test_openmeteo_failure_falls_back_to_clearsky():
    now = DAY - pd.Timedelta(hours=1)
    w = irr.resolve_weather(PLANT, TIMES, None, now=now, nasa_fetch=pytest.fail,
                            openmeteo_fetch=lambda *a, **k: (_ for _ in ()).throw(OSError("down")))
    assert (w["source"] == irr.CLEARSKY).all()


class _Var:
    def __init__(self, v): self.v = v
    def ValuesAsNumpy(self): return np.asarray(self.v, dtype="float32")


class _Hourly:
    def Time(self): return int(DAY.timestamp())
    def TimeEnd(self): return int(DAY.timestamp()) + 3 * 3600
    def Interval(self): return 3600
    def Variables(self, i): return _Var([i * 10.0 + k for k in range(3)])


class _Client:
    calls = 0
    def weather_api(self, url, params):
        type(self).calls += 1
        assert params["hourly"] == irr._OM_VARS and params["forecast_days"] == 3
        return [SimpleNamespace(Hourly=lambda: _Hourly())]


def test_openmeteo_client_parse_and_cache(db_session):
    df = irr.fetch_openmeteo_hourly(18.52, 73.86, db=db_session, client=_Client())
    assert list(df.columns) == irr._OM_VARS and len(df) == 3 and df.index[0] == DAY
    assert df["temperature_2m"].tolist() == [10.0, 11.0, 12.0]
    again = irr.fetch_openmeteo_hourly(18.52, 73.86, db=db_session, client=_Client())
    assert _Client.calls == 1 and again["precipitation"].tolist() == df["precipitation"].tolist()
