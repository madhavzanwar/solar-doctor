# Adapted from SolarPulseAI (https://github.com/anugrahpatil-creator/SolarPulseAI)
# MIT License, Copyright (c) 2026 anugrahpatil-creator. See THIRD_PARTY_NOTICES.md.
# Modified for SolarDoctor: moved to solardoctor.physics.schemas.
"""
app/schemas/plant.py

Pydantic v2 schemas for Plant and PlantConfig.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _check_tz(v):
    if v is None:
        return v
    try:
        ZoneInfo(v)
    except (ZoneInfoNotFoundError, ValueError, KeyError):
        raise ValueError(f"unknown IANA timezone: {v!r}")
    return v


class PlantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=256)
    location: Optional[str] = Field(default=None, max_length=512)
    latitude: float = Field(..., ge=-90.0, le=90.0)
    longitude: float = Field(..., ge=-180.0, le=180.0)
    timezone: str = Field(default="UTC", max_length=64)
    capacity_kw: float = Field(..., gt=0)
    inverter_capacity_kw: float = Field(..., gt=0)
    module_count: Optional[int] = Field(default=None, gt=0)
    # SolarDoctor additions (all optional; SolarPulse clients can omit them)
    park_id: Optional[str] = Field(default=None, max_length=200, description="Axalon Park to link 1:1")
    altitude_m: float = 0.0
    tilt: float = Field(default=20.0, ge=0.0, le=90.0)
    azimuth: float = Field(default=180.0, ge=0.0, le=360.0)
    module_wp: Optional[float] = Field(default=None, gt=0)
    temp_coeff: float = Field(default=-0.004, le=0.0, description="Pmp temperature coefficient, 1/degC")
    tariff_inr_kwh: Optional[float] = Field(default=None, ge=0)
    source: str = Field(default="USER", max_length=32)

    _tz = field_validator("timezone")(_check_tz)


class PlantUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    location: Optional[str] = Field(default=None, max_length=512)
    latitude: Optional[float] = Field(default=None, ge=-90.0, le=90.0)
    longitude: Optional[float] = Field(default=None, ge=-180.0, le=180.0)
    timezone: Optional[str] = Field(default=None, max_length=64)
    capacity_kw: Optional[float] = Field(default=None, gt=0)
    inverter_capacity_kw: Optional[float] = Field(default=None, gt=0)
    module_count: Optional[int] = Field(default=None, gt=0)
    is_active: Optional[bool] = None
    park_id: Optional[str] = None
    altitude_m: Optional[float] = None
    module_wp: Optional[float] = Field(default=None, gt=0)
    temp_coeff: Optional[float] = Field(default=None, le=0.0)
    tariff_inr_kwh: Optional[float] = Field(default=None, ge=0)

    _tz = field_validator("timezone")(_check_tz)


class PlantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    location: Optional[str] = None
    latitude: float
    longitude: float
    timezone: str
    capacity_kw: float
    inverter_capacity_kw: float
    module_count: Optional[int] = None
    is_active: bool
    park_id: Optional[str] = None
    source: str = "USER"
    tariff_inr_kwh: Optional[float] = None
    created_at: datetime
    updated_at: datetime


class PlantConfigCreate(BaseModel):
    tilt: float = Field(default=20.0, ge=0.0, le=90.0)
    azimuth: float = Field(default=180.0, ge=0.0, le=360.0)
    efficiency: float = Field(default=0.18, gt=0.0, le=1.0)
    soiling_threshold: float = Field(default=5.0, ge=0.0, le=100.0)
    clipping_threshold: float = Field(default=95.0, ge=0.0, le=100.0)
    forecast_horizon_minutes: int = Field(default=60, ge=5, le=1440)


class PlantConfigUpdate(BaseModel):
    tilt: Optional[float] = Field(default=None, ge=0.0, le=90.0)
    azimuth: Optional[float] = Field(default=None, ge=0.0, le=360.0)
    efficiency: Optional[float] = Field(default=None, gt=0.0, le=1.0)
    soiling_threshold: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    clipping_threshold: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    forecast_horizon_minutes: Optional[int] = Field(default=None, ge=5, le=1440)


class PlantConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    plant_id: int
    tilt: float
    azimuth: float
    efficiency: float
    soiling_threshold: float
    clipping_threshold: float
    forecast_horizon_minutes: int
    created_at: datetime
    updated_at: datetime
