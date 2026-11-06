"""Deficit detector on SIMULATED telemetry with known injected losses (see deficit_synth.py)."""
import json
from functools import cache

import pytest
from sqlalchemy import select

from solardoctor.physics.models import PlantAlert
from solardoctor.physics.tracker import TRACKER_MARKER

from . import deficit_synth as ds

SEEDS = (0, 1)


@cache
def _run(scenario, seed, curtail=None):
    return ds.run(scenario, seed, curtail=curtail)


def _rule(ev):  # the documented rule on the lowest rolling median of PI: CRITICAL < 0.90, WARNING < 0.95
    low = ev.evidence["pi_rolling_min"]
    return "INFO" if low is None else "CRITICAL" if low < 0.90 else "WARNING"


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("scenario,loss", [("string_5", 0.05), ("string_10", 0.10), ("string_20", 0.20)])
def test_single_string_is_localised(scenario, loss, seed):
    res, truth, sids, _ = _run(scenario, seed)
    (idx,) = truth.strings
    assert [(e.scope, e.scope_id) for e in res["events"]] == [("string", sids[idx])]  # that string only, no plant event
    ev = res["events"][0]
    assert ev.peer_z <= -3 and ev.clear_hours >= 3
    assert ev.pi_median == pytest.approx(1 - loss, abs=0.02)
    assert ev.severity == _rule(ev)
    assert ev.deviation_percent == pytest.approx(loss * 100, abs=2.0)
    if loss == 0.20:
        assert ev.severity == "CRITICAL"


@pytest.mark.parametrize("seed", SEEDS)
def test_plant_wide_soiling_is_one_plant_event(seed):
    res, _, _, _ = _run("soiling_7", seed)
    assert [(e.scope, e.scope_id) for e in res["events"]] == [("plant", None)]
    ev = res["events"][0]
    assert ev.pi_median == pytest.approx(0.93, abs=0.02) and ev.severity == _rule(ev) == "WARNING"
    assert "soiling" in ev.evidence["cause_hint"]


@pytest.mark.parametrize("scenario", ["control", "cloudy"])
@pytest.mark.parametrize("seed", SEEDS)
def test_no_events_on_healthy_or_cloudy(scenario, seed):
    res, _, _, _ = _run(scenario, seed)
    assert res["status"] == "ok" and res["events"] == []


def test_alert_row_has_all_fields_and_provenance():
    res, truth, sids, plant = _run("string_10", 0)
    from sqlalchemy.orm import object_session
    s = object_session(plant)
    (a,) = s.execute(select(PlantAlert)).scalars().all()
    assert (a.alert_type, a.scope, a.string_id, a.inverter_id, a.baseline, a.is_resolved) == \
           ("deficit", "string", sids[next(iter(truth.strings))], None, "pvwatts", False)
    assert a.source == "SIMULATED" and a.expected_power_kw > a.actual_power_kw > 0 and a.deviation_percent > 5
    ev = json.loads(a.evidence_json)
    assert ev["data_source"] == "SIMULATED" and ev["baseline"] == "pvwatts" and ev["samples_used"] > 0
    assert ev["weather_provenance"] == {"site_sensor": 288} and ev["qc"]["clearsky_method"] == "reno"
    assert {"pi_series", "peer_z", "thresholds", "window_start", "window_end"} <= set(ev)


def test_rescan_is_idempotent():
    res, _, _, plant = ds.run("string_10", 3)
    from sqlalchemy.orm import object_session
    s = object_session(plant)
    first = s.execute(select(PlantAlert)).scalars().all()
    res2 = ds.scan(s, plant)
    again = s.execute(select(PlantAlert)).scalars().all()
    assert len(first) == len(again) == 1 and res2["alerts"] == res["alerts"] == [first[0].id]
    # changed numbers update the same row instead of inserting
    plant.pi_critical = 0.85
    ds.scan(s, plant)
    (only,) = s.execute(select(PlantAlert)).scalars().all()
    assert only.id == first[0].id and only.severity == "WARNING"


def test_tracker_plant_is_unsupported_and_raises_nothing():
    db = ds.temp_session()
    plant, invs, strs = ds.make_plant(db)
    ds.populate(db, plant, invs, strs, "string_20", 0)
    plant.location = f"Pune {TRACKER_MARKER}"
    db.commit()
    res = ds.scan(db, plant)
    assert res["status"] == "baseline_unsupported_for_trackers" and res["events"] == []
    assert db.execute(select(PlantAlert)).scalars().all() == []


def test_curtailed_samples_are_ignored_but_unflagged_curtailment_is_a_deficit():
    window = (4, 9, 0.6)  # UTC hours, 60 % of output kept
    flagged, _, _, _ = ds.run("control", 0, curtail=(*window, True))
    assert flagged["events"] == [] and flagged["qc"]["plant"]["curtailed"] > 0
    unflagged, _, _, _ = ds.run("control", 0, curtail=(*window, False))
    assert [e.scope for e in unflagged["events"]] == ["plant"] and unflagged["events"][0].severity == "CRITICAL"


def test_pooled_precision_recall_on_test_seeds():
    runs, pooled, _ = ds.evaluate(SEEDS)
    for r in runs:  # the metric script reports 10 seeds; here every run must be exactly right
        assert r["any"] == r["truth"], (r["scenario"], r["seed"])
    assert pooled["any_severity"]["precision"] == 1.0 and pooled["any_severity"]["recall"] == 1.0
