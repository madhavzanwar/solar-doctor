# Adapted from SolarPulseAI (https://github.com/anugrahpatil-creator/SolarPulseAI)
# MIT License, Copyright (c) 2026 anugrahpatil-creator. See THIRD_PARTY_NOTICES.md.
# Modified for SolarDoctor: moved to solardoctor.physics.schemas.
"""
app/schemas/scada.py

Pydantic v2 schemas for SCADA readings.
"""

from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ScadaReadingCreate(BaseModel):
    plant_id: int
    timestamp: datetime
    power_kw: Optional[float] = Field(default=None, ge=0)
    irradiance_w_m2: Optional[float] = Field(default=None, ge=0)
    temperature_c: Optional[float] = None
    wind_speed_m_s: Optional[float] = Field(default=None, ge=0)
    module_temperature_c: Optional[float] = None
    inverter_power_kw: Optional[float] = Field(default=None, ge=0)
    expected_power_kw: Optional[float] = Field(default=None, ge=0)
    # SolarDoctor additions (optional)
    poa_wm2: Optional[float] = Field(default=None, ge=0)
    p_dc_kw: Optional[float] = Field(default=None, ge=0)
    v: Optional[float] = None
    i: Optional[float] = None
    inverter_id: Optional[int] = None
    string_id: Optional[int] = None
    source: str = "USER"


class ScadaReadingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plant_id: int
    timestamp: datetime
    power_kw: Optional[float] = None
    irradiance_w_m2: Optional[float] = None
    temperature_c: Optional[float] = None
    wind_speed_m_s: Optional[float] = None
    module_temperature_c: Optional[float] = None
    inverter_power_kw: Optional[float] = None
    expected_power_kw: Optional[float] = None
    created_at: datetime


MAX_BATCH_READINGS = 1000


class ScadaBatchCreate(BaseModel):
    readings: List[ScadaReadingCreate] = Field(..., max_length=MAX_BATCH_READINGS)
