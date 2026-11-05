"""forecast router: SolarPulse /forecast endpoints (sync)."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from solardoctor.physics import forecast_service, plant_service
from solardoctor.physics.deps import get_db
from solardoctor.physics.registry import get_registry
from solardoctor.physics.schemas.forecast import (
    ForecastResponse, ForecastSummary, OnlineAdapterStatusResponse, ProbabilisticForecastResponse,
)

router = APIRouter(prefix="/forecast", tags=["Forecast"])


@router.get("/{plant_id}", response_model=List[ForecastResponse], summary="Get forecast records for a plant")
def get_forecasts(
    plant_id: int,
    start: Optional[datetime] = Query(default=None, description="Start datetime (ISO 8601)"),
    end: Optional[datetime] = Query(default=None, description="End datetime (ISO 8601)"),
    limit: int = Query(default=200, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    plant_service.get_plant(db, plant_id)
    return forecast_service.get_forecasts(db, plant_id=plant_id, start=start, end=end, limit=limit)


@router.get("/{plant_id}/summary", response_model=ForecastSummary,
            summary="Get forecast summary statistics for a plant")
def get_forecast_summary(
    plant_id: int,
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
    db: Session = Depends(get_db),
):
    return forecast_service.get_forecast_summary(db, plant_id=plant_id, start=start, end=end)


@router.post("/{plant_id}/generate", response_model=ForecastResponse,
             summary="Trigger an on-demand forecast for a plant")
def generate_forecast(
    plant_id: int,
    horizon_minutes: int = Query(default=60, ge=5, le=1440),
    db: Session = Depends(get_db),
):
    plant = plant_service.get_plant(db, plant_id)
    return forecast_service.generate_forecast(db, plant=plant, horizon_minutes=horizon_minutes)


@router.get("/{plant_id}/probabilistic", response_model=ProbabilisticForecastResponse,
            summary="Probabilistic forecast with P10/P50/P90 bands and ramp/cloud-passage risk metrics")
def get_probabilistic_forecast(
    plant_id: int,
    horizon_minutes: int = Query(default=240, ge=15, le=1440, description="Forecast horizon in minutes"),
    interval_minutes: int = Query(default=15, ge=5, le=60, description="Interval resolution in minutes"),
    db: Session = Depends(get_db),
):
    plant = plant_service.get_plant(db, plant_id)
    return forecast_service.generate_probabilistic_forecast(
        db, plant=plant, horizon_minutes=horizon_minutes, interval_minutes=interval_minutes)


@router.get("/{plant_id}/online-status", response_model=OnlineAdapterStatusResponse,
            summary="Online residual adapter status for a plant (scaling factor, bias, RMSE)",
            tags=["Forecast", "Online Learning"])
def get_online_adapter_status(plant_id: int):
    adapter = get_registry().get_online_adapter(str(plant_id))
    return OnlineAdapterStatusResponse(**adapter.get_status())
