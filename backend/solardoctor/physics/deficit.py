"""Deficit detector: telemetry vs physics baseline on QC-passed clear-sky samples.

Performance index PI = actual / expected, per scope (plant, inverter, string), aggregated to clear hours.
WARNING when the rolling median over ``plant.deficit_min_clear_hours`` clear hours is below ``plant.pi_warning``,
CRITICAL below ``plant.pi_critical``. Strings are compared with their peers (robust z of median PI) to tell a
single bad string (localised, drone target) from a plant-wide deficit (soiling / haze / curtailment).
"""
from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Optional

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from solardoctor.physics import baseline as baseline_mod, irradiance, qa, solar
from solardoctor.physics import weather_service as ws
from solardoctor.physics.anomaly_service import calculate_deviation
from solardoctor.physics.models import Inverter, Plant, PlantAlert, PvString, Telemetry
from solardoctor.physics.tracker import BASELINE_UNSUPPORTED_STATUS, is_tracker_plant

logger = logging.getLogger("solardoctor.physics.deficit")

ALERT_TYPE = "deficit"
PEER_Z = -3.0
MIN_PEERS = 4              # strings needed for a meaningful peer comparison
PEER_SIGMA_FLOOR = 0.01    # PI scatter floor: a MAD of ~0 would turn noise into huge z-scores
ETA = solar.INVERTER_EFFICIENCY
Key = tuple[str, Optional[int]]  # (scope, db id)


@dataclass
class DeficitEvent:
    scope: str
    scope_id: Optional[int]
    name: str
    severity: str  # CRITICAL | WARNING | INFO
    start: datetime
    end: datetime
    pi_median: float
    expected_kw_mean: float
    actual_kw_mean: float
    deviation_percent: float
    clear_hours: int
    peer_z: Optional[float] = None
    evidence: dict = field(default_factory=dict)


@dataclass
class Performance:
    hourly: dict[Key, pd.DataFrame]   # clear hours only: pi, actual_kw, expected_kw, n
    names: dict[Key, str]
    qc: dict[str, dict]
    provenance: dict[str, int]
    baseline: str
    data_source: str
    parent: dict[int, Optional[int]]  # string id -> inverter id
    plant_samples: Optional[pd.DataFrame] = None  # plant scope at full resolution: actual_kw, expected_kw, clear, usable, source


def _qc_name(key: Key) -> str:
    return key[0] if key[1] is None else f"{key[0]}:{key[1]}"


def _shares(strings, inverters) -> tuple[dict[int, float], dict[int, float]]:
    """Module share per string, and per inverter (sum of its strings, else rating share)."""
    mods = {s.id: float(s.module_count or 0) for s in strings}
    tot = sum(mods.values())
    s_share = {i: (m / tot if tot else 1 / len(strings)) for i, m in mods.items()} if strings else {}
    rated = sum(v.ac_kw or 0.0 for v in inverters) or 1.0
    i_share = {}
    for inv in inverters:
        own = [s_share[s.id] for s in strings if s.inverter_id == inv.id]
        i_share[inv.id] = sum(own) if own else (inv.ac_kw or 0.0) / rated
    return s_share, i_share


def _hourly(actual: pd.Series, expected: pd.Series, usable: pd.Series, per_hour: int) -> pd.DataFrame:
    df = pd.DataFrame({"a": actual.where(usable), "e": expected.where(usable), "n": usable.astype(int)})
    h = df.resample("1h").sum(min_count=1)
    h = h[(h["n"] >= max(1, math.ceil(per_hour / 2))) & (h["e"] > 0)]
    return pd.DataFrame({"pi": h["a"] / h["e"], "actual_kw": h["a"] / h["n"], "expected_kw": h["e"] / h["n"],
                         "n": h["n"]})


def performance(plant, telemetry: pd.DataFrame, weather: pd.DataFrame, baseline: str = "pvwatts",
                strings=(), inverters=()) -> Performance:
    """Hourly PI on usable samples for every scope present in ``telemetry``.

    ``telemetry``: UTC-indexed rows with inverter_id/string_id (NaN for plant level), p_ac_kw, p_dc_kw,
    optional curtailed and source. ``weather`` is ``irradiance.resolve_weather`` output.
    """
    exp = baseline_mod.expected_power(plant, weather, baseline)
    idx = weather.index
    step = pd.Series(idx).diff().median() if len(idx) > 1 else pd.Timedelta(hours=1)
    per_hour = max(1, round(pd.Timedelta(hours=1) / step))
    s_share, i_share = _shares(strings, inverters)
    curtailed = (telemetry["curtailed"].fillna(False).astype(bool).groupby(level=0).any()
                 if "curtailed" in telemetry else None)
    inv_by_id = {i.id: i for i in inverters}
    str_rows = telemetry[telemetry["string_id"].notna()]
    inv_rows = telemetry[telemetry["inverter_id"].notna() & telemetry["string_id"].isna()]
    plant_rows = telemetry[telemetry["inverter_id"].isna() & telemetry["string_id"].isna()]

    series: dict[Key, tuple[pd.Series, pd.Series, str]] = {}  # actual, expected, name
    names_by_string = {s.id: s.name for s in strings}
    for sid, g in str_rows.groupby("string_id"):
        sid = int(sid)
        if sid in s_share:
            act = g["p_dc_kw"].fillna(g["p_ac_kw"] / ETA).groupby(level=0).mean().reindex(idx)
            series[("string", sid)] = (act, exp["p_dc_kw"] * s_share[sid], names_by_string[sid])
    for iid, g in inv_rows.groupby("inverter_id"):
        iid = int(iid)
        if iid in inv_by_id:
            limit = inv_by_id[iid].ac_kw or plant.ac_kw * i_share[iid]
            ex = (exp["p_dc_kw"] * i_share[iid] * ETA).clip(upper=limit)
            series[("inverter", iid)] = (g["p_ac_kw"].groupby(level=0).mean().reindex(idx), ex, inv_by_id[iid].name)
    act = None
    if len(plant_rows):
        act = plant_rows["p_ac_kw"].groupby(level=0).mean().reindex(idx)
    elif len(str_rows):  # no plant meter: sum of the strings, through the inverter
        sums = pd.concat([a for (sc, _), (a, _, _) in series.items() if sc == "string"], axis=1)
        act = (sums.sum(axis=1, min_count=1) * ETA).clip(upper=plant.ac_kw)
    if act is not None:
        series[("plant", None)] = (act, exp["p_ac_kw"], plant.name)

    hourly, names, qc, plant_samples = {}, {}, {}, None
    for key, (act, ex, name) in series.items():
        flags, stats = qa.qc_flags(act, weather, exp, plant, curtailed)
        if key[0] == "plant":
            limit = plant.ac_kw
        elif key[0] == "inverter":
            limit = inv_by_id[key[1]].ac_kw or plant.ac_kw
        else:
            limit = np.inf
        usable = flags["usable"] & (ex < qa.CLIP_FRACTION * limit)  # a clipped expectation says nothing about PI
        stats["usable"] = int(usable.sum())
        if key[0] == "plant":
            plant_samples = pd.DataFrame({"actual_kw": act, "expected_kw": ex, "clear": flags["clearsky"],
                                          "usable": usable, "source": weather["source"]})
        hourly[key], names[key], qc[_qc_name(key)] = _hourly(act, ex, usable, per_hour), name, stats
    modes = telemetry["source"].mode() if "source" in telemetry and len(telemetry) else []
    return Performance(
        hourly=hourly, names=names, qc=qc, provenance={k: int(v) for k, v in weather["source"].value_counts().items()},
        baseline=baseline, data_source=str(modes.iloc[0]) if len(modes) else "unknown",
        parent={s.id: s.inverter_id for s in strings}, plant_samples=plant_samples)


def plant_hourly(perf: Performance) -> pd.DataFrame:
    """Plant scope, every hour (not only clear ones): expected_kw, actual_kw, pi (usable samples only, else NaN),
    clear, usable (at least half of the hour's samples), source (most frequent irradiance provider)."""
    s = perf.plant_samples
    if s is None or s.empty:
        return pd.DataFrame(columns=["expected_kw", "actual_kw", "pi", "clear", "usable", "source"])
    u = s["usable"].astype(bool)
    h = pd.DataFrame({"e": s["expected_kw"].where(u), "a": s["actual_kw"].where(u), "u": u.astype(float),
                      "c": s["clear"].astype(float)}).resample("1h").agg({"e": "sum", "a": "sum", "u": "mean", "c": "mean"})
    n_usable = u.astype(int).resample("1h").sum()
    out = pd.DataFrame({
        "expected_kw": s["expected_kw"].resample("1h").mean(), "actual_kw": s["actual_kw"].resample("1h").mean(),
        "pi": (h["a"] / h["e"]).where((n_usable > 0) & (h["e"] > 0)), "clear": h["c"] >= 0.5, "usable": h["u"] >= 0.5,
        "source": s["source"].resample("1h").agg(lambda x: x.mode().iloc[0] if len(x) else "")})
    return out.dropna(subset=["expected_kw"])


def _low_span(pi: pd.Series, n: int, thr: float) -> Optional[tuple[int, int, float]]:
    """(first, last, lowest rolling median) over the positions of ``pi`` covered by rolling-median(n)
    windows below ``thr``."""
    roll = pi.rolling(n, min_periods=n).median()
    pos = np.flatnonzero((roll < thr).to_numpy())
    return (max(int(pos[0]) - n + 1, 0), int(pos[-1]), float(roll.iloc[pos].min())) if len(pos) else None


def _event(perf: Performance, plant, key: Key, h: pd.DataFrame, span: tuple, severity: Optional[str],
           peer_z: Optional[float] = None, hint: Optional[str] = None) -> DeficitEvent:
    """``span`` = (first, last[, lowest rolling median]); severity follows the lowest rolling median."""
    seg = h.iloc[span[0]:span[1] + 1]
    roll_min = span[2] if len(span) > 2 else None
    pi = float(seg["pi"].median())
    exp_kw, act_kw = float(seg["expected_kw"].mean()), float(seg["actual_kw"].mean())
    return DeficitEvent(
        scope=key[0], scope_id=key[1], name=f"{perf.names[key]} ({key[0]})",
        severity=severity or ("CRITICAL" if roll_min < plant.pi_critical else "WARNING"),
        start=seg.index[0].to_pydatetime(), end=(seg.index[-1] + pd.Timedelta(hours=1)).to_pydatetime(),
        pi_median=round(pi, 4), expected_kw_mean=round(exp_kw, 3), actual_kw_mean=round(act_kw, 3),
        deviation_percent=round(calculate_deviation(exp_kw, act_kw) or 0.0, 2), clear_hours=len(seg), peer_z=peer_z,
        evidence={
            "baseline": perf.baseline, "samples_used": int(seg["n"].sum()), "data_source": perf.data_source,
            "qc": perf.qc.get(_qc_name(key)), "weather_provenance": perf.provenance, "cause_hint": hint,
            "pi_rolling_min": None if roll_min is None else round(roll_min, 4),
            "pi_series": {"hours": len(h), "min": round(float(h["pi"].min()), 4),
                          "median": round(float(h["pi"].median()), 4), "max": round(float(h["pi"].max()), 4)},
            "thresholds": {"pi_warning": plant.pi_warning, "pi_critical": plant.pi_critical,
                           "min_clear_hours": plant.deficit_min_clear_hours},
            "peer_z": None if peer_z is None else round(peer_z, 2),
        })


def _plant_series_excluding(perf: Performance, flagged: set[int]) -> Optional[pd.DataFrame]:
    """Plant hourly PI rebuilt from the unflagged strings, so one bad string cannot raise a plant event."""
    keep = [h for (sc, sid), h in perf.hourly.items() if sc == "string" and sid not in flagged]
    if not keep:
        return None
    hours = keep[0].index
    for h in keep[1:]:
        hours = hours.union(h.index)
    a = sum((h["actual_kw"] * h["n"]).reindex(hours).fillna(0) for h in keep)
    e = sum((h["expected_kw"] * h["n"]).reindex(hours).fillna(0) for h in keep)
    n = sum(h["n"].reindex(hours).fillna(0) for h in keep)
    out = pd.DataFrame({"pi": a / e, "actual_kw": a / n, "expected_kw": e / n, "n": n})
    return out[e > 0]


def peer_z(perf: Performance, min_hours: int) -> tuple[pd.Series, dict[int, float]]:
    """(median PI per string, robust z of each against its peers) over strings with >= ``min_hours`` clear hours;
    z is empty with fewer than MIN_PEERS such strings."""
    keys = [k for k in perf.hourly if k[0] == "string" and len(perf.hourly[k]) >= min_hours]
    if len(keys) < MIN_PEERS:
        return pd.Series(dtype=float), {}
    med = pd.Series({k[1]: perf.hourly[k]["pi"].median() for k in keys})
    centre = med.median()
    sigma = max(1.4826 * (med - centre).abs().median(), PEER_SIGMA_FLOOR)
    return med, {int(i): float((v - centre) / sigma) for i, v in med.items()}


def detect(perf: Performance, plant) -> list[DeficitEvent]:
    n = max(1, int(plant.deficit_min_clear_hours))
    events: list[DeficitEvent] = []
    string_keys = [k for k in perf.hourly if k[0] == "string" and len(perf.hourly[k]) >= n]

    z = peer_z(perf, n)[1]
    flagged = {i for i, v in z.items() if v <= PEER_Z}

    for sid in sorted(flagged):
        h = perf.hourly[("string", sid)]
        hint = (f"string z={z[sid]:.1f} vs {len(string_keys) - 1} peers: inspect this string "
                "(soiling patch, bird drop, damage, shading)")
        span = _low_span(h["pi"], n, plant.pi_warning)
        if span:
            events.append(_event(perf, plant, ("string", sid), h, span, None, z[sid], hint))
        else:
            events.append(_event(perf, plant, ("string", sid), h, (0, len(h) - 1), "INFO", z[sid],
                                 "peer deficit below alert threshold; " + hint))

    plant_h = _plant_series_excluding(perf, flagged) if flagged else perf.hourly.get(("plant", None))
    plant_span = _low_span(plant_h["pi"], n, plant.pi_warning) if plant_h is not None and len(plant_h) else None
    if plant_span:
        events.append(_event(perf, plant, ("plant", None), plant_h, plant_span, None, None,
                             "uniform deficit across strings: soiling, haze or curtailment class"))

    for (scope, iid), h in perf.hourly.items():
        if scope != "inverter" or plant_span or len(h) < n or any(perf.parent.get(s) == iid for s in flagged):
            continue
        span = _low_span(h["pi"], n, plant.pi_warning)
        if span:
            events.append(_event(perf, plant, (scope, iid), h, span, None, None,
                                 "inverter-level deficit not explained by one string: check inverter / MPPT"))
    return events


# -- persistence -------------------------------------------------------------

def _telemetry_frame(db: Session, plant_id: int, start: datetime, end: datetime) -> pd.DataFrame:
    rows = db.execute(select(Telemetry).where(Telemetry.plant_id == plant_id, Telemetry.ts >= start,
                                              Telemetry.ts <= end).order_by(Telemetry.ts)).scalars().all()
    cols = ["inverter_id", "string_id", "p_ac_kw", "p_dc_kw", "poa_wm2", "ghi_wm2", "t_amb", "wind_ms",
            "curtailed", "source"]
    df = pd.DataFrame([[getattr(r, c) for c in cols] for r in rows], columns=cols,
                      index=pd.DatetimeIndex([r.ts for r in rows], tz="UTC"))
    for c in cols[:8]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def _upsert(db: Session, plant: Plant, ev: DeficitEvent, baseline: str, source: str) -> PlantAlert:
    iid = ev.scope_id if ev.scope == "inverter" else None
    sid = ev.scope_id if ev.scope == "string" else None
    alert = db.execute(select(PlantAlert).where(
        PlantAlert.plant_id == plant.id, PlantAlert.alert_type == ALERT_TYPE, PlantAlert.scope == ev.scope,
        PlantAlert.inverter_id.is_(None) if iid is None else PlantAlert.inverter_id == iid,
        PlantAlert.string_id.is_(None) if sid is None else PlantAlert.string_id == sid,
        PlantAlert.is_resolved.is_(False))).scalars().first()
    if alert is None:
        alert = PlantAlert(plant_id=plant.id, timestamp=ev.start, alert_type=ALERT_TYPE, scope=ev.scope,
                           inverter_id=iid, string_id=sid, is_resolved=False)
        db.add(alert)
    alert.severity, alert.baseline, alert.source = ev.severity, baseline, source
    alert.message = (f"{ev.name}: PI {ev.pi_median:.3f} over {ev.clear_hours} clear hours "
                     f"({ev.start:%Y-%m-%d %H:%M}..{ev.end:%Y-%m-%d %H:%M} UTC), deviation {ev.deviation_percent:.1f}%")[:1024]
    alert.expected_power_kw, alert.actual_power_kw = ev.expected_kw_mean, ev.actual_kw_mean
    alert.deviation_percent = ev.deviation_percent
    alert.evidence_json = json.dumps({**ev.evidence, "window_start": ev.start.isoformat(),
                                      "window_end": ev.end.isoformat(), "pi_median": ev.pi_median,
                                      "clear_hours": ev.clear_hours}, default=str)
    return alert


def load_inputs(db: Session, plant: Plant, start: datetime, end: datetime, now: Optional[datetime] = None,
                nasa_fetch: Callable = ws.fetch_nasa_power_hourly,
                openmeteo_fetch: Callable = irradiance.fetch_openmeteo_hourly, plant_level_only: bool = False):
    """(telemetry, weather, strings, inverters) for [start, end], or None without telemetry.
    ``plant_level_only`` drops inverter/string rows when plant-meter rows exist (long analytics windows)."""
    tel = _telemetry_frame(db, plant.id, start, end)
    if tel.empty:
        return None
    if plant_level_only and (plant_rows := tel[tel["inverter_id"].isna() & tel["string_id"].isna()]).size:
        tel = plant_rows
    gaps = tel.index.to_series().diff()
    step = gaps[gaps > pd.Timedelta(0)].median()
    step = pd.Timedelta(minutes=15) if pd.isna(step) else step
    grid = pd.date_range(tel.index.min(), tel.index.max(), freq=step)
    weather = irradiance.resolve_weather(plant, grid, tel[["ghi_wm2", "poa_wm2", "t_amb", "wind_ms"]], db=db, now=now,
                                         nasa_fetch=nasa_fetch, openmeteo_fetch=openmeteo_fetch)
    strings = db.execute(select(PvString).where(PvString.plant_id == plant.id)).scalars().all()
    inverters = db.execute(select(Inverter).where(Inverter.plant_id == plant.id)).scalars().all()
    return tel, weather, strings, inverters


def scan_and_persist(db: Session, plant_id: int, start: datetime, end: datetime, baseline: str = "pvwatts",
                     now: Optional[datetime] = None, nasa_fetch: Callable = ws.fetch_nasa_power_hourly,
                     openmeteo_fetch: Callable = irradiance.fetch_openmeteo_hourly) -> dict:
    """Run the detector over [start, end] telemetry; one open alert per (scope, ids) is created or updated."""
    plant = db.get(Plant, plant_id)
    if plant is None:
        raise ValueError(f"plant {plant_id} not found")
    empty = {"events": [], "alerts": [], "qc": {}, "provenance": {}}
    if is_tracker_plant(plant):
        return {"status": BASELINE_UNSUPPORTED_STATUS, **empty}
    inputs = load_inputs(db, plant, start, end, now, nasa_fetch, openmeteo_fetch)
    if inputs is None:
        return {"status": "no_telemetry", **empty}
    tel, weather, strings, inverters = inputs
    perf = performance(plant, tel, weather, baseline, strings, inverters)
    events = detect(perf, plant)
    alerts = [_upsert(db, plant, ev, baseline, perf.data_source) for ev in events]
    db.commit()
    return {"status": "ok", "baseline": baseline, "data_source": perf.data_source, "events": events,
            "alerts": [a.id for a in alerts], "qc": perf.qc, "provenance": perf.provenance}
