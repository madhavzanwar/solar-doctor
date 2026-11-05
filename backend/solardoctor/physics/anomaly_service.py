# Adapted from SolarPulseAI app/services/anomaly_service.py
# (https://github.com/anugrahpatil-creator/SolarPulseAI), MIT License,
# Copyright (c) 2026 anugrahpatil-creator. See THIRD_PARTY_NOTICES.md.
# Modified for SolarDoctor: sync SQLAlchemy 2.0, PlantAlert table; thresholds/severity logic unchanged.
"""Shortfall detection and alert persistence.

Compares actual power against expected/forecast power and creates ``PlantAlert`` rows when the
deviation exceeds the configured thresholds (default WARNING >= 10 %, CRITICAL >= 25 %).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from solardoctor.physics.models import Plant, PlantAlert
from solardoctor.physics.tracker import is_tracker_plant
from solardoctor.physics.schemas.alert import AlertThresholdRequest

logger = logging.getLogger("solardoctor.physics.anomaly")

# In-memory threshold store per plant (as in SolarPulse; process-local).
_thresholds: dict[int, dict] = {}

DEFAULT_WARNING_THRESHOLD = 10.0   # percent
DEFAULT_CRITICAL_THRESHOLD = 25.0  # percent


def _get_thresholds(plant_id: int) -> dict:
    return _thresholds.get(
        plant_id, {"warning": DEFAULT_WARNING_THRESHOLD, "critical": DEFAULT_CRITICAL_THRESHOLD}
    )


def set_threshold(request: AlertThresholdRequest) -> None:
    _thresholds[request.plant_id] = {
        "warning": request.warning_threshold_percent,
        "critical": request.critical_threshold_percent,
    }


def calculate_deviation(expected_power_kw: float, actual_power_kw: float) -> Optional[float]:
    """Deviation in percent; None if expected is effectively zero."""
    if expected_power_kw is None or actual_power_kw is None:
        return None
    if abs(expected_power_kw) < 0.001:
        return None
    return ((expected_power_kw - actual_power_kw) / expected_power_kw) * 100.0


def _classify_severity(deviation_percent: float, thresholds: dict) -> Optional[str]:
    if deviation_percent >= thresholds["critical"]:
        return "CRITICAL"
    if deviation_percent >= thresholds["warning"]:
        return "WARNING"
    return None


def detect_and_persist_anomaly(
    db: Session,
    plant_id: int,
    timestamp: datetime,
    expected_power_kw: float,
    actual_power_kw: float,
    alert_type: str = "shortfall",
    source: str = "USER",
) -> Optional[PlantAlert]:
    plant = db.get(Plant, plant_id)
    if plant is not None and is_tracker_plant(plant):
        # Callers pass a fixed-tilt baseline/forecast as "expected"; a deficit against it is meaningless here.
        logger.info("No anomaly alert for tracker plant %s (fixed-tilt baseline invalid)", plant_id)
        return None
    deviation = calculate_deviation(expected_power_kw, actual_power_kw)
    if deviation is None:
        return None
    severity = _classify_severity(deviation, _get_thresholds(plant_id))
    if severity is None:
        return None
    alert = PlantAlert(
        plant_id=plant_id,
        timestamp=timestamp,
        alert_type=alert_type,
        severity=severity,
        message=(
            f"Power shortfall detected: expected={expected_power_kw:.2f} kW, "
            f"actual={actual_power_kw:.2f} kW, deviation={deviation:.1f}%"
        ),
        expected_power_kw=expected_power_kw,
        actual_power_kw=actual_power_kw,
        deviation_percent=round(deviation, 2),
        is_resolved=False,
        source=source,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    logger.warning("Anomaly alert created: plant=%s severity=%s deviation=%.1f%%", plant_id, severity, deviation)
    return alert


def get_alerts(
    db: Session,
    plant_id: Optional[int] = None,
    severity: Optional[str] = None,
    is_resolved: Optional[bool] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    limit: int = 200,
) -> List[PlantAlert]:
    q = select(PlantAlert)
    if plant_id is not None:
        q = q.where(PlantAlert.plant_id == plant_id)
    if severity is not None:
        q = q.where(PlantAlert.severity == severity.upper())
    if is_resolved is not None:
        q = q.where(PlantAlert.is_resolved == is_resolved)
    if start is not None:
        q = q.where(PlantAlert.timestamp >= start)
    if end is not None:
        q = q.where(PlantAlert.timestamp <= end)
    q = q.order_by(PlantAlert.timestamp.desc(), PlantAlert.id.desc()).limit(limit)
    return list(db.execute(q).scalars().all())


def get_alert_by_id(db: Session, alert_id: int) -> Optional[PlantAlert]:
    return db.get(PlantAlert, alert_id)


def resolve_alert(db: Session, alert_id: int) -> Optional[PlantAlert]:
    alert = get_alert_by_id(db, alert_id)
    if alert is None:
        return None
    alert.is_resolved = True
    alert.resolved_at = datetime.now(tz=timezone.utc)
    db.commit()
    db.refresh(alert)
    return alert
