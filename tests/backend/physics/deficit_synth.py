"""SIMULATED telemetry with known injected losses, for testing and measuring the deficit detector.

Everything here is synthetic (source="SIMULATED"). The truth model is ``solar.expected_power`` (the repo's
original pvlib chain); the detector's baseline is the independent ``baseline.expected_power`` chain, so a
small systematic mismatch between the two is part of what is being measured. Irradiance is a measured-style
GHI (clear-sky x clearness) written into telemetry; power carries 1 % multiplicative noise.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sqlalchemy import create_engine, insert
from sqlalchemy.orm import Session

from solardoctor.db.models import Base
from solardoctor.physics import deficit, irradiance, solar
from solardoctor.physics.models import Inverter, Plant, PvString, Telemetry

SOURCE = "SIMULATED"
START = datetime(2026, 3, 18, tzinfo=timezone.utc)
NOW = datetime(2026, 3, 30, tzinfo=timezone.utc)
DAYS = 3
N_STRINGS, MODULES = 8, 100
NOISE = 0.01
_KEEP: list[Session] = []
SCENARIOS = ("control", "string_5", "string_10", "string_20", "soiling_7", "cloudy")


@dataclass
class Truth:
    strings: dict[int, float] = field(default_factory=dict)  # string index -> fractional loss
    plant_loss: float = 0.0

    def keys(self, string_ids: list[int]) -> set[tuple[str, int | None]]:
        out = {("string", string_ids[i]) for i in self.strings}
        return out | ({("plant", None)} if self.plant_loss else set())


def temp_session() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return Session(engine)


def make_plant(db: Session) -> tuple[Plant, list[Inverter], list[PvString]]:
    plant = Plant(name="Synthetic plant (SIMULATED)", lat=18.52, lon=73.86, tz="Asia/Kolkata", altitude_m=560.0,
                  tilt=20.0, azimuth=180.0, dc_kw=400.0, ac_kw=360.0, module_count=N_STRINGS * MODULES,
                  source=SOURCE, location="Pune")
    db.add(plant)
    db.flush()
    invs = [Inverter(plant_id=plant.id, name=f"INV-{i + 1}", ac_kw=180.0) for i in range(2)]
    db.add_all(invs)
    db.flush()
    strs = [PvString(plant_id=plant.id, inverter_id=invs[i // 4].id, name=f"S-{i + 1:02d}", module_count=MODULES)
            for i in range(N_STRINGS)]
    db.add_all(strs)
    db.flush()
    return plant, invs, strs


def clearness(rng: np.random.Generator, times: pd.DatetimeIndex, cloudy_days: tuple[int, ...]) -> np.ndarray:
    """Clear days: ~0.97 with slow drift and tiny jitter. Cloudy days: AR(1) cloud passages, k in 0.1..1.0."""
    n = len(times)
    k = 0.97 + 0.01 * np.sin(np.linspace(0, 6, n)) + rng.normal(0, 0.003, n)
    day = np.asarray((times - times[0].normalize()) / pd.Timedelta(days=1)).astype(int)
    ar = np.zeros(n)
    for i in range(1, n):
        ar[i] = 0.9 * ar[i - 1] + rng.normal(0, 0.45)
    cloud = np.clip(0.5 + 0.3 * ar, 0.1, 1.0)
    return np.where(np.isin(day, cloudy_days), cloud, k)


def populate(db: Session, plant, invs, strs, scenario: str, seed: int, curtail: tuple[int, int, float, bool] | None = None
             ) -> Truth:
    """Insert 15-min telemetry (plant, inverter and string rows) for ``scenario``; return the injected truth.

    ``curtail`` = (hour_from, hour_to, fraction kept, flagged): output cap, optionally flagged by the SCADA.
    """
    rng = np.random.default_rng(seed)
    times = pd.date_range(START, periods=DAYS * 96, freq="15min")
    cloudy = (1,) if scenario == "cloudy" else ()
    ghi = clearness(rng, times, cloudy) * irradiance_clearsky(plant, times)
    t_air = 25 + 8 * np.sin((times.hour + times.minute / 60 - 6) / 24 * 2 * np.pi)
    wind = np.full(len(times), 2.0)
    ex = solar.expected_power(plant, times, ghi=pd.Series(ghi, index=times), temp_air=t_air, wind_speed=wind)

    truth = Truth()
    if scenario.startswith("string_"):
        truth.strings[int(rng.integers(N_STRINGS))] = int(scenario.split("_")[1]) / 100
    if scenario == "soiling_7":
        truth.plant_loss = 0.07
    cap = np.ones(len(times))
    flagged = np.zeros(len(times), bool)
    if curtail:
        h = times.hour.to_numpy()
        hit = (h >= curtail[0]) & (h < curtail[1])
        cap[hit] = curtail[2]
        flagged = hit & curtail[3]

    dc_share = ex["p_dc_kw"].to_numpy() / N_STRINGS
    s_dc = []
    for i in range(N_STRINGS):
        loss = truth.strings.get(i, 0.0)
        s_dc.append(dc_share * (1 - loss) * (1 - truth.plant_loss) * cap * rng.normal(1.0, NOISE, len(times)))
    inv_ac = [np.minimum((sum(s_dc[4 * j:4 * j + 4])) * solar.INVERTER_EFFICIENCY, 180.0) for j in range(2)]
    plant_ac = inv_ac[0] + inv_ac[1]

    def rows(ts, inv, sid, ac, dc):
        return [dict(ts=t.to_pydatetime(), plant_id=plant.id, inverter_id=inv, string_id=sid, p_ac_kw=float(a),
                     p_dc_kw=None if d is None else float(d), poa_wm2=None, ghi_wm2=float(g), t_amb=float(ta),
                     wind_ms=2.0, curtailed=bool(c), source=SOURCE)
                for t, a, d, g, ta, c in zip(ts, ac, dc if dc is not None else [None] * len(ts), ghi, t_air, flagged)]

    data = rows(times, None, None, plant_ac, None)
    for j, inv in enumerate(invs):
        data += rows(times, inv.id, None, inv_ac[j], None)
    for i, s in enumerate(strs):
        data += rows(times, s.inverter_id, s.id, s_dc[i] * solar.INVERTER_EFFICIENCY, s_dc[i])
    db.execute(insert(Telemetry), data)
    db.commit()
    return truth


def irradiance_clearsky(plant, times) -> np.ndarray:
    return solar.clearsky_irradiance(plant.lat, plant.lon, times, plant.altitude_m)["ghi"].to_numpy()


def scan(db: Session, plant, baseline: str = "pvwatts") -> dict:
    return deficit.scan_and_persist(
        db, plant.id, START, START + pd.Timedelta(days=DAYS), baseline, now=NOW,
        nasa_fetch=lambda *a, **k: (_ for _ in ()).throw(AssertionError("site GHI should cover every row")))


def run(scenario: str, seed: int, db: Session | None = None, curtail=None):
    """Fresh plant + telemetry + scan. Returns (result, truth, string_ids, plant)."""
    db = db or temp_session()
    _KEEP.append(db)  # the plant only weakly references its session; callers use object_session(plant)
    plant, invs, strs = make_plant(db)
    truth = populate(db, plant, invs, strs, scenario, seed, curtail)
    return scan(db, plant), truth, [s.id for s in strs], plant


def score(rows: list[tuple[set, set, set]]) -> dict:
    """rows: (truth keys, detected keys any severity, detected keys >= WARNING). Precision / recall pooled."""
    out = {}
    for name, idx in (("any_severity", 1), ("warning_or_critical", 2)):
        tp = sum(len(r[0] & r[idx]) for r in rows)
        fp = sum(len(r[idx] - r[0]) for r in rows)
        fn = sum(len(r[0] - r[idx]) for r in rows)
        out[name] = {"tp": tp, "fp": fp, "fn": fn,
                     "precision": tp / (tp + fp) if tp + fp else float("nan"),
                     "recall": tp / (tp + fn) if tp + fn else float("nan")}
    return out


def evaluate(seeds, scenarios=SCENARIOS):
    """Run every scenario x seed; return per-run rows and pooled / per-scenario scores."""
    runs = []
    for sc in scenarios:
        for seed in seeds:
            res, truth, sids, _ = run(sc, seed)
            ev = res["events"]
            runs.append({"scenario": sc, "seed": seed, "truth": truth.keys(sids),
                         "any": {(e.scope, e.scope_id) for e in ev},
                         "warn": {(e.scope, e.scope_id) for e in ev if e.severity != "INFO"},
                         "events": ev})
    triple = lambda rs: [(r["truth"], r["any"], r["warn"]) for r in rs]
    return runs, score(triple(runs)), {sc: score(triple([r for r in runs if r["scenario"] == sc])) for sc in scenarios}
