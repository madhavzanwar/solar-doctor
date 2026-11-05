"""Deterministic golden cases run against either the SolarPulse originals or the SolarDoctor port.

``run_cases(ns)`` returns a JSON-serialisable dict; ``ns`` supplies the callables (see ``ours()`` /
``original()``). Captured originals live in golden/solarpulse_golden.json so the comparison still
works when the SolarPulse clone is absent (regenerate with ``python make_golden.py``).
"""
from __future__ import annotations

import contextlib
import dataclasses
import math
from datetime import datetime, timezone
from types import SimpleNamespace

import numpy as np
import pandas as pd

NDIGITS = 6


def _clean(x):
    if isinstance(x, (np.floating, float)):
        x = float(x)
        return None if math.isnan(x) else round(x, NDIGITS)
    if isinstance(x, datetime):
        return x.isoformat()
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, pd.DataFrame):
        return {c: [_clean(v) for v in x[c].tolist()] for c in x.columns}
    if isinstance(x, (pd.Series, np.ndarray)):
        return [_clean(v) for v in list(x)]
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if hasattr(x, "value") and hasattr(x, "name") and not isinstance(x, (str, bytes)):
        return x.value  # Enum
    if dataclasses.is_dataclass(x):
        return _clean(dataclasses.asdict(x))
    return x


def weather_df() -> pd.DataFrame:
    times = pd.date_range("2024-06-01 00:00:00", periods=48, freq="1h", tz="UTC")
    hours = times.hour.values
    daylight = (hours >= 6) & (hours <= 18)
    ghi = np.zeros(len(times))
    ghi[daylight] = 850.0 * np.sin(np.pi * (hours[daylight] - 6) / 12.0)
    return pd.DataFrame({
        "ghi_nwp": ghi,
        "dni_nwp": np.where(ghi > 50, ghi * 1.1, 0.0),
        "dhi_nwp": np.where(ghi > 50, ghi * 0.25, 0.0),
        "temp_ambient_nwp": 22.0 + 10.0 * (ghi / 850.0),
        "wind_speed_nwp": np.full(48, 2.5),
        "cloud_cover_pct": np.full(48, 15.0),
    }, index=times)


def _train_data():
    wx = weather_df()
    rng = np.random.RandomState(0)
    y = (wx["ghi_nwp"].values / 1000.0) * 900.0 + rng.normal(0, 5.0, len(wx))
    return wx, np.clip(y, 0, None)


WEATHERAPI_RAW = {
    "location": {"name": "Pune", "tz_id": "Asia/Kolkata"},
    "current": {"temp_c": 31.2, "humidity": 40, "wind_kph": 11.0, "cloud": 25, "uv": 7.0,
                "condition": {"text": "Sunny"}, "is_day": 1},
    "forecast": {"forecastday": [{"hour": [
        {"time_epoch": 1717228800 + 3600 * h, "temp_c": 20.0 + h, "humidity": 50, "wind_kph": 8.0,
         "cloud": 10 * (h % 5), "uv": float(h % 9), "condition": {"text": "Clear"}, "is_day": 1 if 6 <= h <= 18 else 0}
        for h in range(0, 24, 3)]}]},
}


# The mock weather is a function of the wall-clock hour (is_day, sun fraction -> condition text). The
# captured golden values were taken in daylight at the plant's longitude, so pin the clock to a fixed
# daytime instant (2026-11-05 06:30 UTC, ~12:00 IST) for BOTH the port and the original.
FROZEN_NOW = datetime(2026, 11, 5, 6, 30, tzinfo=timezone.utc)


class _FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return FROZEN_NOW if tz is None else FROZEN_NOW.astimezone(tz)


@contextlib.contextmanager
def frozen_clock(module):
    """Replace ``datetime`` in a service module with one whose now() is FROZEN_NOW."""
    original = module.datetime
    module.datetime = _FrozenDatetime
    try:
        yield
    finally:
        module.datetime = original


def run_cases(ns: SimpleNamespace) -> dict:
    out: dict = {}
    wx = weather_df()
    cfg = ns.PlantConfig(
        plant_id="t", name="Test", latitude=28.6139, longitude=77.2090, altitude=216.0, tilt_deg=25.0,
        azimuth_deg=180.0, capacity_dc_kw=1000.0, ac_export_limit_kw=800.0)

    # 1. pvlib feature extraction + full 21-column pipeline
    out["pvlib_features"] = _clean(ns.compute_pvlib_features(wx, cfg))
    scada = pd.Series((wx["ghi_nwp"].values / 1000.0) * 850.0, index=wx.index, name="active_power_kw")
    out["pipeline_21"] = _clean(ns.SolarFeaturePipeline(cfg).transform(wx, scada_history=scada))

    # 2. clipping
    g = np.array([0.0, 100.0, 799.9, 800.0, 950.0, 1200.0])
    out["clip_array"] = _clean(ns.apply_clipping(g, 800.0))
    out["clip_scalar"] = _clean(ns.apply_clipping(950.0, 800.0))
    out["clip_series"] = _clean(ns.apply_clipping(pd.Series(g), 800.0))
    out["clip_metrics"] = _clean(ns.calculate_clipping_metrics(g, 800.0, 0.5))
    out["clip_service"] = [
        _clean(ns.calculate_clipping(dc, 100.0, eff)) for dc, eff in [(0, 0.96), (50, 0.96), (110, 0.96), (200, 1.0), (-5, 0.9)]
    ]

    # 3. soiling
    ts = pd.date_range("2024-01-01", periods=240, freq="6h", tz="UTC")
    rain = np.zeros(240)
    rain[60], rain[120], rain[180] = 5.0, 14.0, 1.0
    s = ns.calculate_dynamic_soiling(ts, rain, soiling_rate_per_day=0.004)
    out["soiling_series"] = _clean(s)
    clipped = np.linspace(0, 500, 240)
    deliv = ns.apply_soiling_loss(clipped, s.values)
    out["soiling_apply"] = _clean(deliv)
    out["soiling_metrics"] = _clean(ns.calculate_soiling_metrics(clipped, deliv, 6.0))
    out["soiling_service"] = [
        _clean(ns.calculate_soiling_loss(500.0, d, rf, irr, prev_loss := 0.5 if d > 5 else 0.0))
        for d, rf, irr in [(0, 0, 1000), (7, 0, 600), (40, 0, 1200), (20, 6.0, 800), (-3, -1, -10)]
    ]

    # 4. ramp risk
    n = 24
    p50 = np.concatenate([np.linspace(0, 700, 8), [700, 500, 250, 600, 700, 690], np.linspace(650, 0, 10)])
    df = pd.DataFrame({
        "p10": p50 * 0.7, "p50": p50, "p90": np.minimum(p50 * 1.2, 800.0),
        "cloud_cover": np.linspace(5, 80, n),
    })
    pts, summ = ns.compute_ramp_risk_profile(df, capacity_kw=1000.0, interval_minutes=15.0)
    out["ramp_points"] = _clean([dataclasses.asdict(p) for p in pts])
    out["ramp_summary"] = _clean(dataclasses.asdict(summ))
    out["ramp_classify"] = [
        ns.classify_ramp_risk(r, u, c, d).value
        for r in (0.2, 1.2, 2.6, 4.0, 5.5) for u, c, d in [(10, 0.1, False), (45, 0.7, True)]
    ]

    # 5. online residual adapter
    ad = ns.OnlineResidualAdapter("p1")
    applied = []
    seq = [(80, 100, 600), (90, 100, 650), (120, 100, 700), (50, 100, 10), (95, 100, 800), (60, 100, 500)]
    for ya, yb, ghi in seq:
        applied.append(ad.update(ya, yb, ghi))
    applied.append(ad.update(70, 100, 600, has_active_anomaly=True))
    applied.append(ad.update(70, 100, 600, is_curtailed=True))
    out["adapter_applied"] = applied
    st = ad.get_status()
    out["adapter_status"] = _clean({k: v for k, v in st.items() if k != "last_updated"})
    out["adapter_adjust"] = _clean(ad.adjust_forecast(np.array([0.0, 100, 200, 300]), np.array([0, 1, 4, 10])))

    # 6. LightGBM + probabilistic quantile models (fixed data/seed)
    X, y = _train_data()
    Xf = ns.SolarFeaturePipeline(cfg).transform(X)
    params = {"n_estimators": 40, "n_jobs": 1, "num_leaves": 7, "min_child_samples": 3}
    m = ns.LightGBMForecaster(params=params)
    m.fit(Xf, y)
    out["lgbm_pred"] = _clean(m.predict(Xf))
    pm = ns.ProbabilisticForecaster(base_params={"n_estimators": 40, "n_jobs": 1, "num_leaves": 7, "min_child_samples": 3})
    pm.fit(Xf, y)
    out["prob_pred"] = _clean(pm.predict_quantiles(Xf))

    # 7. anomaly thresholds / severity
    out["deviation"] = [ns.calculate_deviation(e, a) for e, a in [(100, 90), (100, 60), (0, 5), (None, 1), (50, 55), (0.0005, 0)]]
    th = {"warning": 10.0, "critical": 25.0}
    out["severity"] = [ns.classify_severity(d, th) for d in (0, 9.99, 10, 24.9, 25, 80, -5)]

    # 8. diagnosis
    ts0 = datetime(2026, 3, 20, 6, 0, tzinfo=timezone.utc)
    cases = [
        dict(inverter_error_code="F056"), dict(inverter_error_code="afci"), dict(inverter_error_code="ZZ"),
        dict(inverter_error_code="ISO_FAULT"), dict(inverter_error_code="COMM_TIMEOUT"),
        dict(expected_power_kw=100, actual_power_kw=40, irradiance_w_m2=800, temperature_c=38),
        dict(expected_power_kw=100, actual_power_kw=45, irradiance_w_m2=800, temperature_c=25),
        dict(expected_power_kw=100, actual_power_kw=10, irradiance_w_m2=800, temperature_c=25),
        dict(expected_power_kw=100, actual_power_kw=85, irradiance_w_m2=800, days_since_cleaning=12),
        dict(expected_power_kw=100, actual_power_kw=95, irradiance_w_m2=900),
        dict(expected_power_kw=100, actual_power_kw=95, irradiance_w_m2=300),
        dict(expected_power_kw=100, actual_power_kw=80, alert_message="Inverter trip F034 detected"),
        dict(expected_power_kw=100, actual_power_kw=80, alert_message="Heavy dust soiling"),
        dict(expected_power_kw=100, actual_power_kw=80, alert_message="grid curtailment active"),
        dict(),
    ]
    diags = []
    for c in cases:
        d = ns.diagnose_root_cause(plant_id=1, plant_name="P", capacity_kw=1000.0, timestamp=ts0, **c)
        dd = d.model_dump()
        for k in ("created_at", "timestamp", "currency", "financial_assumption", "telemetry_ts", "telemetry_source"):
            dd.pop(k, None)
        diags.append(_clean(dd))
    out["diagnosis"] = diags
    out["taxonomy"] = _clean([t.model_dump() for t in ns.get_root_cause_taxonomy()])

    # 9. weather helpers (deterministic parts)
    out["irradiance_estimate"] = [
        ns.estimate_irradiance(c, uv, d) for c, uv, d in [(0, 8, True), (50, 4, True), (100, 8, True), (20, 12, True), (0, 8, False)]]
    cur = ns.parse_current(WEATHERAPI_RAW)
    out["weather_current"] = _clean({k: v for k, v in dataclasses.asdict(cur).items() if k != "timestamp"})
    out["weather_hourly"] = _clean([dataclasses.asdict(p) for p in ns.parse_hourly(WEATHERAPI_RAW)])
    with frozen_clock(ns.weather_module):
        mock = ns.mock_weather(18.52, 73.86)
    out["weather_mock_static"] = _clean({"loc": mock.location_name, "source": mock.source, "n": len(mock.hourly_forecast),
                                         "cond": mock.current.condition_text})

    # 10. SolarPulse's simple physics power (pvlib clear-sky + area/efficiency model)
    when = datetime(2026, 3, 20, 7, 0, tzinfo=timezone.utc)
    out["physics_power"] = [
        _clean(ns.calculate_physics_power(18.5204, 73.8567, 18.0, 180.0, 120.0, 0.18, when)),
        _clean(ns.calculate_physics_power(18.5204, 73.8567, 18.0, 180.0, 120.0, 0.18, datetime(2026, 3, 20, 20, 0, tzinfo=timezone.utc))),
        _clean(ns.calculate_physics_power(18.5204, 73.8567, 18.0, 180.0, 120.0, 0.18, when, irradiance_w_m2=700.0, temperature_c=40.0)),
        _clean(ns.calculate_physics_power(18.5204, 73.8567, 18.0, 180.0, 120.0, 0.18, when, irradiance_w_m2=0.5)),
        _clean(ns.calculate_physics_power(18.5204, 73.8567, 18.0, 180.0, 5.0, 0.18, when, irradiance_w_m2=1500.0)),
    ]
    return out


def ours() -> SimpleNamespace:
    from ml.forecast.config import PlantConfig
    from ml.forecast.features.feature_pipeline import SolarFeaturePipeline
    from ml.forecast.features.pvlib_features import compute_pvlib_features
    from ml.forecast.models.lightgbm_model import LightGBMForecaster
    from ml.forecast.models.online_residual_adapter import OnlineResidualAdapter
    from ml.forecast.models.probabilistic_model import ProbabilisticForecaster
    from ml.forecast.postprocessing import clipping as pc, ramp_risk as rr, soiling as ps
    from solardoctor.physics import anomaly_service as an, clipping as cs, diagnosis_service as ds
    from solardoctor.physics import forecast_service as fs, soiling as ss, weather_service as ws
    return SimpleNamespace(
        PlantConfig=PlantConfig, compute_pvlib_features=compute_pvlib_features,
        SolarFeaturePipeline=SolarFeaturePipeline, apply_clipping=pc.apply_clipping,
        calculate_clipping_metrics=pc.calculate_clipping_metrics, calculate_clipping=cs.calculate_clipping,
        calculate_dynamic_soiling=ps.calculate_dynamic_soiling, apply_soiling_loss=ps.apply_soiling_loss,
        calculate_soiling_metrics=ps.calculate_soiling_metrics, calculate_soiling_loss=ss.calculate_soiling_loss,
        compute_ramp_risk_profile=rr.compute_ramp_risk_profile, classify_ramp_risk=rr.classify_ramp_risk,
        OnlineResidualAdapter=OnlineResidualAdapter, LightGBMForecaster=LightGBMForecaster,
        ProbabilisticForecaster=ProbabilisticForecaster, calculate_deviation=an.calculate_deviation,
        classify_severity=an._classify_severity, diagnose_root_cause=ds.diagnose_root_cause,
        get_root_cause_taxonomy=ds.get_root_cause_taxonomy, estimate_irradiance=ws._estimate_irradiance,
        parse_current=ws._parse_current, parse_hourly=ws._parse_hourly_forecast, mock_weather=ws._mock_weather_data,
        calculate_physics_power=fs.calculate_physics_power, weather_module=ws,
    )


def original() -> SimpleNamespace:
    import sp_original as o
    return SimpleNamespace(
        PlantConfig=o.mod("ml.config").PlantConfig,
        compute_pvlib_features=o.mod("ml.features.pvlib_features").compute_pvlib_features,
        SolarFeaturePipeline=o.mod("ml.features.feature_pipeline").SolarFeaturePipeline,
        apply_clipping=o.mod("ml.postprocessing.clipping").apply_clipping,
        calculate_clipping_metrics=o.mod("ml.postprocessing.clipping").calculate_clipping_metrics,
        calculate_clipping=o.mod("services.clipping_service").calculate_clipping,
        calculate_dynamic_soiling=o.mod("ml.postprocessing.soiling").calculate_dynamic_soiling,
        apply_soiling_loss=o.mod("ml.postprocessing.soiling").apply_soiling_loss,
        calculate_soiling_metrics=o.mod("ml.postprocessing.soiling").calculate_soiling_metrics,
        calculate_soiling_loss=o.mod("services.soiling_service").calculate_soiling_loss,
        compute_ramp_risk_profile=o.mod("ml.postprocessing.ramp_risk").compute_ramp_risk_profile,
        classify_ramp_risk=o.mod("ml.postprocessing.ramp_risk").classify_ramp_risk,
        OnlineResidualAdapter=o.mod("ml.models.online_residual_adapter").OnlineResidualAdapter,
        LightGBMForecaster=o.mod("ml.models.lightgbm_model").LightGBMForecaster,
        ProbabilisticForecaster=o.mod("ml.models.probabilistic_model").ProbabilisticForecaster,
        calculate_deviation=o.mod("services.anomaly_service").calculate_deviation,
        classify_severity=o.mod("services.anomaly_service")._classify_severity,
        diagnose_root_cause=o.mod("services.diagnosis_service").diagnose_root_cause,
        get_root_cause_taxonomy=o.mod("services.diagnosis_service").get_root_cause_taxonomy,
        estimate_irradiance=o.mod("services.weather_service")._estimate_irradiance,
        parse_current=o.mod("services.weather_service")._parse_current,
        parse_hourly=o.mod("services.weather_service")._parse_hourly_forecast,
        mock_weather=o.mod("services.weather_service")._mock_weather_data,
        calculate_physics_power=o.mod("services.forecast_service")._calculate_physics_power,
        weather_module=o.mod("services.weather_service"),
    )
