# Adapted from SolarPulseAI (https://github.com/anugrahpatil-creator/SolarPulseAI)
# MIT License, Copyright (c) 2026 anugrahpatil-creator. See THIRD_PARTY_NOTICES.md.
# Modified for SolarDoctor: moved to solardoctor.physics.schemas.
"""
app/schemas/alert.py

Pydantic v2 schemas for anomaly alerts.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional

from pydantic import AliasChoices, BaseModel, BeforeValidator, ConfigDict, Field
from typing_extensions import Annotated


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
    # deficit detector (migration 0012); evidence is the parsed evidence_json column
    scope: str = "plant"
    inverter_id: Optional[int] = None
    string_id: Optional[int] = None
    baseline: Optional[str] = None
    evidence: Annotated[Optional[dict[str, Any]], BeforeValidator(lambda v: json.loads(v) if isinstance(v, str) else v)] = Field(
        default=None, validation_alias=AliasChoices("evidence", "evidence_json"))


class AlertUpdate(BaseModel):
    is_resolved: bool = True


class AlertThresholdRequest(BaseModel):
    plant_id: int
    warning_threshold_percent: float = Field(default=10.0, ge=0.0, le=100.0)
    critical_threshold_percent: float = Field(default=25.0, ge=0.0, le=100.0)
