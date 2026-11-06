"""Soiling and degradation analytics on daily irradiance-normalised energy (rdtools / pvlib).

``daily``: UTC-date indexed frame with ``actual_kwh`` and ``expected_kwh`` (summed over QC-usable clear hours, so
the ratio is a performance ratio against the part-A baseline) and ``insolation`` (kWh/m2 on the same hours).

Soiling: >= 60 days -> RdTools stochastic rate-and-recovery (``rdtools_srr``, label ``measured``); fewer days
with rain data -> ``pvlib.soiling.kimber`` (``pvlib_kimber``, label ``modelled``: assumed parameters, nothing is
fitted to the plant); otherwise ``insufficient_data``. Solar Data Tools' power-only fallback is not installed
(cvxpy stack), so with no irradiance-normalised energy at all the method is ``unavailable``.
"""
from __future__ import annotations

import json
import logging
import warnings
from datetime import date, datetime, timezone
from typing import Optional

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from solardoctor.physics.models import PlantAnalytics

logger = logging.getLogger("solardoctor.physics.soiling_analytics")

SRR_MIN_DAYS = 60
DEGRADATION_MIN_DAYS = 2 * 365
KIMBER = dict(cleaning_threshold=6.0, soiling_loss_rate=0.0015, grace_period=14, max_soiling=0.3)  # pvlib defaults
UNAVAILABLE = ("no irradiance-normalised daily energy; the Solar Data Tools power-only fallback is not installed "
               "(cvxpy dependency stack)")


def _normalised(daily: pd.DataFrame) -> pd.Series:
    e = daily["expected_kwh"].where(daily["expected_kwh"] > 0)
    return (daily["actual_kwh"] / e).replace([np.inf, -np.inf], np.nan).dropna()


def _kimber(rain: pd.Series) -> dict:
    from pvlib.soiling import kimber
    loss = kimber(rain.fillna(0.0), **KIMBER)
    eod = loss.resample("1D").last()
    cleaned = (eod == 0) & (eod.shift() > 0)  # soiling reset to zero by rain
    return {"status": "ok", "method": "pvlib_kimber", "label": "modelled",
            "soiling_ratio_p50": round(float(1 - loss.median()), 4), "soiling_ratio_latest": round(float(1 - loss.iloc[-1]), 4),
            "soiling_loss_rate_per_day": KIMBER["soiling_loss_rate"], "soiling_loss_rate_pct_per_day": KIMBER["soiling_loss_rate"] * 100,
            "cleaning_events": [d.date().isoformat() for d in cleaned.index[cleaned]],
            "parameters": KIMBER, "days": len(eod),
            "note": "Kimber model with assumed default parameters driven by NASA POWER rain; not fitted to this plant"}


def soiling_analysis(plant, daily: pd.DataFrame, rain_mm_hourly: Optional[pd.Series] = None, reps: int = 300) -> dict:
    norm = _normalised(daily) if len(daily) else pd.Series(dtype=float)
    base = {"plant_id": getattr(plant, "id", None), "days_with_data": int(len(norm))}
    if len(norm) >= SRR_MIN_DAYS:
        from rdtools.soiling import soiling_srr
        ins = daily["insolation"].reindex(norm.index)
        full = pd.date_range(norm.index.min(), norm.index.max(), freq="D", tz=norm.index.tz)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                sr, ci, info = soiling_srr(norm.reindex(full), ins.reindex(full), reps=reps)
            except Exception as exc:  # rdtools raises ValueError when no valid soiling interval exists
                if rain_mm_hourly is not None and len(rain_mm_hourly.dropna()):
                    return {**base, **_kimber(rain_mm_hourly), "note": f"rdtools SRR found no usable interval ({exc}); "
                            "Kimber model with assumed default parameters driven by NASA POWER rain, not fitted to this plant"}
                return {**base, "status": "insufficient_data", "method": "rdtools_srr", "label": "measured",
                        "reason": f"rdtools SRR found no usable soiling interval: {exc}"}
        iv = info["soiling_interval_summary"]
        ok = iv[iv["valid"]]
        ci_rate = ([round(float(-ok["soiling_rate_high"].median()), 6), round(float(-ok["soiling_rate_low"].median()), 6)]
                   if len(ok) >= 2 else None)  # one interval has no spread: a [r, r] CI would be false precision
        note = None if ci_rate else "fewer than 2 valid soiling intervals: no rate confidence interval"
        return {**base, "status": "ok", "method": "rdtools_srr", "label": "measured", "note": note,
                "soiling_ratio_p50": round(float(sr), 4), "soiling_ratio_ci": [round(float(v), 4) for v in ci],
                "soiling_loss_rate_per_day": round(float(-ok["soiling_rate"].median()), 6),
                "soiling_loss_rate_ci_per_day": ci_rate,
                "soiling_loss_rate_pct_per_day": round(float(-ok["soiling_rate"].median()) * 100, 4),
                "cleaning_events": [pd.Timestamp(t).date().isoformat() for t in iv["start"].iloc[1:][iv["valid"].iloc[1:]]],
                "intervals": int(len(ok)), "ci_level_pct": 68.2}
    if rain_mm_hourly is not None and len(rain_mm_hourly.dropna()):
        return {**base, **_kimber(rain_mm_hourly)}
    if not len(norm):
        return {**base, "status": "unavailable", "method": "unavailable", "label": "none", "reason": UNAVAILABLE}
    return {**base, "status": "insufficient_data", "method": "none", "label": "none",
            "reason": f"{len(norm)} days of normalised energy (< {SRR_MIN_DAYS}) and no rain data for the Kimber model"}


def degradation_analysis(plant, daily: pd.DataFrame) -> dict:
    norm = _normalised(daily) if len(daily) else pd.Series(dtype=float)
    days = int((norm.index.max() - norm.index.min()).days + 1) if len(norm) else 0
    base = {"plant_id": getattr(plant, "id", None), "method": "rdtools_yoy", "label": "measured", "days_available": days}
    if days < DEGRADATION_MIN_DAYS:
        return {**base, "status": "insufficient_data", "reason": f"{days} days; year-on-year needs >= {DEGRADATION_MIN_DAYS}"}
    from rdtools.degradation import degradation_year_on_year
    full = norm.reindex(pd.date_range(norm.index.min(), norm.index.max(), freq="D", tz=norm.index.tz))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            rate, ci, _ = degradation_year_on_year(full)
        except ValueError as exc:  # e.g. sparse days: no year-over-year pairs
            return {**base, "status": "insufficient_data", "reason": f"rdtools year-on-year found no usable data: {exc}"}
    return {**base, "status": "ok", "rate_pct_per_year": round(float(rate), 4), "ci_pct_per_year": [round(float(v), 4) for v in ci]}


def save(db: Session, plant_id: int, kind: str, day: date, result: dict, now: Optional[datetime] = None) -> PlantAnalytics:
    """Idempotent upsert on (plant, kind, day)."""
    row = db.execute(select(PlantAnalytics).where(PlantAnalytics.plant_id == plant_id, PlantAnalytics.kind == kind,
                                                  PlantAnalytics.day == day)).scalars().first()
    if row is None:
        row = PlantAnalytics(plant_id=plant_id, kind=kind, day=day)
        db.add(row)
    row.method, row.label = result.get("method", "none"), result.get("label", "none")
    row.result_json = json.dumps(result, default=str)
    row.computed_at = now or datetime.now(timezone.utc)
    db.commit()
    return row


def latest(db: Session, plant_id: int, kind: str) -> Optional[dict]:
    row = db.execute(select(PlantAnalytics).where(PlantAnalytics.plant_id == plant_id, PlantAnalytics.kind == kind)
                     .order_by(PlantAnalytics.day.desc())).scalars().first()
    return None if row is None else {**json.loads(row.result_json), "day": row.day.isoformat(),
                                     "computed_at": row.computed_at.isoformat()}
