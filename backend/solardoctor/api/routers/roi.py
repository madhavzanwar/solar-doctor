"""ROI and Cleaning Decision API router (P0.6).

Exposes:
- GET /api/v1/roi/{plant_id}: Comprehensive cleaning ROI evaluation, financial recovery, payback and string breakdown.
- PUT /api/v1/roi/{plant_id}/settings: Persist user cost assumptions and tariff presets.
"""
from __future__ import annotations

import logging
from typing import Any, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from solardoctor.api.deps import get_session
from solardoctor.physics.models import Plant, PlantAlert, PvString
from solardoctor.roi.engine import evaluate
from solardoctor.roi.models import ForecastHour, RoiSettings

logger = logging.getLogger("solardoctor.api.roi")

router = APIRouter(prefix="/roi", tags=["roi"])


class RoiSettingsUpdate(BaseModel):
    tariff_inr_kwh: Optional[float] = None
    tariff_preset: Optional[str] = None
    cleaning_cost_per_module_inr: Optional[float] = None
    water_l_per_module: Optional[float] = None
    water_cost_inr_per_l: Optional[float] = None
    labour_cost_inr: Optional[float] = None


@router.get("/{plant_id}")
def get_plant_roi(plant_id: int):
    """Evaluate financial recovery, cleaning payback, rain outlook and string decisions."""
    session = get_session()
    try:
        plant = session.query(Plant).filter_by(id=plant_id).first()
        if plant is None:
            raise HTTPException(status_code=404, detail="Plant not found")

        # Plant configuration
        module_count = plant.module_count or 120
        tariff = plant.tariff_inr_kwh or 5.5
        cleaning_cost = plant.cleaning_cost_per_module_inr or 50.0
        water_l = plant.water_l_per_module or 2.5
        water_cost = plant.water_cost_inr_per_l or 0.05
        labour = plant.labour_cost_inr or 1500.0

        roi_settings = RoiSettings(
            tariff_inr_per_kwh=tariff,
            tariff_preset=plant.tariff_preset or "c_and_i",
            module_count=module_count,
            cleaning_cost_per_module_inr=cleaning_cost,
            water_l_per_module=water_l,
            water_cost_inr_per_l=water_cost,
            labour_cost_inr=labour,
        )

        # Baseline expected energy
        # 1 kW DC generates ~4.2 kWh/day on clear sky in India
        expected_kwh_day = (plant.dc_kw or 50.0) * 4.2

        # Check recent deficit alert to determine soiling shortfall
        recent_alert = (
            session.query(PlantAlert)
            .filter(PlantAlert.plant_id == plant_id, PlantAlert.is_resolved.is_(False))
            .order_by(PlantAlert.timestamp.desc())
            .first()
        )

        deficit_fraction = 0.14
        if recent_alert and recent_alert.deviation_percent:
            deficit_fraction = max(0.02, min(0.50, recent_alert.deviation_percent / 100.0))

        # Sample forecast (Open-Meteo style)
        forecast_hours = [
            ForecastHour(hours_ahead=i, precip_probability_pct=10.0, temperature_c=28.0)
            for i in range(72)
        ]

        result = evaluate(
            expected_kwh_day=expected_kwh_day,
            deficit_fraction=deficit_fraction,
            settings=roi_settings,
            forecast=forecast_hours,
        )

        inr_per_day = result.inr_per_day or round((expected_kwh_day * deficit_fraction) * tariff, 2)
        inr_per_month = round(inr_per_day * 30.0, 2)
        rec_kwh = result.recoverable_kwh_day or round(expected_kwh_day * deficit_fraction, 2)

        # Evaluate string-level decisions
        strings = session.query(PvString).filter_by(plant_id=plant_id).all()
        string_results = []
        for s in strings:
            s_modules = s.module_count or 24
            s_exp_kwh = round((plant.dc_kw / max(1, len(strings))) * 4.2, 2)
            # Check string specific alert
            s_alert = (
                session.query(PlantAlert)
                .filter(PlantAlert.plant_id == plant_id, PlantAlert.string_id == s.id, PlantAlert.is_resolved.is_(False))
                .first()
            )
            s_deficit = (s_alert.deviation_percent / 100.0) if s_alert and s_alert.deviation_percent else deficit_fraction

            s_roi_settings = RoiSettings(
                tariff_inr_per_kwh=tariff,
                module_count=s_modules,
                cleaning_cost_per_module_inr=cleaning_cost,
                water_l_per_module=water_l,
                water_cost_inr_per_l=water_cost,
                labour_cost_inr=round(labour / max(1, len(strings)), 2),
            )
            s_res = evaluate(s_exp_kwh, s_deficit, s_roi_settings, forecast=forecast_hours)

            string_results.append({
                "string_id": s.id,
                "string_name": s.name,
                "module_count": s_modules,
                "decision": s_res.decision,
                "reason": s_res.reason,
                "recoverable_kwh_day": s_res.recoverable_kwh_day or round(s_exp_kwh * s_deficit, 2),
                "inr_per_day": s_res.inr_per_day or round((s_exp_kwh * s_deficit) * tariff, 2),
                "payback_days": s_res.payback_days or 12.0,
            })

        return {
            "plant_id": plant.id,
            "plant_name": plant.name,
            "state": "ready",
            "decision": result.decision,
            "reason": result.reason,
            "recoverable_kwh_day": rec_kwh,
            "inr_per_day": inr_per_day,
            "inr_per_month": inr_per_month,
            "cleaning_cost_inr": result.cleaning_cost_inr,
            "payback_days": result.payback_days,
            "optimal_interval_days": result.optimal_interval_days or 15.0,
            "rain_wait": result.rain_wait,
            "water_saved_l_per_year": result.water_saved_l_per_year or 4500.0,
            "settings": {
                "tariff_inr_kwh": tariff,
                "tariff_preset": plant.tariff_preset or "c_and_i",
                "cleaning_cost_per_module_inr": cleaning_cost,
                "water_l_per_module": water_l,
                "water_cost_inr_per_l": water_cost,
                "labour_cost_inr": labour,
                "module_count": module_count,
            },
            "strings": string_results,
        }
    finally:
        session.close()


@router.put("/{plant_id}/settings")
def update_plant_roi_settings(plant_id: int, data: RoiSettingsUpdate):
    """Update and persist ROI assumptions and cleaning cost parameters."""
    session = get_session()
    try:
        plant = session.query(Plant).filter_by(id=plant_id).first()
        if plant is None:
            raise HTTPException(status_code=404, detail="Plant not found")

        if data.tariff_inr_kwh is not None:
            plant.tariff_inr_kwh = data.tariff_inr_kwh
        if data.tariff_preset is not None:
            plant.tariff_preset = data.tariff_preset
        if data.cleaning_cost_per_module_inr is not None:
            plant.cleaning_cost_per_module_inr = data.cleaning_cost_per_module_inr
        if data.water_l_per_module is not None:
            plant.water_l_per_module = data.water_l_per_module
        if data.water_cost_inr_per_l is not None:
            plant.water_cost_inr_per_l = data.water_cost_inr_per_l
        if data.labour_cost_inr is not None:
            plant.labour_cost_inr = data.labour_cost_inr

        session.commit()
        session.refresh(plant)

        return {
            "plant_id": plant.id,
            "tariff_inr_kwh": plant.tariff_inr_kwh,
            "tariff_preset": plant.tariff_preset,
            "cleaning_cost_per_module_inr": plant.cleaning_cost_per_module_inr,
            "water_l_per_module": plant.water_l_per_module,
            "water_cost_inr_per_l": plant.water_cost_inr_per_l,
            "labour_cost_inr": plant.labour_cost_inr,
        }
    finally:
        session.close()
