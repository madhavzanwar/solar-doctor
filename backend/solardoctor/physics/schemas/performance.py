"""Pydantic v2 response/request models for /performance and /strings/{id}/peers (physics deficit engine)."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, model_validator

from solardoctor.physics.schemas.alert import AlertResponse


class HourlyPoint(BaseModel):
    ts: datetime
    expected_kw: Optional[float] = None
    actual_kw: Optional[float] = None
    pi: Optional[float] = Field(default=None, description="actual / expected on usable samples; null when none")
    clear: bool = Field(description="clear-sky period (QC)")
    usable: bool = Field(description="passed every QC gate; only these hours feed PI and alerts")
    source: str = Field(description="irradiance provenance: site_sensor | nasa_power | openmeteo | clearsky_model")


class DeficitEventOut(BaseModel):
    scope: Literal["plant", "inverter", "string"]
    scope_id: Optional[int] = None
    name: str
    severity: Literal["CRITICAL", "WARNING", "INFO"]
    start: datetime
    end: datetime
    pi_median: float
    expected_kw_mean: float
    actual_kw_mean: float
    deviation_percent: float
    clear_hours: int
    peer_z: Optional[float] = None
    evidence: dict[str, Any] = {}


class PerformanceResponse(BaseModel):
    plant_id: int
    baseline: str
    start: datetime
    end: datetime
    status: str = Field(description="ok | no_telemetry")
    data_source: Optional[str] = None
    series: list[HourlyPoint] = []
    events: list[DeficitEventOut] = Field(default=[], description="computed for this window, not persisted")
    open_alerts: list[AlertResponse] = []
    soiling: Optional[dict[str, Any]] = Field(default=None, description="latest plant_analytics row, else null")
    degradation: Optional[dict[str, Any]] = None
    qc: dict[str, Any] = {}
    provenance: dict[str, int] = {}


class ScanResponse(BaseModel):
    status: str = Field(description="ok | no_telemetry")
    baseline: Optional[str] = None
    data_source: Optional[str] = None
    events: list[DeficitEventOut] = []
    alert_ids: list[int] = []
    qc: dict[str, Any] = {}
    provenance: dict[str, int] = {}


class ThresholdsRequest(BaseModel):
    pi_warning: float
    pi_critical: float
    deficit_min_clear_hours: int = Field(ge=1, le=24)

    @model_validator(mode="after")
    def _ordered(self) -> "ThresholdsRequest":
        if not 0 < self.pi_critical < self.pi_warning <= 1:
            raise ValueError("require 0 < pi_critical < pi_warning <= 1")
        return self


class ThresholdsResponse(ThresholdsRequest):
    plant_id: int


class PeerValue(BaseModel):
    string_id: int
    name: str
    normalised_yield: float = Field(description="median hourly PI over clear usable hours")
    peer_z: Optional[float] = None
    clear_hours: int


class PeersResponse(BaseModel):
    string_id: int
    plant_id: int
    start: datetime
    end: datetime
    status: str = Field(description="ok | no_telemetry | no_clear_hours_for_string")
    normalised_yield: Optional[float] = None
    plant_median: Optional[float] = Field(default=None, description="median of the peer strings' normalised yield")
    peer_z: Optional[float] = Field(default=None, description="robust z (MAD); null with fewer than 4 comparable strings")
    peers: list[PeerValue] = []


