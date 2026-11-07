"""Input/output types for the ROI engine. Pure data, no I/O. Money is in INR."""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

# Editable starting points, never facts: every output labels the tariff as a user assumption.
TARIFF_PRESETS: dict[str, float] = {"utility_ppa": 2.6, "c_and_i": 6.5, "residential": 8.0}

ASSUMPTION_LABEL = "user assumption (editable)"


def finite(x) -> Optional[float]:
    """float(x) if it is a finite real number, else None (None, NaN, inf, bool, strings)."""
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _nonneg(name: str, x) -> float:
    v = finite(x)
    if v is None or v < 0:
        raise ValueError(f"{name} must be a finite number >= 0, got {x!r}")
    return v


@dataclass(frozen=True)
class ForecastHour:
    """One hourly forecast row (Open-Meteo style). `hours_ahead` is relative to now (0 = this hour)."""
    hours_ahead: float
    precip_probability_pct: Optional[float] = None  # 0..100
    temperature_c: Optional[float] = None


@dataclass(frozen=True)
class RoiSettings:
    """Plant-level ROI inputs (DESIGN.md 8.4). All monetary values are user assumptions."""
    tariff_inr_per_kwh: float = TARIFF_PRESETS["c_and_i"]
    tariff_preset: Optional[str] = "c_and_i"  # None = custom value
    module_count: int = 0
    cleaning_cost_per_module_inr: float = 0.0
    water_l_per_module: float = 0.0
    water_cost_inr_per_l: float = 0.0
    labour_cost_inr: float = 0.0
    soiling_rate_per_day: Optional[float] = None  # fraction/day; RdTools value overrides via evaluate()
    rain_prob_threshold_pct: float = 60.0
    rain_window_h: float = 72.0
    calendar_interval_days: float = 15.0
    # Assumption: clean now when the clean pays for itself within this many days (spec gives no number).
    max_payback_days: float = 30.0

    def __post_init__(self) -> None:
        for n in ("tariff_inr_per_kwh", "cleaning_cost_per_module_inr", "water_l_per_module",
                  "water_cost_inr_per_l", "labour_cost_inr", "rain_window_h", "max_payback_days"):
            _nonneg(n, getattr(self, n))
        if finite(self.module_count) is None or self.module_count < 0:
            raise ValueError(f"module_count must be >= 0, got {self.module_count!r}")
        if not (finite(self.rain_prob_threshold_pct) is not None and 0 <= self.rain_prob_threshold_pct <= 100):
            raise ValueError("rain_prob_threshold_pct must be within 0..100")
        cal = finite(self.calendar_interval_days)
        if cal is None or cal <= 0:
            raise ValueError("calendar_interval_days must be > 0")
        if self.soiling_rate_per_day is not None and finite(self.soiling_rate_per_day) is None:
            raise ValueError("soiling_rate_per_day must be finite or None")

    @classmethod
    def from_preset(cls, preset: str, **kw) -> "RoiSettings":
        return cls(tariff_inr_per_kwh=TARIFF_PRESETS[preset], tariff_preset=preset, **kw)


@dataclass(frozen=True)
class RoiResult:
    decision: str  # "CLEAN NOW" | "WAIT"
    reason: str
    # intermediates; None where an input was missing or the quantity is undefined
    expected_kwh_day: Optional[float] = None
    deficit_fraction: Optional[float] = None
    recoverable_kwh_day: Optional[float] = None
    inr_per_day: Optional[float] = None
    clean_value_inr_per_day: Optional[float] = None  # V in T*: value of a day of clean production
    cleaning_cost_inr: Optional[float] = None
    water_l_per_clean: Optional[float] = None
    payback_days: Optional[float] = None
    payback_label: str = ""  # human text, e.g. "never pays back"
    never_pays_back: bool = False
    rain_wait: bool = False
    rain_peak_probability_pct: Optional[float] = None
    rain_peak_hours_ahead: Optional[float] = None
    optimal_interval_days: Optional[float] = None
    optimal_interval_note: str = ""
    water_saved_l_per_year: Optional[float] = None  # signed; negative = uses more than calendar schedule
    incomplete: bool = False  # True when inputs or cost config were missing: no saving/payback was computed
    soiling_rate_per_day: Optional[float] = None
    soiling_rate_source: str = ""  # e.g. "pvlib_kimber assumed default"; T* is a heuristic on this rate
    assumptions: dict = field(default_factory=dict)
