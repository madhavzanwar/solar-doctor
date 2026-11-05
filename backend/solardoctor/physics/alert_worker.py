# Adapted from SolarPulseAI app/workers/alert_worker.py
# (https://github.com/anugrahpatil-creator/SolarPulseAI), MIT License,
# Copyright (c) 2026 anugrahpatil-creator. See THIRD_PARTY_NOTICES.md.
# Modified for SolarDoctor: sync SQLAlchemy 2.0; telemetry table; pvlib expected power when no forecast.
"""Alert check: compare latest telemetry against expected power and persist a PlantAlert.

Expected power is the most recent stored forecast if there is one, else the pvlib/PVWatts physics
baseline at the telemetry timestamp. Notifications go through a pluggable adapter (log-only here).
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from solardoctor.physics import solar
from solardoctor.physics.anomaly_service import detect_and_persist_anomaly
from solardoctor.physics.models import Forecast, Plant, Telemetry

logger = logging.getLogger("solardoctor.physics.alerts")


class NotificationAdapter:
    def send(self, message: str, severity: str, plant_id: int) -> None:
        raise NotImplementedError


class LogNotificationAdapter(NotificationAdapter):
    def send(self, message: str, severity: str, plant_id: int) -> None:
        logger.info("[NOTIFICATION] plant=%s severity=%s message=%s", plant_id, severity, message)


def run_alert_check(db: Session, plant_id: int, lookback_minutes: int = 60,
                    adapter: Optional[NotificationAdapter] = None) -> int:
    """Returns the number of alerts created (0 or 1)."""
    since = datetime.now(tz=timezone.utc) - timedelta(minutes=lookback_minutes)
    plant = db.get(Plant, plant_id)
    tel = db.execute(
        select(Telemetry).where(Telemetry.plant_id == plant_id, Telemetry.ts >= since)
        .order_by(Telemetry.ts.desc()).limit(1)
    ).scalar_one_or_none()
    if plant is None or tel is None or tel.p_ac_kw is None:
        return 0

    forecast = db.execute(
        select(Forecast).where(Forecast.plant_id == plant_id, Forecast.forecast_time >= since)
        .order_by(Forecast.forecast_time.desc()).limit(1)
    ).scalar_one_or_none()
    if forecast is not None:
        expected = forecast.predicted_power_kw
    else:
        ghi = None if tel.ghi_wm2 is None else pd.Series([tel.ghi_wm2])
        expected = float(solar.expected_power(plant, [tel.ts], ghi=ghi)["p_ac_kw"].iloc[0])

    alert = detect_and_persist_anomaly(
        db, plant_id=plant_id, timestamp=tel.ts, expected_power_kw=expected,
        actual_power_kw=tel.p_ac_kw, source=tel.source,
    )
    if alert is None:
        return 0
    (adapter or LogNotificationAdapter()).send(alert.message, alert.severity, plant_id)
    if forecast is not None:
        forecast.actual_power_kw = tel.p_ac_kw
        db.commit()
    return 1
