"""ROI engine: should we clean now or wait? Pure functions, see docs/solardoctor/ROI_METHOD.md."""
from __future__ import annotations

import math
from typing import Iterable, Optional

from .models import ASSUMPTION_LABEL, ForecastHour, RoiResult, RoiSettings, finite

CLEAN_NOW = "CLEAN NOW"
WAIT = "WAIT"
DAYS_PER_YEAR = 365.0


def cleaning_cost(s: RoiSettings) -> float:
    """modules x INR/module + water L x INR/L + labour."""
    return s.module_count * s.cleaning_cost_per_module_inr + water_per_clean(s) * s.water_cost_inr_per_l + s.labour_cost_inr


def water_per_clean(s: RoiSettings) -> float:
    return s.module_count * s.water_l_per_module


def payback_days(cost: float, inr_per_day: Optional[float]) -> Optional[float]:
    """cost / INR-per-day; None when INR/day is missing, zero or negative (never pays back)."""
    if inr_per_day is None or inr_per_day <= 0:
        return None
    return cost / inr_per_day


def optimal_interval_days(cost: float, rate_per_day: Optional[float], clean_value_inr_per_day: Optional[float]) -> Optional[float]:
    """T* = sqrt(2C / (r V)); None if r <= 0, V <= 0, C < 0 or any input is missing/non-finite."""
    c, r, v = finite(cost), finite(rate_per_day), finite(clean_value_inr_per_day)
    if c is None or r is None or v is None or r <= 0 or v <= 0 or c < 0:
        return None
    return math.sqrt(2 * c / (r * v))


def rain_outlook(forecast: Iterable[ForecastHour], threshold_pct: float, window_h: float):
    """Peak precipitation probability inside the window; returns (wait, peak_pct, hours_ahead_of_peak).

    Rows with missing/NaN probability or hours_ahead are ignored; window is inclusive (72 h counts, 73 h does not).
    """
    peak, at = None, None
    for h in forecast or ():
        p, t = finite(h.precip_probability_pct), finite(h.hours_ahead)
        if p is None or t is None or t < 0 or t > window_h:
            continue
        if peak is None or p > peak:
            peak, at = p, t
    return (peak is not None and peak >= threshold_pct), peak, at


def evaluate(expected_kwh_day, deficit_fraction, settings: RoiSettings,
             forecast: Iterable[ForecastHour] = (), soiling_rate_per_day: Optional[float] = None) -> RoiResult:
    """Clean-now-or-wait decision with every intermediate number.

    expected_kwh_day: clear-sky expected energy of the scope being cleaned.
    deficit_fraction: attributable deficit as a fraction of that energy (clamped to 0..1).
    soiling_rate_per_day: fraction/day (e.g. RdTools); falls back to settings.soiling_rate_per_day.
    """
    s = settings
    cost = round(cleaning_cost(s), 2)
    water = water_per_clean(s)
    rate = finite(soiling_rate_per_day) if soiling_rate_per_day is not None else finite(s.soiling_rate_per_day)
    assumptions = {
        "label": ASSUMPTION_LABEL,
        "tariff_inr_per_kwh": s.tariff_inr_per_kwh,
        "tariff_source": f"preset:{s.tariff_preset}" if s.tariff_preset else "custom",
        "module_count": s.module_count,
        "cleaning_cost_per_module_inr": s.cleaning_cost_per_module_inr,
        "water_l_per_module": s.water_l_per_module,
        "water_cost_inr_per_l": s.water_cost_inr_per_l,
        "labour_cost_inr": s.labour_cost_inr,
        "rain_prob_threshold_pct": s.rain_prob_threshold_pct,
        "rain_window_h": s.rain_window_h,
        "calendar_interval_days": s.calendar_interval_days,
        "max_payback_days": s.max_payback_days,
        "soiling_rate_per_day": rate,
    }
    kwh, frac = finite(expected_kwh_day), finite(deficit_fraction)
    if kwh is None or frac is None or kwh < 0:
        return RoiResult(WAIT, "Insufficient data: expected energy or attributable deficit is missing or invalid, "
                         "so no saving can be computed.", cleaning_cost_inr=cost, water_l_per_clean=water,
                         payback_label="unknown (missing inputs)", assumptions=assumptions)
    frac = min(max(frac, 0.0), 1.0)

    recoverable = kwh * frac
    inr_day = recoverable * s.tariff_inr_per_kwh
    v = kwh * s.tariff_inr_per_kwh
    pay = payback_days(cost, inr_day)
    never = pay is None
    t_star = optimal_interval_days(cost, rate, v)
    if t_star is not None:
        note = "heuristic: linear soiling loss, constant cost per clean"
    else:
        note = "undefined: needs soiling rate > 0, clean-production value > 0 and a cleaning cost"
    saved = None
    if t_star is not None and t_star > 0:
        saved = water * (DAYS_PER_YEAR / s.calendar_interval_days - DAYS_PER_YEAR / t_star)

    rain, peak, at = rain_outlook(forecast, s.rain_prob_threshold_pct, s.rain_window_h)
    if rain:
        decision = WAIT
        reason = (f"Rain likely: {peak:g}% precipitation probability at +{at:g} h "
                  f"(threshold {s.rain_prob_threshold_pct:g}% within {s.rain_window_h:g} h); rain may clean the panels for free.")
    elif never:
        decision = WAIT
        reason = "Cleaning never pays back: the recoverable value is 0 or negative at this tariff and deficit."
    elif pay <= s.max_payback_days:
        decision = CLEAN_NOW
        reason = (f"Cleaning costs Rs {cost:,.2f} and recovers about Rs {inr_day:,.2f}/day: "
                  f"pays back in {pay:.1f} days (limit {s.max_payback_days:g} days).")
    else:
        decision = WAIT
        reason = (f"Payback of {pay:.1f} days exceeds the {s.max_payback_days:g}-day limit "
                  f"(cost Rs {cost:,.2f}, recovers Rs {inr_day:,.2f}/day).")
    return RoiResult(
        decision=decision, reason=reason,
        expected_kwh_day=round(kwh, 3), deficit_fraction=round(frac, 6),
        recoverable_kwh_day=round(recoverable, 3), inr_per_day=round(inr_day, 2),
        clean_value_inr_per_day=round(v, 2), cleaning_cost_inr=cost, water_l_per_clean=water,
        payback_days=None if never else round(pay, 2),
        payback_label="never pays back" if never else f"{pay:.1f} days",
        never_pays_back=never, rain_wait=rain, rain_peak_probability_pct=peak, rain_peak_hours_ahead=at,
        optimal_interval_days=None if t_star is None else round(t_star, 2), optimal_interval_note=note,
        water_saved_l_per_year=None if saved is None else round(saved, 1), assumptions=assumptions)
