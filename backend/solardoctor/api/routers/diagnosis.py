"""diagnosis router: SolarPulse /diagnosis endpoints (root-cause taxonomy, on-demand and per-alert)."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from solardoctor.physics import diagnosis_service, plant_service
from solardoctor.physics.deps import get_db
from solardoctor.physics.schemas.diagnosis import DiagnosisRequest, DiagnosisResponse, RootCauseTaxonomyItem

router = APIRouter(prefix="/diagnosis", tags=["AI Diagnosis"])


@router.get("/taxonomy", response_model=List[RootCauseTaxonomyItem],
            summary="Root-cause diagnostic taxonomy and supported inverter error codes")
def get_taxonomy():
    return diagnosis_service.get_root_cause_taxonomy()


@router.post("/diagnose", response_model=DiagnosisResponse,
             summary="Rule-based root-cause diagnosis from telemetry or inverter error codes")
def run_diagnosis(request: DiagnosisRequest, db: Session = Depends(get_db)):
    plant = plant_service.get_plant(db, request.plant_id)
    has_tariff = plant.tariff_inr_kwh is not None
    try:
        expected, actual, tel = diagnosis_service.resolve_power_inputs(
            db, plant, request.expected_power_kw, request.actual_power_kw,
            allow_simulated=request.allow_simulated)
    except diagnosis_service.InsufficientDataError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    diag = diagnosis_service.diagnose_root_cause(
        plant_id=plant.id, plant_name=plant.name, capacity_kw=plant.dc_kw,
        alert_id=request.alert_id, inverter_error_code=request.inverter_error_code,
        expected_power_kw=expected, actual_power_kw=actual,
        irradiance_w_m2=request.irradiance_w_m2, temperature_c=request.temperature_c,
        module_temp_c=request.module_temp_c, days_since_cleaning=request.days_since_cleaning,
        notes=request.notes,
        tariff_per_kwh=plant.tariff_inr_kwh if has_tariff else None,
        currency="INR" if has_tariff else diagnosis_service.CURRENCY_UNSET,
    )
    if tel is not None:
        diag.telemetry_ts, diag.telemetry_source = tel.ts, tel.source
        diag.telemetry_evidence = {**(diag.telemetry_evidence or {}), "telemetry_ts": tel.ts.isoformat(),
                                   "telemetry_source": tel.source}
    diag.id = diagnosis_service.persist_diagnosis(db, diag).id
    return diag


@router.get("/alert/{alert_id}", response_model=DiagnosisResponse,
            summary="Run or retrieve the root-cause diagnosis for a plant alert")
def diagnose_alert(alert_id: int, db: Session = Depends(get_db)):
    try:
        return diagnosis_service.run_diagnosis_for_alert(db, alert_id)
    except diagnosis_service.InsufficientDataError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/plant/{plant_id}", response_model=List[DiagnosisResponse],
            summary="List root-cause diagnoses for a plant")
def list_plant_diagnoses(plant_id: int, limit: int = Query(default=50, ge=1, le=200),
                         db: Session = Depends(get_db)):
    return diagnosis_service.list_diagnoses_by_plant(db, plant_id=plant_id, limit=limit)
