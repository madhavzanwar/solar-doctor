"""--reset safety with dependants, --shift-to-now provenance/physics, seed error handling.

No network (mock NASA fetcher, see test_seed.py).
"""
from __future__ import annotations

import importlib.util
import json
from datetime import timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import sqlalchemy as sa

from solardoctor.physics import solar
from tests.backend.test_seed import ENV, END, mock_nasa, _use_db  # noqa: F401  (shared mock + helpers)

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def db(tmp_path, monkeypatch):
    _use_db(monkeypatch, tmp_path / "x.db")
    from solardoctor.db.session import get_session, init_db
    init_db()
    s = get_session()
    yield s
    s.close()
    from solardoctor.db import session as sess
    sess._engine = sess._SessionLocal = None


def _count(db, model, *where):
    return db.scalar(sa.select(sa.func.count()).select_from(model).where(*where))


def test_reset_with_comments_photos_detections_and_foreign_rows(db, tmp_path):
    from solardoctor.db.models import Detection, FaultComment, FaultPhoto, Inspection, PanelFault, Park, User
    from solardoctor.physics.models import Plant, PlantAlert, Telemetry
    from solardoctor.seed.builder import run_seed

    cache = tmp_path / "cache"
    run_seed(db, fetcher=mock_nasa, cache_dir=cache, window_end=END, env=ENV)
    s04 = db.query(PanelFault).filter(PanelFault.panel_id == "S-04").one()
    db.add_all([
        FaultComment(fault_id=s04.id, author="technician@solardoctor.example", body="checked connectors"),
        FaultPhoto(fault_id=s04.id, original_name="a.jpg", stored_name="fault-photos/1/a.jpg",
                   content_type="image/jpeg", size_bytes=3),
        Inspection(id="INSP-X", park_id="PARK_PCCOE_ROOFTOP"),
    ])
    db.commit()
    db.add(Detection(inspection_id="INSP-X", fault_id=s04.id))
    # rows that --reset must never touch: a real PVDAQ plant, a user plant (+telemetry, alert), a foreign fault
    pv = Plant(name="PVDAQ 1 FIXTURE_NOT_REAL_DATA", lat=40.0, lon=-105.0, dc_kw=10, ac_kw=8, source="PVDAQ")
    us = Plant(name="My own plant", lat=18.0, lon=73.0, dc_kw=5, ac_kw=4, source="USER")
    db.add_all([pv, us])
    db.flush()
    t0 = pd.Timestamp("2024-06-01", tz="UTC").to_pydatetime()
    db.add_all([Telemetry(plant_id=pv.id, ts=t0, p_ac_kw=1.0, source="PVDAQ"),
                Telemetry(plant_id=us.id, ts=t0, p_ac_kw=1.0, source="USER"),
                PlantAlert(plant_id=us.id, timestamp=t0, alert_type="x", severity="WARNING", message="m", source="USER"),
                PanelFault(park_id="PARK_BHADLA_C", panel_id="R9-C9", class_="cell", notes="field-observed")])
    db.commit()
    n_user_users = _count(db, User)

    run_seed(db, fetcher=mock_nasa, cache_dir=cache, window_end=END, env=ENV, reset=True)  # must not raise

    assert _count(db, FaultComment) == 0 and _count(db, FaultPhoto) == 0
    det = db.query(Detection).one()
    assert det.fault_id is None                                  # detached, the inspection's detection survives
    new_s04 = db.query(PanelFault).filter(PanelFault.panel_id == "S-04").one()
    assert new_s04.id != s04.id and new_s04.notes.startswith("SIMULATED")
    assert _count(db, Telemetry, Telemetry.source == "PVDAQ") == 1
    assert _count(db, Telemetry, Telemetry.source == "USER") == 1
    assert _count(db, PlantAlert, PlantAlert.source == "USER") == 1
    assert {p.name for p in db.query(Plant)} >= {"PVDAQ 1 FIXTURE_NOT_REAL_DATA", "My own plant", "Bhadla Block C"}
    assert db.query(PanelFault).filter(PanelFault.panel_id == "R9-C9").count() == 1
    assert _count(db, User) == n_user_users
    assert db.get(Park, "PARK_PCCOE_ROOFTOP").name.endswith("(SIMULATED)")


def test_shift_to_now_is_labelled_and_physically_consistent(db, tmp_path):
    from solardoctor.db.models import PanelFault
    from solardoctor.physics.models import Plant, PlantAlert, Telemetry, WeatherCache
    from solardoctor.seed.builder import run_seed

    today = pd.Timestamp.now(tz="UTC").normalize()

    def lagging(lat, lon, start, end):  # GHI is only available until ~40 days ago, like the real service
        df = mock_nasa(lat, lon, start, end)
        df.loc[df.index >= today - pd.Timedelta(days=40), "ghi"] = np.nan
        return df

    rep = run_seed(db, fetcher=lagging, cache_dir=tmp_path / "cache", env=ENV, shift_to_now=True,
                   manifest_path=tmp_path / "m.json")
    assert rep.shift_days >= 30 and "--shift-to-now" in rep.window_note
    newest = db.scalar(sa.select(sa.func.max(Telemetry.ts)))
    assert pd.Timestamp(newest).normalize() == today - pd.Timedelta(days=1)     # ends yesterday
    assert all(v["irradiance_source"] == "NASA_POWER_TIME_SHIFTED" for v in rep.plants.values())

    metas = [json.loads(m.payload_json) for m in db.query(WeatherCache).filter(WeatherCache.kind == "seed_meta")]
    assert len(metas) == 3
    for m in metas:
        assert m["irradiance_source"] == "NASA_POWER_TIME_SHIFTED" and m["shift_days"] == rep.shift_days
        assert "time-shifted NASA POWER irradiance" in m["irradiance_note"]
    manifest = json.loads((tmp_path / "m.json").read_text())
    assert manifest["time_shifted_irradiance"] is True and manifest["shift_days"] == rep.shift_days
    # everything is still labelled SIMULATED
    assert _count(db, Telemetry, Telemetry.source != "SIMULATED") == 0
    assert _count(db, PlantAlert, PlantAlert.source != "SIMULATED") == 0
    assert _count(db, Plant, Plant.source != "SIMULATED") == 0
    # faults are dated inside the window
    assert {f.first_seen_date for f in db.query(PanelFault)} == {(today - pd.Timedelta(days=1)).date().isoformat()}

    # Physics stays consistent for the dates shown: GHI never exceeds the clear-sky ceiling computed for the
    # SHIFTED timestamps, and is zero when the sun is down there.
    p = db.query(Plant).filter(Plant.name == "Bhadla Block C").one()
    df = pd.read_sql(sa.select(Telemetry).where(Telemetry.plant_id == p.id, Telemetry.inverter_id.is_(None)),
                     db.get_bind(), parse_dates=["ts"]).sort_values("ts")
    ts = pd.DatetimeIndex(df.ts)
    ts = ts.tz_localize("UTC") if ts.tz is None else ts
    cs = solar.clearsky_irradiance(p.lat, p.lon, ts, p.altitude_m)["ghi"].to_numpy()
    assert (df.ghi_wm2.to_numpy() <= 1.16 * cs + 1e-6).all()
    assert (df.ghi_wm2[cs <= 0] == 0).all() and (df.ghi_wm2[cs > 200] > 0).any()
    # the seeded data now passes the 24 h freshness bar of the diagnose path
    assert pd.Timestamp.now(tz="UTC") - pd.Timestamp(newest) < timedelta(hours=48)


def test_bad_seed_password_is_a_clean_error(db, tmp_path, monkeypatch, capsys):
    from solardoctor.seed.builder import SeedError, run_seed
    with pytest.raises(SeedError, match="10-256"):
        run_seed(db, fetcher=mock_nasa, cache_dir=tmp_path, window_end=END,
                 env={"SOLARDOCTOR_SEED_ADMIN_PASSWORD": "short"})
    # and via the CLI: message on stderr, exit code 1, no traceback
    monkeypatch.setenv("SOLARDOCTOR_SEED_ADMIN_PASSWORD", "short")
    spec = importlib.util.spec_from_file_location("seed_cli2", REPO_ROOT / "scripts" / "seed.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main(["--offline", "--cache-dir", str(tmp_path / "c2")]) == 1
    err = capsys.readouterr().err
    assert "ERROR: cannot create seed user" in err and "Traceback" not in err
