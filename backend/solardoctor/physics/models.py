# Table layout adapted from SolarPulseAI app/models/* (MIT, (c) 2026 anugrahpatil-creator);
# see THIRD_PARTY_NOTICES.md. Converted to SolarDoctor's single sync declarative Base.
"""ORM models for the physics / forecasting side of SolarDoctor.

One ``Base`` (``solardoctor.db.models.Base``), one Alembic history (revision 0011).

Naming: Axalon already owns the ``/alerts`` HTTP router (test delivery) and an alert
module, so the physics alert table is ``plant_alerts``. SolarPulse's ``PlantConfig``
(tilt/azimuth/efficiency/thresholds) is folded into ``plants`` columns; the API still
exposes it as a separate ``/plants/{id}/config`` resource.

``Park`` <-> ``Plant`` is 1:1 via ``plants.park_id`` (unique FK -> ``parks.id``), so
thermal inspections, panel faults and work orders (which hang off ``parks``) attach to
plants through ``plant.park`` / ``park.plant``.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, backref, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from solardoctor.db.models import Base


class UTCDateTime(TypeDecorator):
    """Timezone-aware UTC datetimes on every backend (SQLite drops tzinfo)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


# BigInteger PKs must stay INTEGER on SQLite to autoincrement.
_BigPk = BigInteger().with_variant(Integer, "sqlite")

SOURCE_USER = "USER"
SOURCE_SIMULATED = "SIMULATED"
SOURCE_PVDAQ = "PVDAQ"


class Plant(Base):
    __tablename__ = "plants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    park_id: Mapped[Optional[str]] = mapped_column(
        String, ForeignKey("parks.id", ondelete="SET NULL"), unique=True, nullable=True
    )
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    location: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    lat: Mapped[float] = mapped_column(Float, nullable=False)
    lon: Mapped[float] = mapped_column(Float, nullable=False)
    tz: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)
    altitude_m: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    tilt: Mapped[float] = mapped_column(Float, default=20.0, nullable=False)
    azimuth: Mapped[float] = mapped_column(Float, default=180.0, nullable=False)
    dc_kw: Mapped[float] = mapped_column(Float, nullable=False)
    ac_kw: Mapped[float] = mapped_column(Float, nullable=False)
    module_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    module_wp: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    temp_coeff: Mapped[float] = mapped_column(Float, default=-0.004, nullable=False)  # 1/degC of Pmp
    tariff_inr_kwh: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default=SOURCE_USER, nullable=False)
    # SolarPulse PlantConfig fields
    efficiency: Mapped[float] = mapped_column(Float, default=0.18, nullable=False)
    soiling_threshold: Mapped[float] = mapped_column(Float, default=5.0, nullable=False)
    clipping_threshold: Mapped[float] = mapped_column(Float, default=95.0, nullable=False)
    forecast_horizon_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        UTCDateTime, default=utcnow, onupdate=utcnow, nullable=False
    )

    park = relationship("Park", backref=backref("plant", uselist=False))
    inverters = relationship("Inverter", back_populates="plant", cascade="all, delete-orphan")
    strings = relationship("PvString", back_populates="plant", cascade="all, delete-orphan")


class Inverter(Base):
    __tablename__ = "inverters"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    ac_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    vendor: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)

    plant = relationship("Plant", back_populates="inverters")


class PvString(Base):
    __tablename__ = "strings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plants.id", ondelete="CASCADE"), nullable=False, index=True
    )
    inverter_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("inverters.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    module_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    plant = relationship("Plant", back_populates="strings")


class Telemetry(Base):
    __tablename__ = "telemetry"
    __table_args__ = (Index("ix_telemetry_plant_ts", "plant_id", "ts"),)

    id: Mapped[int] = mapped_column(_BigPk, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    plant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plants.id", ondelete="CASCADE"), nullable=False
    )
    inverter_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("inverters.id", ondelete="SET NULL"), nullable=True
    )
    string_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("strings.id", ondelete="SET NULL"), nullable=True
    )
    p_ac_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p_dc_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    v: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    i: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    poa_wm2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ghi_wm2: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    t_amb: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    t_mod: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    wind_ms: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    p_expected_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default=SOURCE_USER, nullable=False)


class Forecast(Base):
    __tablename__ = "forecasts"
    __table_args__ = (Index("ix_forecasts_plant_time", "plant_id", "forecast_time"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plants.id", ondelete="CASCADE"), nullable=False
    )
    forecast_time: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    generated_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    predicted_power_kw: Mapped[float] = mapped_column(Float, nullable=False)
    actual_power_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence_lower: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confidence_upper: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str] = mapped_column(String(64), default="1.0", nullable=False)
    physics_power_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    ml_power_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)


class PlantAlert(Base):
    """Telemetry-vs-expected shortfall alert (SolarPulse ``AnomalyAlert``)."""

    __tablename__ = "plant_alerts"
    __table_args__ = (Index("ix_plant_alerts_plant_ts", "plant_id", "timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plants.id", ondelete="CASCADE"), nullable=False
    )
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    alert_type: Mapped[str] = mapped_column(String(64), nullable=False)
    severity: Mapped[str] = mapped_column(String(32), nullable=False)  # INFO | WARNING | CRITICAL
    message: Mapped[str] = mapped_column(String(1024), nullable=False)
    expected_power_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    actual_power_kw: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    deviation_percent: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    is_resolved: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(UTCDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    source: Mapped[str] = mapped_column(String(32), default=SOURCE_USER, nullable=False)


class Diagnosis(Base):
    __tablename__ = "diagnoses"
    __table_args__ = (Index("ix_diagnoses_plant_ts", "plant_id", "timestamp"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    plant_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("plants.id", ondelete="CASCADE"), nullable=False
    )
    alert_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("plant_alerts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    timestamp: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    root_cause_category: Mapped[str] = mapped_column(String(64), nullable=False)
    root_cause_title: Mapped[str] = mapped_column(String(255), nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    inverter_error_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    estimated_loss_kw: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    financial_impact_per_day: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    urgency_level: Mapped[str] = mapped_column(String(32), default="MEDIUM", nullable=False)
    summary: Mapped[str] = mapped_column(String(1024), nullable=False)
    root_cause_details: Mapped[str] = mapped_column(Text, nullable=False)
    technician_steps_json: Mapped[str] = mapped_column(Text, nullable=False)
    safety_warning: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    preventative_advice: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)


class WeatherCache(Base):
    __tablename__ = "weather_cache"
    __table_args__ = (UniqueConstraint("lat_key", "lon_key", "kind", name="uq_weather_cache_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lat_key: Mapped[float] = mapped_column(Float, nullable=False)  # rounded to 0.1 deg
    lon_key: Mapped[float] = mapped_column(Float, nullable=False)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # current | forecast | nasa_power
    source: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(UTCDateTime, default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
