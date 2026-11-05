# Adapted from SolarPulseAI (https://github.com/anugrahpatil-creator/SolarPulseAI)
# MIT License, Copyright (c) 2026 anugrahpatil-creator. See THIRD_PARTY_NOTICES.md.
# Modified for SolarDoctor: moved to solardoctor.physics.schemas.
"""
app/schemas/alert.py

Pydantic v2 schemas for anomaly alerts.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class AlertResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plant_id: int
    timestamp: datetime
    alert_type: str
    severity: str
    message: str
    expected_power_kw: Optional[float] = None
    actual_power_kw: Optional[float] = None
    deviation_percent: Optional[float] = None
    is_resolved: bool
    resolved_at: Optional[datetime] = None
    created_at: datetime


class AlertUpdate(BaseModel):
    is_resolved: bool = True


class AlertThresholdRequest(BaseModel):
    plant_id: int
    warning_threshold_percent: float = Field(default=10.0, ge=0.0, le=100.0)
    critical_threshold_percent: float = Field(default=25.0, ge=0.0, le=100.0)
