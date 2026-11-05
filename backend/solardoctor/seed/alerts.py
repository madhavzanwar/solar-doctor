"""Alert generation by running the physics module's own detector over the simulated series.

Nothing is hand-written: daily performance indices are computed against the physics expected
power, and ``anomaly_service.detect_and_persist_anomaly`` decides whether a shortfall is an alert
and with which severity.  "Sustained" means ``SUSTAIN_DAYS`` consecutive eligible days above the
plant's soiling threshold.  Eligible hours are daylight, POA >= MIN_POA, and not inverter-clipped.
The expected series uses the same (cloudy-spell-included) irradiance as the telemetry, so the
cloudy spell produces no deficit.
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from solardoctor.physics import anomaly_service
from solardoctor.physics.models import PlantAlert
from solardoctor.physics.schemas.alert import AlertThresholdRequest
from solardoctor.seed.simulate import PlantSim
from solardoctor.seed.specs import SOURCE

SUSTAIN_DAYS = 3
MIN_POA = 250.0
MIN_SAMPLES = 8          # 15-min samples (2 h) of eligible hours per day
CLIP_FRACTION = 0.92


def eligible_mask(sim: PlantSim) -> np.ndarray:
    poa = sim.clean["poa_global"].to_numpy()
    elev = sim.clean["solar_elevation"].to_numpy()
    exp_ac = sim.clean["p_ac_kw"].to_numpy()
    return (elev > 15.0) & (poa >= MIN_POA) & (exp_ac < CLIP_FRACTION * sim.spec.ac_kw)


def daily_series(times: pd.DatetimeIndex, mask: np.ndarray, expected: np.ndarray, actual: np.ndarray) -> list[dict]:
    out = []
    days = times.normalize()
    for day in days.unique():
        m = mask & (days == day)
        if m.sum() < MIN_SAMPLES or expected[m].sum() <= 0:
            continue
        i_peak = int(np.flatnonzero(m)[np.argmax(expected[m])])
        out.append(dict(day=day, ts=times[i_peak], exp=float(expected[m].mean()), act=float(actual[m].mean()),
                        deficit=100.0 * (1.0 - actual[m].sum() / expected[m].sum())))
    return out


def _run_state_machine(db: Session, plant_id: int, series: list[dict], threshold: float, alert_type: str,
                       label: str, expected_scale=None) -> list[PlantAlert]:
    created: list[PlantAlert] = []
    over, open_alert = 0, None
    for d in series:
        if d["deficit"] >= threshold:
            over += 1
            if over >= SUSTAIN_DAYS and open_alert is None:
                scale = 1.0 if expected_scale is None else expected_scale(d["day"])
                alert = anomaly_service.detect_and_persist_anomaly(
                    db, plant_id, d["ts"].to_pydatetime(), d["exp"] * scale, d["act"],
                    alert_type=alert_type, source=SOURCE)
                if alert is not None:
                    alert.message = f"[{label}] sustained {over}-day shortfall vs physics baseline. " + alert.message
                    db.commit()
                    created.append(alert)
                    open_alert = alert
        else:
            over = 0
            if open_alert is not None:
                open_alert.is_resolved = True
                open_alert.resolved_at = d["ts"].to_pydatetime().astimezone(timezone.utc)
                db.commit()
                open_alert = None
    return created


def generate_alerts(db: Session, plant_id: int, sim: PlantSim, soiling_threshold: float) -> list[PlantAlert]:
    """Run the detector over the plant (and each string, when the plant has strings)."""
    anomaly_service.set_threshold(AlertThresholdRequest(
        plant_id=plant_id, warning_threshold_percent=soiling_threshold, critical_threshold_percent=25.0))
    try:
        mask = eligible_mask(sim)
        exp_ac = sim.clean["p_ac_kw"].to_numpy()
        created: list[PlantAlert] = []
        if not sim.spec.strings:
            created += _run_state_machine(
                db, plant_id, daily_series(sim.times, mask, exp_ac, sim.plant_ac_kw),
                soiling_threshold, "soiling_loss", "plant-wide")
            return created

        # With strings: the plant-wide index uses the median string (robust to one faulty string),
        # and each string is compared against its peers' daily median index.
        pi: dict[str, dict] = {}
        for g in sim.groups:
            exp = g.p_expected_dc_kw
            pi[g.name] = {s["day"]: s for s in daily_series(sim.times, mask, exp, g.p_dc_kw)}
        days = sorted(set.intersection(*[set(v) for v in pi.values()]))
        median_def = {d: float(np.median([pi[n][d]["deficit"] for n in pi])) for d in days}
        plant_series = []
        for d in days:
            ref = next(iter(pi.values()))[d]
            exp_sum = sum(pi[n][d]["exp"] for n in pi)  # plant-level DC kW (clean physics)
            plant_series.append(dict(ref, exp=exp_sum, act=exp_sum * (1.0 - median_def[d] / 100.0),
                                     deficit=median_def[d]))
        created += _run_state_machine(db, plant_id, plant_series, soiling_threshold, "soiling_loss", "plant-wide")

        for g in sim.groups:
            peer = {d: median_def[d] for d in days}
            series = []
            for d in days:
                s = pi[g.name][d]
                peer_pi = 1.0 - peer[d] / 100.0
                rel_def = 100.0 * (1.0 - (1.0 - s["deficit"] / 100.0) / peer_pi) if peer_pi > 0 else 0.0
                series.append(dict(s, deficit=rel_def))
            def scale(day, _peer=peer):
                return 1.0 - _peer[day] / 100.0  # expected = clean string share x peers' soiling index
            created += _run_state_machine(db, plant_id, series, soiling_threshold, "string_underperformance",
                                          g.name, expected_scale=scale)
        return created
    finally:
        anomaly_service._thresholds.pop(plant_id, None)
