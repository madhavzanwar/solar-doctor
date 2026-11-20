"""Fusion engine: reconcile telemetry and photo evidence using the YAML decision table."""
from __future__ import annotations

from functools import lru_cache
from types import MappingProxyType
from importlib import resources
from typing import Iterable, Optional

import yaml

from solardoctor.roi import ForecastHour, evaluate
from solardoctor.roi.models import finite

from .models import CLASSES, FusionSettings, FusionVerdict, PhotoEvidence, Severity, TelemetryEvidence

_LABELS = {"dusty": "dust", "bird_drop": "bird droppings", "electrical_damage": "electrical damage",
           "physical_damage": "physical damage", "snow_covered": "snow cover", "clean": "clean panels"}


@lru_cache(maxsize=1)
def load_rules() -> tuple[MappingProxyType, ...]:
    """Spec rows then fallback rows, sorted by precedence. Loaded once."""
    data = yaml.safe_load(resources.files(__package__).joinpath("rules.yaml").read_text(encoding="utf-8"))
    rows = list(data["rules"]) + list(data.get("fallback_rules", []))
    return tuple(_freeze(r) for r in sorted(rows, key=lambda r: r["precedence"]))


def _freeze(v):
    if isinstance(v, dict):
        return MappingProxyType({k: _freeze(x) for k, x in v.items()})
    if isinstance(v, list):
        return tuple(_freeze(x) for x in v)
    return v


def _as_list(v) -> list:
    return v if isinstance(v, (list, tuple)) else [v]


def telemetry_state(t: Optional[TelemetryEvidence]) -> tuple[str, str]:
    """(state, issue). Deficit = open alert WARNING/CRITICAL; INFO is only a peer hint."""
    if t is None:
        return "inconclusive", "no telemetry evidence"
    if t.status != "ok":
        return "inconclusive", f"telemetry status {t.status}"
    hours = finite(t.usable_clear_hours)  # None / NaN / junk = unknown
    if hours is not None and hours <= 0:
        return "inconclusive", "no QC-usable clear-sky hours"
    if hours is None and t.deficit_severity is None:
        return "inconclusive", "clear-sky coverage unknown"
    if str(t.deficit_severity or "").upper() in ("WARNING", "CRITICAL"):
        return "deficit", ""
    return "no_deficit", ""


def photo_state(p: Optional[PhotoEvidence], threshold: float) -> tuple[str, str]:
    """(state, issue). Confidence exactly at the threshold is accepted."""
    if p is None:
        return "unclear", "no photo"
    if p.is_ood:
        return "unclear", "out of distribution"
    conf = finite(p.confidence)
    if conf is None:
        return "unclear", "confidence missing"
    if conf < threshold:
        return "unclear", f"confidence {conf:.0%} below {threshold:.0%}"
    if p.needs_field_check:
        return "unclear", p.field_check_reason or "model flagged field check"
    cls = str(p.predicted_class or "").strip().lower().replace("-", "_")
    if cls not in CLASSES:
        return "unclear", f"unknown class {p.predicted_class!r}"
    return cls, ""


def _snow_decision(forecast: Iterable[ForecastHour], s: FusionSettings) -> tuple[str, str]:
    temps = [(finite(h.temperature_c), finite(h.hours_ahead)) for h in forecast or ()]
    warm = [(c, t) for c, t in temps if c is not None and t is not None and 0 <= t <= s.melt_window_h and c >= s.melt_temp_c]
    if warm:
        c, t = min(warm, key=lambda x: x[1])
        return "WAIT", f"Melt forecast: {c:g} C at +{t:g} h, so the snow should clear by itself."
    return "CLEAR IF SAFE", "No melt in the forecast; clear the snow only if it is safe to reach the panels."


def fuse(telemetry: Optional[TelemetryEvidence], photo: Optional[PhotoEvidence], settings: FusionSettings,
         *, forecast: Iterable[ForecastHour] = ()) -> FusionVerdict:
    forecast = tuple(forecast or ())
    t_state, t_issue = telemetry_state(telemetry)
    p_state, p_issue = photo_state(photo, settings.conf_threshold)
    row = next(r for r in load_rules()
               if ("any" in _as_list(r["telemetry"]) or t_state in _as_list(r["telemetry"]))
               and ("any" in _as_list(r["photo"]) or p_state in _as_list(r["photo"])))

    conf = finite(photo.confidence) if photo is not None else None
    conf = 0.0 if row["confidence_basis"] == "zero" or conf is None else conf
    dev = finite(telemetry.deviation_percent) if telemetry else None
    if dev is None and telemetry and finite(telemetry.attributable_deficit_fraction) is not None:
        dev = telemetry.attributable_deficit_fraction * 100
    ctx = {"photo_issue": p_issue, "telemetry_issue": t_issue, "recheck_days": settings.recheck_days,
           "photo_class_label": _LABELS.get(p_state, p_state), "photo_conf_pct": f"{conf:.0%} confidence",
           "deficit_pct": f"{dev:.1f}%" if dev is not None else "an unquantified margin"}

    action, roi = row.get("action"), None
    if row.get("decider") == "roi":
        roi = evaluate(telemetry.expected_kwh_day, telemetry.attributable_deficit_fraction, settings.roi, forecast,
                       soiling_rate_per_day=telemetry.soiling_loss_rate_per_day,
                       soiling_rate_source=telemetry.soiling_rate_source)
        action, ctx["roi_reason"] = roi.decision, roi.reason
    elif row.get("decider") == "snow":
        action, ctx["snow_reason"] = _snow_decision(forecast, settings)

    sev = row["severity"]
    sev = row.get("severity_by_action", {}).get(action, sev)
    # a WAIT never escalates: CRITICAL auto-creates work orders
    if row.get("escalate_on_critical_telemetry") and action != "WAIT" and telemetry and str(telemetry.deficit_severity).upper() == "CRITICAL":
        sev = "CRITICAL"
    return FusionVerdict(verdict=row["verdict"], action=action, confidence=conf, reason=row["reason"].format_map(ctx),
                         severity=Severity(sev), rule_id=row["id"], telemetry_state=t_state, photo_state=p_state, roi=roi,
                         roi_incomplete=bool(roi and roi.incomplete))
