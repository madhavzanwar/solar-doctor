"""Harder SIMULATED scenarios (deficit_synth_hard.py): fast deterministic seed per scenario + review-fix regressions."""
from functools import cache

import pytest

from . import deficit_synth_hard as hs

SEED = 100


@cache
def _run(scenario, seed=SEED):
    return hs.run(scenario, seed)


def test_timestamp_jitter_is_binned_and_string_fault_found():
    res, truth, sids, _ = _run("jitter")
    (idx,) = truth.strings
    assert res["provenance"] == {"site_sensor": res["provenance"]["site_sensor"]}  # site GHI matched, not NASA/model
    assert [(e.scope, e.scope_id, e.severity) for e in res["events"]] == [("string", sids[idx], "CRITICAL")]


# -- clock offset QC (fast, no scan) ------------------------------------------

@pytest.mark.parametrize("shift_h", [0, 1, -1])
def test_clock_offset_minutes_recovers_shift(shift_h):
    import numpy as np
    import pandas as pd
    from solardoctor.physics import qa, solar
    from . import deficit_synth as ds
    plant = type("P", (), dict(lat=18.52, lon=73.86, altitude_m=560.0))()
    times = pd.date_range(ds.START, periods=4 * 96, freq="15min")
    cs = solar.clearsky_irradiance(plant.lat, plant.lon, times, plant.altitude_m)["ghi"]
    k = ds.clearness(np.random.default_rng(0), times, (1,))
    ghi = (cs * k).shift(4 * shift_h).fillna(0.0)  # labels late by shift_h hours
    w = pd.DataFrame({"ghi": ghi, "ghi_clearsky": cs, "source": "site_sensor"})
    off = qa.clock_offset_minutes(w)
    assert off == 60.0 * shift_h


# -- truth rules per scenario (seed 100, the first report seed) ---------------

NASA_FP = ("measured at seed 100: plant WARNING on a healthy plant. With only hourly NASA-style GHI (3 % clear to 33 % "
           "overcast error) the satellite error becomes a plant PI error that the clear-sky index gate cannot remove")
PCLOUD_FP = ("measured at seed 100: plant WARNING (PI 0.96) on a healthy broken-cloud plant, from only ~25 usable "
             "samples; sensor lag of 7 min behind the array leaves residual PI error in the few samples that pass the gate")
XFAIL = {"partly_cloudy": PCLOUD_FP, "control_nasa": NASA_FP, "cloudy_nasa": NASA_FP}


@pytest.mark.parametrize("scenario", [
    pytest.param(sc, marks=pytest.mark.xfail(strict=True, reason=XFAIL[sc])) if sc in XFAIL else sc
    for sc in hs.SCENARIOS if sc not in ("time_offset",)])
def test_scenario_truth_rules(scenario):
    res, truth, sids, _ = _run(scenario)
    j = hs.judge(scenario, res, truth, sids)
    assert j["warn"]["fp"] == 0 and j["warn"]["fn"] == 0, (scenario, [(e.scope, e.scope_id, e.severity) for e in res["events"]])


def test_just_under_threshold_is_not_flagged():
    res, truth, sids, _ = _run("just_under")
    assert not [e for e in res["events"] if e.severity != "INFO"]


def test_slow_soiling_not_premature_and_detected():
    res, truth, _, _ = _run("slow_soiling")
    plant_ev = [e for e in res["events"] if e.scope == "plant"]
    assert plant_ev and min(e.start for e in plant_ev) >= truth.t4


def test_time_offset_suspected_suppresses_alerts():
    res, _, _, _ = _run("time_offset")
    assert res["qc_status"] == "time_offset_suspected" and abs(res["clock_offset_min"]) == 60.0 and res["events"] == []


def test_aligned_clock_is_not_flagged():
    for sc in ("control_hard", "partly_cloudy"):  # partly_cloudy: sensor lags the array by 7 min, below the 30 min limit
        res = _run(sc)[0]
        assert res["qc_status"] == "ok" and abs(res["clock_offset_min"]) < 30


# -- R2: the clear-sky gate really removes cloudy samples ----------------------

def test_cloudy_samples_are_gated_out():
    clear, cloudy = _run("control_hard")[0]["qc"]["plant"], _run("partly_cloudy")[0]["qc"]["plant"]
    per_day = lambda q, d: q["usable"] / d
    assert per_day(cloudy, 4) < 0.5 * per_day(clear, 3)


# -- R3 / R4 -------------------------------------------------------------------

def _drop_rows(scenario, keep):
    from sqlalchemy import delete
    from sqlalchemy.orm import object_session

    from solardoctor.physics.models import Telemetry
    from . import deficit_synth as ds
    db = ds.temp_session()
    res, truth, sids, plant = hs.run(scenario, SEED, db)
    db.execute(delete(Telemetry).where(~keep(Telemetry, sids)))
    db.commit()
    return hs.scan(db, plant, scenario), sids


def test_inverter_only_plant_wide_soiling_is_one_plant_event():
    res, _ = _drop_rows("control_hard", lambda T, sids: T.inverter_id.isnot(None) & T.string_id.is_(None))
    assert res["events"] == []  # healthy: nothing
    from . import deficit_synth as ds
    db = ds.temp_session()
    res, truth, sids, plant = hs.run("slow_soiling", SEED, db)
    from sqlalchemy import delete
    from solardoctor.physics.models import Telemetry
    db.execute(delete(Telemetry).where(Telemetry.string_id.isnot(None) | Telemetry.inverter_id.is_(None)))
    db.commit()
    res = hs.scan(db, plant, "slow_soiling")
    assert [(e.scope, e.scope_id) for e in res["events"]] == [("plant", None)]


def test_fewer_than_four_strings_records_insufficient_peers():
    res, sids = _drop_rows("jitter", lambda T, s: T.string_id.is_(None) | T.string_id.in_(s[:3]))
    assert res["events"] and {e.evidence["localisation"] for e in res["events"]} == {"insufficient_peers"}


def test_full_string_set_records_peer_compared():
    res = _run("jitter")[0]
    assert {e.evidence["localisation"] for e in res["events"]} == {"peer_compared"}


def test_plant_total_from_strings_needs_coverage():
    """One of 8 strings silent (12.5 % of the modules): the string-sum total is NaN, not a 12 % plant deficit."""
    res, sids = _drop_rows("control_hard", lambda T, s: T.string_id.in_(s[1:]) & T.string_id.isnot(None))  # NULL-safe: also drops plant and inverter rows
    assert res["events"] == [] and res["qc"]["plant"]["usable"] == 0
