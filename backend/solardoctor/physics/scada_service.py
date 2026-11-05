# Adapted from SolarPulseAI app/services/scada_service.py
# (https://github.com/anugrahpatil-creator/SolarPulseAI), MIT License,
# Copyright (c) 2026 anugrahpatil-creator. See THIRD_PARTY_NOTICES.md.
# Modified for SolarDoctor: sync SQLAlchemy 2.0; SCADA readings stored in the ``telemetry`` table.
"""SCADA ingestion and retrieval, plus the online-adapter feedback loop.

SolarPulse's ``ScadaReading`` fields map onto ``telemetry`` columns:
power_kw -> p_ac_kw (falls back to inverter_power_kw), irradiance_w_m2 -> ghi_wm2,
temperature_c -> t_amb, module_temperature_c -> t_mod, wind_speed_m_s -> wind_ms,
expected_power_kw -> p_expected_kw.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from solardoctor.physics.models import Forecast, Plant, PlantAlert, Telemetry
from solardoctor.physics.registry import get_registry
from solardoctor.physics.schemas.scada import ScadaReadingCreate, ScadaReadingResponse

logger = logging.getLogger("solardoctor.physics.scada")

_FORECAST_MATCH_WINDOW_MINUTES = 20  # +/- around the reading


def to_response(t: Telemetry) -> ScadaReadingResponse:
    return ScadaReadingResponse(
        id=t.id, plant_id=t.plant_id, timestamp=t.ts, power_kw=t.p_ac_kw, irradiance_w_m2=t.ghi_wm2,
        temperature_c=t.t_amb, wind_speed_m_s=t.wind_ms, module_temperature_c=t.t_mod,
        inverter_power_kw=t.p_ac_kw, expected_power_kw=t.p_expected_kw, created_at=t.ts,
    )


def _from_create(d: ScadaReadingCreate) -> Telemetry:
    extra = d.model_dump()
    return Telemetry(
        plant_id=d.plant_id, ts=d.timestamp,
        p_ac_kw=d.power_kw if d.power_kw is not None else d.inverter_power_kw,
        ghi_wm2=d.irradiance_w_m2, t_amb=d.temperature_c, t_mod=d.module_temperature_c,
        wind_ms=d.wind_speed_m_s, p_expected_kw=d.expected_power_kw,
        poa_wm2=extra.get("poa_wm2"), p_dc_kw=extra.get("p_dc_kw"), v=extra.get("v"), i=extra.get("i"),
        inverter_id=extra.get("inverter_id"), string_id=extra.get("string_id"),
        source=extra.get("source") or "USER",
    )


def _online_adapter_updates(db: Session, rows: List[Telemetry]) -> None:
    """Step the OnlineResidualAdapter for new readings. Best-effort: never raises.

    Lookups are batched per plant (one forecast query over the batch's time span, one active-alert
    count) and the adapter checkpoint is written once per plant, not once per row.
    """
    try:
        window = timedelta(minutes=_FORECAST_MATCH_WINDOW_MINUTES)
        by_plant: Dict[int, List[Telemetry]] = {}
        for r in rows:
            if r.p_ac_kw is not None:
                by_plant.setdefault(r.plant_id, []).append(r)
        registry = get_registry()
        for plant_id, rs in by_plant.items():
            rs.sort(key=lambda r: r.ts)
            forecasts = db.execute(
                select(Forecast).where(
                    Forecast.plant_id == plant_id,
                    Forecast.forecast_time >= rs[0].ts - window, Forecast.forecast_time <= rs[-1].ts + window)
            ).scalars().all()
            if not forecasts:
                continue
            active = db.execute(
                select(func.count(PlantAlert.id)).where(
                    PlantAlert.plant_id == plant_id, PlantAlert.is_resolved.is_(False))
            ).scalar_one() or 0
            applied = False
            for r in rs:
                near = [f for f in forecasts if abs((f.forecast_time - r.ts).total_seconds()) <= window.total_seconds()]
                if not near:
                    continue
                match = min(near, key=lambda f: abs((f.forecast_time - r.ts).total_seconds()))
                applied |= registry.update_online_state(
                    plant_id=str(plant_id), y_actual=r.p_ac_kw, y_pred_base=match.ml_power_kw or match.predicted_power_kw,
                    ghi=r.ghi_wm2 or 0.0, has_active_anomaly=active > 0, persist=False)
            if applied:
                registry._persist_adapter(registry.get_online_adapter(str(plant_id)))
    except Exception as exc:
        logger.warning("Online adapter update failed: %s", exc)


def assert_plant_exists(db: Session, plant_id: int) -> None:
    if db.execute(select(Plant.id).where(Plant.id == plant_id)).scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Plant {plant_id} not found")


def insert_reading(db: Session, data: ScadaReadingCreate) -> Telemetry:
    assert_plant_exists(db, data.plant_id)
    reading = _from_create(data)
    db.add(reading)
    db.commit()
    db.refresh(reading)
    _online_adapter_updates(db, [reading])
    return reading


def batch_insert_readings(db: Session, readings: List[ScadaReadingCreate]) -> List[Telemetry]:
    if not readings:
        return []
    pids = {r.plant_id for r in readings}
    found = set(db.execute(select(Plant.id).where(Plant.id.in_(pids))).scalars())
    missing = pids - found
    if missing:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Plant {sorted(missing)[0]} not found")
    rows = [_from_create(r) for r in readings]
    db.add_all(rows)
    db.commit()
    _online_adapter_updates(db, rows)
    return rows


def get_recent_readings(db: Session, plant_id: int, limit: int = 100) -> List[Telemetry]:
    assert_plant_exists(db, plant_id)
    return list(db.execute(
        select(Telemetry).where(Telemetry.plant_id == plant_id).order_by(Telemetry.ts.desc()).limit(limit)
    ).scalars().all())


def get_readings_by_range(db: Session, plant_id: int, start: datetime, end: datetime,
                          limit: int = 1000) -> List[Telemetry]:
    assert_plant_exists(db, plant_id)
    return list(db.execute(
        select(Telemetry).where(Telemetry.plant_id == plant_id, Telemetry.ts >= start, Telemetry.ts <= end)
        .order_by(Telemetry.ts.asc()).limit(limit)
    ).scalars().all())


def get_scada_statistics(db: Session, plant_id: int) -> Dict[str, Optional[float]]:
    assert_plant_exists(db, plant_id)
    row = db.execute(
        select(
            func.avg(Telemetry.p_ac_kw), func.max(Telemetry.p_ac_kw), func.min(Telemetry.p_ac_kw),
            func.avg(Telemetry.ghi_wm2), func.count(Telemetry.id),
        ).where(Telemetry.plant_id == plant_id)
    ).one()
    return {
        "avg_power_kw": row[0], "max_power_kw": row[1], "min_power_kw": row[2],
        "avg_irradiance_w_m2": row[3], "total_readings": row[4],
    }
