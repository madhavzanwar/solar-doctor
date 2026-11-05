# Adapted from SolarPulseAI app/services/forecast_service.py
# (https://github.com/anugrahpatil-creator/SolarPulseAI), MIT License,
# Copyright (c) 2026 anugrahpatil-creator. See THIRD_PARTY_NOTICES.md.
# Modified for SolarDoctor: sync SQLAlchemy 2.0; pvlib PVWatts physics layer; trained-model path
# via ml.forecast; no random "development fallback" noise; honest model labels.
"""Forecast orchestration.

Pipeline: weather -> pvlib physics (clear-sky/POA/cell temp/PVWatts) -> soiling -> clipping
-> optional trained LightGBM -> online residual adapter -> ``forecasts`` row.

Model labels (``model_name``) are honest:
  * ``physics_baseline``  - no trained artifact; deterministic pvlib/PVWatts expected power.
  * ``lightgbm``          - a trained artifact from ``ml/forecast/artifacts`` was used.
  * probabilistic: ``physics_scenario_simulated`` when no quantile model exists. Its P10/P90 band
    and cloud-passage wave are a SIMULATED scenario (SolarPulse's heuristic), not a measured or
    learned uncertainty.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import numpy as np
import pandas as pd
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ml.forecast.postprocessing.ramp_risk import compute_ramp_risk_profile
from solardoctor.physics import solar, weather_service
from solardoctor.physics.clipping import calculate_clipping
from solardoctor.physics.models import Forecast, Plant, Telemetry
from solardoctor.physics.registry import get_registry
from solardoctor.physics.schemas.forecast import (
    ForecastSummary, ProbabilisticForecastPoint, ProbabilisticForecastResponse, RampRiskSummarySchema,
)
from solardoctor.physics.soiling import calculate_soiling_loss

logger = logging.getLogger("solardoctor.physics.forecast")

# SolarPulse placeholder: soiling is evaluated at a fixed 7 days since cleaning until real
# cleaning history is tracked. It is an ASSUMPTION, not an observation.
ASSUMED_DAYS_SINCE_CLEANING = 7.0


# ── Ported SolarPulse physics (kept verbatim for golden tests) ───────────────


def calculate_physics_power(
    latitude: float,
    longitude: float,
    tilt: float,
    azimuth: float,
    capacity_kw: float,
    efficiency: float,
    forecast_time: datetime,
    irradiance_w_m2: Optional[float] = None,
    temperature_c: Optional[float] = None,
) -> float:
    """SolarPulse's simple physics estimate (``_calculate_physics_power`` upstream).

    Clear-sky GHI via pvlib (or an astronomical fallback) x area x efficiency x temperature
    derate, capped at plant capacity. Zero at night. Kept for parity; the service itself uses
    the PVWatts model in ``solardoctor.physics.solar``.
    """
    import pvlib

    if irradiance_w_m2 is None:
        try:
            location = pvlib.location.Location(latitude=latitude, longitude=longitude, tz="UTC")
            times = pd.DatetimeIndex([forecast_time.astimezone(timezone.utc)])
            clearsky = location.get_clearsky(times)
            irradiance_w_m2 = max(0.0, float(clearsky["ghi"].iloc[0]))
        except Exception as exc:  # pragma: no cover - pvlib failure path
            logger.debug("pvlib clearsky failed: %s", exc)
            irradiance_w_m2 = None

        if irradiance_w_m2 is None:
            utc_time = forecast_time.astimezone(timezone.utc)
            doy = utc_time.timetuple().tm_yday
            hour_utc = utc_time.hour + utc_time.minute / 60.0
            solar_time_h = (hour_utc + longitude / 15.0) % 24.0
            declination_rad = np.radians(23.45 * np.sin(np.radians((360 / 365) * (doy - 81))))
            lat_rad = np.radians(latitude)
            hour_angle_rad = np.radians(15.0 * (solar_time_h - 12.0))
            sin_elevation = (
                np.sin(lat_rad) * np.sin(declination_rad)
                + np.cos(lat_rad) * np.cos(declination_rad) * np.cos(hour_angle_rad)
            )
            irradiance_w_m2 = 0.0 if sin_elevation <= 0.0 else float(980.0 * (sin_elevation ** 1.15))

    if irradiance_w_m2 <= 1.0:
        return 0.0

    temperature_c = temperature_c or 25.0
    temp_correction = 1.0 - max(0.0, (temperature_c - 25.0) * 0.004)
    panel_area_m2 = (capacity_kw * 1000.0) / (1000.0 * efficiency)
    dc_power_kw = (irradiance_w_m2 / 1000.0) * panel_area_m2 * efficiency * temp_correction / 1.0
    return min(dc_power_kw, capacity_kw)


def simulated_cloud_scenario(base_power: float, time_offset_min: float, ac_kw: float):
    """SolarPulse's synthetic cloud-passage wave -> (p10, p50, p90, cloud_pct). SIMULATED."""
    wave = 0.25 * np.sin(2 * np.pi * time_offset_min / 80.0) + 0.15 * np.cos(2 * np.pi * time_offset_min / 35.0)
    cloud_factor = float(np.clip(0.20 + wave, 0.05, 0.85))
    p50 = float(np.clip(base_power * (1.0 - 0.55 * cloud_factor), 0.0, ac_kw))
    p10 = float(np.clip(p50 * (1.0 - 0.40 * np.sqrt(cloud_factor)), 0.0, p50))
    p90 = float(np.clip(min(base_power, p50 * (1.0 + 0.35 * (1.0 - cloud_factor))), p50, ac_kw))
    return p10, p50, p90, cloud_factor * 100.0


# ── Physics layer used by the service ────────────────────────────────────────


def _weather_frame(wd: Optional[weather_service.WeatherData], times: pd.DatetimeIndex):
    """Return a frame (ghi, t, w, c) aligned to ``times`` from REAL weather, or None.

    The mock weather source is synthetic and is never used as an irradiance input.
    """
    if wd is None or wd.source == "mock" or not wd.hourly_forecast:
        return None
    pts = sorted(wd.hourly_forecast, key=lambda p: p.timestamp)
    idx = pd.DatetimeIndex([p.timestamp for p in pts]).tz_convert("UTC")
    df = pd.DataFrame({
        "ghi": [p.irradiance_w_m2 for p in pts],
        "t": [p.temperature_c for p in pts],
        "w": [p.wind_speed_kph / 3.6 for p in pts],
        "c": [p.cloud_cover_pct for p in pts],
    }, index=idx)
    df = df[~df.index.duplicated()].reindex(times, method="nearest", tolerance=pd.Timedelta("90min"))
    if df["ghi"].isna().all():
        return None
    return df.fillna({"ghi": 0.0, "t": 25.0, "w": 1.5, "c": 0.0})


def _ghi_from_weather(wd, times):
    df = _weather_frame(wd, times)
    return (None, None, None) if df is None else (df["ghi"], df["t"], df["w"])


def _physics_ac_series(plant: Plant, times: pd.DatetimeIndex, wd=None, soiling_loss: float = 0.0):
    ghi, t_air, wind = _ghi_from_weather(wd, times)
    return solar.expected_power(plant, times, ghi=ghi, temp_air=t_air, wind_speed=wind,
                                soiling_loss=soiling_loss)


def _soiling_fraction(plant_power_kw: float = 1.0, irradiance: float = 600.0) -> float:
    s = calculate_soiling_loss(
        current_power_kw=plant_power_kw, days_since_cleaning=ASSUMED_DAYS_SINCE_CLEANING,
        irradiance_w_m2=irradiance,
    )
    return s.soiling_loss_percent / 100.0


def _trained_dc_kw(plant: Plant, times: pd.DatetimeIndex, wd, probabilistic: bool = False):
    """Predict with a trained artifact, or return None when none exists / it fails."""
    try:
        model = get_registry().get_model(plant_id=str(plant.id), probabilistic=probabilistic)
    except FileNotFoundError:
        return None
    except Exception as exc:
        logger.error("Could not load model artifact: %s", exc)
        return None
    wf = _weather_frame(wd, times)
    if wf is None:
        return None  # trained models need real NWP inputs; the mock is not accepted
    try:
        from ml.forecast.features.feature_pipeline import SolarFeaturePipeline
        wx = pd.DataFrame({"ghi_nwp": wf["ghi"].values, "temp_ambient_nwp": wf["t"].values,
                           "wind_speed_nwp": wf["w"].values, "cloud_cover_pct": wf["c"].values}, index=times)
        # Weather feeds give GHI only; split into DNI/DHI with the Erbs model (as the feature
        # pipeline would for pvlib) so every canonical weather column is populated.
        import pvlib
        zen = pvlib.solarposition.get_solarposition(times, plant.lat, plant.lon)["apparent_zenith"]
        erbs = pvlib.irradiance.erbs(wx["ghi_nwp"], zen, times)
        wx["dni_nwp"], wx["dhi_nwp"] = erbs["dni"].fillna(0.0).values, erbs["dhi"].fillna(0.0).values
        X = SolarFeaturePipeline(solar.plant_config_from_orm(plant)).transform(wx)
        if probabilistic:
            return model.predict_quantiles(X)
        return pd.Series(model.predict(X), index=times)
    except Exception as exc:
        logger.error("Trained-model inference failed: %s", exc)
        return None


# ── Forecast generation ──────────────────────────────────────────────────────


def _latest_telemetry(db: Session, plant_id: int) -> Optional[Telemetry]:
    return db.execute(
        select(Telemetry).where(Telemetry.plant_id == plant_id).order_by(Telemetry.ts.desc()).limit(1)
    ).scalar_one_or_none()


def generate_forecast(db: Session, plant: Plant, horizon_minutes: int = 60, weather_transport=None) -> Forecast:
    """Generate and persist one forecast point ``horizon_minutes`` ahead."""
    forecast_time = datetime.now(tz=timezone.utc) + timedelta(minutes=horizon_minutes)
    wd = None
    try:
        wd = weather_service.get_forecast_weather(plant.lat, plant.lon, days=3, db=db,
                                                  transport=weather_transport)
    except Exception as exc:
        logger.warning("Could not fetch weather for plant %s: %s", plant.id, weather_service.redact(exc))

    times = pd.DatetimeIndex([forecast_time])
    soil = _soiling_fraction()
    phys = _physics_ac_series(plant, times, wd, soiling_loss=0.0)
    physics_dc = float(phys["p_dc_kw"].iloc[0])

    model_name, ml_kw = "physics_baseline", None
    trained = _trained_dc_kw(plant, times, wd)
    if trained is not None:
        ml_dc = float(trained.iloc[0]) * (1.0 - soil)
        ml_kw = calculate_clipping(ml_dc, plant.ac_kw, efficiency=solar.INVERTER_EFFICIENCY).clipped_ac_power_kw
        model_name = "lightgbm"
    soiled = _physics_ac_series(plant, times, wd, soiling_loss=soil)
    base_kw = ml_kw if ml_kw is not None else float(soiled["p_ac_kw"].iloc[0])

    # Online residual adapter (Tier 2): single-step correction
    final_kw = base_kw
    try:
        adapter = get_registry().get_online_adapter(str(plant.id))
        final_kw = float(adapter.adjust_forecast(np.array([base_kw]), np.array([0.0]))[0])
    except Exception as exc:
        logger.warning("Online adapter step failed, using base prediction: %s", exc)

    margin = final_kw * 0.10  # SolarPulse's fixed +/-10 % band; NOT a calibrated interval
    record = Forecast(
        plant_id=plant.id,
        forecast_time=forecast_time,
        generated_at=datetime.now(tz=timezone.utc),
        predicted_power_kw=round(final_kw, 4),
        confidence_lower=round(max(0.0, final_kw - margin), 4),
        confidence_upper=round(min(plant.ac_kw, final_kw + margin), 4),
        model_name=model_name,
        model_version="1.1",
        physics_power_kw=round(physics_dc, 4),
        ml_power_kw=round(base_kw, 4),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def get_forecasts(db: Session, plant_id: int, start: Optional[datetime] = None,
                  end: Optional[datetime] = None, limit: int = 200) -> List[Forecast]:
    q = select(Forecast).where(Forecast.plant_id == plant_id)
    if start:
        q = q.where(Forecast.forecast_time >= start)
    if end:
        q = q.where(Forecast.forecast_time <= end)
    return list(db.execute(q.order_by(Forecast.forecast_time.asc()).limit(limit)).scalars().all())


def get_forecast_summary(db: Session, plant_id: int, start: Optional[datetime] = None,
                         end: Optional[datetime] = None) -> ForecastSummary:
    records = get_forecasts(db, plant_id, start=start, end=end, limit=10000)
    if not records:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"No forecast records found for plant {plant_id}")
    predicted = [r.predicted_power_kw for r in records]
    actual = [r.actual_power_kw for r in records if r.actual_power_kw is not None]
    total_pred_kwh = sum(predicted) / 60.0  # SolarPulse assumes 1-minute spacing
    total_act_kwh = sum(actual) / 60.0 if actual else None
    mae = None
    if actual and len(actual) == len(records):
        mae = float(np.mean([abs(r.predicted_power_kw - (r.actual_power_kw or 0)) for r in records]))
    return ForecastSummary(
        plant_id=plant_id,
        period_start=min(r.forecast_time for r in records),
        period_end=max(r.forecast_time for r in records),
        total_predicted_kwh=round(total_pred_kwh, 4),
        total_actual_kwh=round(total_act_kwh, 4) if total_act_kwh is not None else None,
        mean_absolute_error_kw=round(mae, 4) if mae is not None else None,
        record_count=len(records),
        model_name=records[-1].model_name,
    )


def generate_probabilistic_forecast(
    db: Session, plant: Plant, horizon_minutes: int = 240, interval_minutes: int = 15,
    now: Optional[datetime] = None, weather_transport=None,
) -> ProbabilisticForecastResponse:
    """P10/P50/P90 series with ramp-rate/BESS metrics (see module docstring for labelling)."""
    now = now or datetime.now(tz=timezone.utc)
    start_time = now.replace(second=0, microsecond=0)
    remainder = start_time.minute % interval_minutes
    if remainder:
        start_time += timedelta(minutes=interval_minutes - remainder)
    step_count = max(2, int(horizon_minutes / interval_minutes) + 1)
    timestamps = [start_time + timedelta(minutes=i * interval_minutes) for i in range(step_count)]
    times = pd.DatetimeIndex(timestamps)

    wd = None
    try:
        wd = weather_service.get_forecast_weather(plant.lat, plant.lon, days=3, db=db,
                                                  transport=weather_transport)
    except Exception as exc:
        logger.warning("Could not fetch weather for plant %s: %s", plant.id, weather_service.redact(exc))

    soil = _soiling_fraction()
    base = _physics_ac_series(plant, times, wd, soiling_loss=soil)["p_ac_kw"].to_numpy()

    quant = _trained_dc_kw(plant, times, wd, probabilistic=True)
    if quant is not None:
        model_name = "probabilistic_quantile"
        scale = (1.0 - soil) * solar.INVERTER_EFFICIENCY
        p10 = np.minimum(quant["p10"].to_numpy() * scale, plant.ac_kw)
        p50 = np.minimum(quant["p50"].to_numpy() * scale, plant.ac_kw)
        p90 = np.minimum(quant["p90"].to_numpy() * scale, plant.ac_kw)
        cloud = [0.0] * len(times)
    else:
        model_name = "physics_scenario_simulated"
        p10, p50, p90, cloud = [], [], [], []
        for t, b in zip(timestamps, base):
            if b <= 0.5:
                p10.append(0.0); p50.append(0.0); p90.append(0.0); cloud.append(0.0)
            else:
                a, m, c, cl = simulated_cloud_scenario(float(b), (t - start_time).total_seconds() / 60.0, plant.ac_kw)
                p10.append(a); p50.append(m); p90.append(c); cloud.append(cl)

    df_points = pd.DataFrame({
        "forecast_time": [t.isoformat() for t in timestamps],
        "p10": np.round(p10, 2), "p50": np.round(p50, 2), "p90": np.round(p90, 2),
        "cloud_cover": np.round(cloud, 1),
    })
    metrics, risk = compute_ramp_risk_profile(df=df_points, capacity_kw=plant.dc_kw,
                                              interval_minutes=float(interval_minutes))
    points = [
        ProbabilisticForecastPoint(
            forecast_time=timestamps[i], p10_kw=pm.p10_kw, p50_kw=pm.p50_kw, p90_kw=pm.p90_kw,
            uncertainty_band_kw=pm.uncertainty_band_kw, relative_uncertainty_pct=pm.relative_uncertainty_pct,
            ramp_rate_kw_per_min=pm.ramp_rate_kw_per_min, ramp_rate_pct_per_min=pm.ramp_rate_pct_per_min,
            ramp_direction=pm.ramp_direction.value, ramp_risk_level=pm.ramp_risk_level.value,
            cloud_impact_factor=pm.cloud_impact_factor,
            bess_reserve_recommendation_kw=pm.bess_reserve_recommendation_kw,
            reserve_action=pm.reserve_action,
        )
        for i, pm in enumerate(metrics)
    ]
    summary = RampRiskSummarySchema(
        max_ramp_rate_kw_per_min=risk.max_ramp_rate_kw_per_min,
        max_ramp_down_kw_per_min=risk.max_ramp_down_kw_per_min,
        max_ramp_up_kw_per_min=risk.max_ramp_up_kw_per_min,
        ramp_risk_score=risk.ramp_risk_score,
        highest_risk_level=risk.highest_risk_level.value,
        high_risk_event_count=risk.high_risk_event_count,
        critical_risk_event_count=risk.critical_risk_event_count,
        avg_uncertainty_band_kw=risk.avg_uncertainty_band_kw,
        recommended_bess_capacity_kw=risk.recommended_bess_capacity_kw,
        primary_action_advisory=risk.primary_action_advisory,
    )
    return ProbabilisticForecastResponse(
        plant_id=plant.id, plant_name=plant.name, capacity_kw=plant.dc_kw, generated_at=now,
        horizon_minutes=horizon_minutes, interval_minutes=interval_minutes, model_name=model_name,
        points=points, summary=summary,
    )
