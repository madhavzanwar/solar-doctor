"""Input/output types for the fusion engine. Fields mirror the physics-deficit and vision-predict contracts."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from solardoctor.roi import RoiResult, RoiSettings

CLASSES = ("clean", "dusty", "bird_drop", "snow_covered", "electrical_damage", "physical_damage")


class Severity(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(frozen=True)
class TelemetryEvidence:
    """Telemetry side. Adapter notes in docs/solardoctor/interfaces/fusion-roi.md."""
    status: str = "ok"                              # physics scan/performance `status`: ok | no_telemetry | ...
    usable_clear_hours: Optional[int] = None        # physics qc.plant.usable; 0 = cloudy / no QC data; None = unknown
    deficit_severity: Optional[str] = None          # open deficit alert: None | INFO | WARNING | CRITICAL
    pi_median: Optional[float] = None               # performance index (actual / expected)
    deviation_percent: Optional[float] = None       # (expected - actual) / expected x 100
    expected_kwh_day: Optional[float] = None        # clear-sky expected energy of the scope
    attributable_deficit_fraction: Optional[float] = None  # fraction of that energy lost (see adapter note)
    soiling_loss_rate_per_day: Optional[float] = None      # fraction/day, positive = loss (soiling_analysis)


@dataclass(frozen=True)
class PhotoEvidence:
    """Photo side, mirrors vision PredictResult."""
    predicted_class: str
    confidence: Optional[float]                     # calibrated max probability
    is_ood: bool = False
    needs_field_check: bool = False
    field_check_reason: Optional[str] = None        # null | out_of_distribution | low_confidence
    model_version: Optional[str] = None


@dataclass(frozen=True)
class FusionSettings:
    roi: RoiSettings
    conf_threshold: float = 0.6        # photo confidence below this is "unclear" (exactly 0.6 is accepted)
    recheck_days: int = 7              # "WAIT, re-check in N days"
    melt_temp_c: float = 2.0           # forecast temperature at or above this melts snow
    melt_window_h: float = 48.0        # how far ahead a melt counts as "WAIT"


@dataclass(frozen=True)
class FusionVerdict:
    verdict: str
    action: str
    confidence: float
    reason: str
    severity: Severity
    rule_id: str
    telemetry_state: str               # deficit | no_deficit | inconclusive
    photo_state: str                   # unclear | one of CLASSES
    roi: Optional[RoiResult] = None    # set only by the soiling row
