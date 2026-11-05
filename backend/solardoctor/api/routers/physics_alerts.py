"""Plant (telemetry) alerts: SolarPulse /alerts and /anomaly endpoints.

Clash with Axalon's alerts router (``POST /alerts/test``, inspection-fault notification test) is
resolved by path: Axalon keeps ``/alerts/test``; this router adds ``GET /alerts``,
``GET /alerts/{id}`` and ``PATCH /alerts/{id}/resolve`` (distinct method/path shapes), backed by
the ``plant_alerts`` table. See docs/solardoctor/DECISIONS.md.
"""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from solardoctor.physics import anomaly_service
from solardoctor.physics.deps import get_db
from solardoctor.physics.schemas.alert import AlertResponse, AlertThresholdRequest

router = APIRouter(tags=["Alerts"])


@router.get("/alerts", response_model=List[AlertResponse], summary="List plant alerts with optional filters")
def list_alerts(
    plant_id: Optional[int] = Query(default=None),
    severity: Optional[str] = Query(default=None, description="INFO | WARNING | CRITICAL"),
    is_resolved: Optional[bool] = Query(default=None),
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return anomaly_service.get_alerts(db, plant_id=plant_id, severity=severity, is_resolved=is_resolved,
                                      start=start, end=end, limit=limit)


@router.get("/alerts/{alert_id}", response_model=AlertResponse, summary="Get a specific plant alert")
def get_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = anomaly_service.get_alert_by_id(db, alert_id)
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Alert {alert_id} not found")
    return alert


@router.patch("/alerts/{alert_id}/resolve", response_model=AlertResponse, summary="Mark a plant alert resolved")
def resolve_alert(alert_id: int, db: Session = Depends(get_db)):
    alert = anomaly_service.resolve_alert(db, alert_id)
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Alert {alert_id} not found")
    return alert


@router.get("/anomaly/{plant_id}", response_model=List[AlertResponse], summary="Anomaly alerts for a plant")
def get_plant_anomalies(
    plant_id: int,
    severity: Optional[str] = Query(default=None),
    is_resolved: Optional[bool] = Query(default=None),
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    return anomaly_service.get_alerts(db, plant_id=plant_id, severity=severity, is_resolved=is_resolved,
                                      start=start, end=end, limit=limit)


@router.post("/anomaly/threshold", summary="Configure anomaly detection thresholds for a plant")
def set_anomaly_threshold(request: AlertThresholdRequest) -> dict:
    anomaly_service.set_threshold(request)
    return {
        "detail": "Thresholds updated", "plant_id": request.plant_id,
        "warning_threshold_percent": request.warning_threshold_percent,
        "critical_threshold_percent": request.critical_threshold_percent,
    }
