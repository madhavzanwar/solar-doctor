"""Hourly / daily physics jobs on SIMULATED telemetry: idempotent, per-plant failure isolation, tracker skip."""
import json
from datetime import timedelta

import pytest

from solardoctor.physics import deficit, jobs
from solardoctor.physics.models import PlantAlert, PlantAnalytics
from solardoctor.physics.tracker import TRACKER_MARKER

from . import deficit_synth as ds

NOW = ds.START + timedelta(days=ds.DAYS)
NO_NET = dict(nasa_fetch=lambda *a, **k: (_ for _ in ()).throw(AssertionError("site GHI covers every row")),
              openmeteo_fetch=lambda *a, **k: (_ for _ in ()).throw(AssertionError("no future rows")))


@pytest.fixture
def db():
    s = ds.temp_session()
    yield s
    s.close()


def _plant(db, scenario="string_10", seed=0):
    plant, invs, strs = ds.make_plant(db)
    ds.populate(db, plant, invs, strs, scenario, seed)
    return plant


def test_hourly_creates_alerts_and_is_idempotent(db):
    plant = _plant(db)
    assert jobs.run_hourly(db, NOW, **NO_NET) == {plant.id: "ok"}
    rows = db.query(PlantAlert).all()
    assert len(rows) == 1 and rows[0].scope == "string" and rows[0].source == "SIMULATED"
    jobs.run_hourly(db, NOW, **NO_NET)
    assert db.query(PlantAlert).count() == 1


def test_daily_rescans_and_persists_analytics_idempotently(db):
    plant = _plant(db)
    assert jobs.run_daily(db, NOW, **NO_NET) == {plant.id: {"scan": "ok", "soiling": "insufficient_data",
                                                            "degradation": "insufficient_data"}}
    rows = {r.kind: r for r in db.query(PlantAnalytics)}
    assert set(rows) == {"soiling", "degradation"} and db.query(PlantAlert).count() == 1
    assert json.loads(rows["soiling"].result_json)["days_with_data"] == 3
    jobs.run_daily(db, NOW, **NO_NET)
    assert db.query(PlantAnalytics).count() == 2 and db.query(PlantAlert).count() == 1


def test_one_failing_plant_does_not_stop_the_others(db, monkeypatch):
    bad, good = _plant(db), _plant(db)
    real = deficit.scan_and_persist

    def flaky(db_, plant_id, *a, **k):
        if plant_id == bad.id:
            raise RuntimeError("boom")
        return real(db_, plant_id, *a, **k)
    monkeypatch.setattr(deficit, "scan_and_persist", flaky)
    assert jobs.run_hourly(db, NOW, **NO_NET) == {bad.id: "error", good.id: "ok"}
    assert {a.plant_id for a in db.query(PlantAlert)} == {good.id}


def test_inactive_and_tracker_plants_are_skipped(db):
    a, b, c = _plant(db), _plant(db), _plant(db)
    a.is_active = False
    b.location = f"Pune {TRACKER_MARKER}"
    db.commit()
    assert list(jobs.run_hourly(db, NOW, **NO_NET)) == [c.id]


def test_scheduler_is_off_unless_env_set(monkeypatch):
    from solardoctor.api.app import _start_physics_jobs
    monkeypatch.delenv("SOLARDOCTOR_PHYSICS_JOBS", raising=False)
    assert _start_physics_jobs() is None


def test_failing_degradation_does_not_prevent_saving_soiling(db, monkeypatch):
    from solardoctor.physics import soiling_analytics as sa
    plant = _plant(db)
    monkeypatch.setattr(sa, "degradation_analysis", lambda *a, **k: (_ for _ in ()).throw(ValueError("boom")))
    res = jobs.run_daily(db, NOW, **NO_NET)
    assert res[plant.id]["soiling"] == "insufficient_data" and res[plant.id]["degradation"] == "error"
    assert {r.kind for r in db.query(PlantAnalytics)} == {"soiling"}


def test_analytics_load_plant_level_rows_only(db, monkeypatch):
    plant = _plant(db)
    seen = []
    real = deficit.performance
    monkeypatch.setattr(deficit, "performance", lambda p, tel, *a, **k: (seen.append(len(tel)), real(p, tel, *a, **k))[1])
    jobs._analytics(db, plant, NOW, NO_NET["nasa_fetch"], NO_NET["openmeteo_fetch"])
    assert seen == [3 * 96]  # plant meter rows only, not the 2 inverters and 8 strings
