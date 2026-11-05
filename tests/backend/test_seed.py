"""`make seed` (scripts/seed.py): idempotency, labelling, physics-visible injected events, logins.

No network: NASA POWER is replaced by a deterministic mock fetcher (clear-sky x a smooth clearness
index).  The mock is test scaffolding, not data; the seed itself labels real runs by their actual source.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from solardoctor.physics import solar
from solardoctor.seed import irradiance as irr_mod
from solardoctor.seed.specs import CLOUDY_SPELL_DAYS, PLANTS

REPO_ROOT = Path(__file__).resolve().parents[2]
END = "2026-03-31"  # an arbitrary fixed window end (mock data, so the date is irrelevant)
ADMIN_PW = "seed-admin-pass-123"
TECH_PW = "seed-tech-pass-456"
ENV = {
    "SOLARDOCTOR_SEED_ADMIN_PASSWORD": ADMIN_PW,
    "SOLARDOCTOR_SEED_TECH_PASSWORD": TECH_PW,
}


def mock_nasa(lat, lon, start, end):
    """Hourly UTC frame shaped like pvlib.iotools.get_nasa_power output (ghi, temp_air, wind_speed)."""
    idx = pd.date_range(pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize() + pd.Timedelta(hours=23),
                        freq="h", tz="UTC")
    cs = solar.clearsky_irradiance(lat, lon, idx + pd.Timedelta(minutes=30))["ghi"].to_numpy()
    day = np.asarray((idx - idx[0]) / pd.Timedelta(days=1), dtype=float)
    k = 0.93 + 0.04 * np.sin(day * 1.7)
    hr = idx.hour.to_numpy()
    return pd.DataFrame({"ghi": cs * k, "temp_air": 27 + 6 * np.cos((hr - 9) / 24 * 2 * np.pi),
                         "wind_speed": 2.0}, index=idx)


def _use_db(mp, path):
    mp.setenv("SOLARDOCTOR_DB_URL", f"sqlite:///{path}")
    from solardoctor.db import session as s
    s._engine = None
    s._SessionLocal = None


@pytest.fixture(scope="module")
def seeded(tmp_path_factory):
    from _pytest.monkeypatch import MonkeyPatch
    mp = MonkeyPatch()
    root = tmp_path_factory.mktemp("seed")
    _use_db(mp, root / "seed.db")
    from solardoctor.db.session import get_session, init_db
    from solardoctor.seed.builder import run_seed
    init_db()
    db = get_session()
    rep = run_seed(db, fetcher=mock_nasa, cache_dir=root / "cache", window_end=END, env=ENV,
                   manifest_path=root / "cache" / "seed_manifest.json")
    yield dict(db=db, report=rep, root=root)
    db.close()
    mp.undo()
    from solardoctor.db import session as s
    s._engine = None
    s._SessionLocal = None


def _count(db, model):
    return db.scalar(sa.select(sa.func.count()).select_from(model))


def _plant(db, name):
    from solardoctor.physics.models import Plant
    return db.query(Plant).filter(Plant.name == name).one()


def _tel_df(db, plant_id):
    from solardoctor.physics.models import Telemetry
    return pd.read_sql(sa.select(Telemetry).where(Telemetry.plant_id == plant_id), db.get_bind(), parse_dates=["ts"])


# ------------------------------------------------------------------ structure
def test_plants_and_links(seeded):
    from solardoctor.db.models import Park
    from solardoctor.physics.models import Plant
    db = seeded["db"]
    plants = db.query(Plant).order_by(Plant.id).all()
    assert [p.name for p in plants] == ["Bhadla Block C", "PCCoE Rooftop", "Pavagada Unit 4"]
    assert [p.dc_kw for p in plants] == [50_000.0, 120.0, 25_000.0]
    assert all(p.tz == "Asia/Kolkata" and p.tariff_inr_kwh > 0 and 0 < p.tilt < 45 for p in plants)
    for p in plants:
        park = db.get(Park, p.park_id)
        assert park is not None and park.plant.id == p.id  # Park <-> Plant 1:1 link
    names = {s.name for s in _plant(db, "PCCoE Rooftop").strings}
    assert names == {f"S-0{i}" for i in range(1, 7)}
    assert len(_plant(db, "Bhadla Block C").inverters) == 10


def test_telemetry_counts_and_cadence(seeded):
    db = seeded["db"]
    for name, rows in (("Bhadla Block C", 2880), ("Pavagada Unit 4", 2880), ("PCCoE Rooftop", 2880 * 9)):
        df = _tel_df(db, _plant(db, name).id)
        assert len(df) == rows
        plant_level = df[df.inverter_id.isna() & df.string_id.isna()].sort_values("ts")
        assert len(plant_level) == 2880
        assert set(plant_level.ts.diff().dropna()) == {pd.Timedelta(minutes=15)}


def test_everything_is_labelled_simulated(seeded):
    from solardoctor.physics.models import Forecast, Inverter, Plant, PlantAlert, Telemetry, WeatherCache
    db = seeded["db"]
    for model in (Plant, Telemetry, PlantAlert):
        assert _count(db, model) > 0
        assert db.scalar(sa.select(sa.func.count()).select_from(model).where(model.source != "SIMULATED")) == 0
    assert all(f.model_name.endswith("SIMULATED") for f in db.query(Forecast))
    assert all(i.vendor == "SIMULATED" for i in db.query(Inverter))
    metas = db.query(WeatherCache).filter(WeatherCache.kind == "seed_meta").all()
    assert len(metas) == 3 and all(m.source == "SIMULATED" and "NASA_POWER" in m.payload_json for m in metas)
    from solardoctor.db.models import PanelFault
    assert all(f.notes.startswith("SIMULATED") for f in db.query(PanelFault))


def test_ac_never_above_rating_and_zero_at_night(seeded):
    db = seeded["db"]
    for spec in PLANTS:
        p = _plant(db, spec.name)
        plant_level = _tel_df(db, p.id)
        plant_level = plant_level[plant_level.inverter_id.isna()]
        assert plant_level.p_ac_kw.max() <= p.ac_kw + 1e-6
        night = plant_level[plant_level.poa_wm2 <= 0]
        assert len(night) > 500 and (night.p_ac_kw == 0).all()
        assert plant_level.p_ac_kw.max() > 0.5 * p.ac_kw  # and it does produce by day


# ------------------------------------------------------------------ physics-visible events
def _string_pi(db):
    p = _plant(db, "PCCoE Rooftop")
    df = _tel_df(db, p.id)
    df = df[df.string_id.notna() & (df.poa_wm2 > 500) & (df.p_expected_kw > 0)].copy()
    df["pi"] = df.p_ac_kw / df.p_expected_kw
    df["day"] = (df.ts.dt.floor("D") - df.ts.min().floor("D")).dt.days
    names = {s.id: s.name for s in p.strings}
    df["string"] = df.string_id.map(names)
    return df.groupby(["day", "string"]).pi.mean().unstack()


def test_s04_deficit_vs_physics_expected_power(seeded):
    pi = _string_pi(seeded["db"])
    healthy = [c for c in pi.columns if c != "S-04"]
    # Before the fault starts (day 10) S-04 is like its peers.
    early = pi.loc[2:8]
    assert (early["S-04"] - early[healthy].median(axis=1)).abs().max() < 0.02
    # Right after the fault starts: absolute PI of S-04 is 0.85-0.90, healthy strings ~1.0
    # (they only carry the plant-wide soiling, <= 2.5 % at this point).
    just_after = pi.loc[11:14]
    assert just_after["S-04"].between(0.85, 0.90).all(), just_after["S-04"]
    assert (just_after[healthy].to_numpy() > 0.95).all() and (just_after[healthy].to_numpy() < 1.02).all()
    # Throughout the fault, S-04 sits 10-15 % below its peers (soiling hits all strings equally).
    rel = pi.loc[11:, "S-04"] / pi.loc[11:, healthy].median(axis=1)
    assert rel.between(0.85, 0.90).all(), rel.describe()


def test_soiling_ramp_visible_on_plant_level(seeded):
    db = seeded["db"]
    p = _plant(db, "Bhadla Block C")
    df = _tel_df(db, p.id)
    df = df[df.inverter_id.isna() & (df.poa_wm2 > 500) & (df.p_expected_kw > 0) & (df.p_expected_kw < 0.9 * p.ac_kw)]
    df["day"] = (df.ts.dt.floor("D") - df.ts.min().floor("D")).dt.days
    daily = (df.p_ac_kw / df.p_expected_kw).groupby(df.day).mean()
    assert daily.loc[0:2].mean() == pytest.approx(1.0, abs=0.02)
    assert 0.88 <= daily.loc[27:29].mean() <= 0.94        # ~9 % soiling after 28 days at 0.3 %/day
    slope = np.polyfit(daily.index, daily.values, 1)[0]
    assert slope == pytest.approx(-0.003, abs=0.0006)       # injected 0.30 %/day recovered


def test_cloudy_spell_has_no_deficit_against_cloudy_irradiance(seeded):
    from solardoctor.physics.models import PlantAlert
    db = seeded["db"]
    p = _plant(db, "Bhadla Block C")
    df = _tel_df(db, p.id)
    df = df[df.inverter_id.isna() & (df.p_expected_kw > 0)].copy()
    df["day"] = (df.ts.dt.floor("D") - df.ts.min().floor("D")).dt.days
    daily_exp = df.groupby("day").p_expected_kw.mean()
    spell = list(CLOUDY_SPELL_DAYS)
    # The spell is genuinely cloudy ...
    assert daily_exp.loc[spell].max() < 0.5 * daily_exp.loc[[d - 4 for d in spell]].min()
    # ... but telemetry tracks the (cloudy) expected power: same PI as the clear days around it.
    ok = df[(df.poa_wm2 > 100) & (df.p_expected_kw < 0.9 * p.ac_kw)]
    pi = (ok.p_ac_kw / ok.p_expected_kw).groupby(ok.day).mean()
    around = pi.loc[[d for d in range(12, 21) if d not in spell]]
    assert (pi.loc[spell] - around.mean()).abs().max() < 0.03
    # and no alert is raised on those days (alerts need sustained deficits on eligible days)
    t0 = df.ts.min().floor("D")
    lo, hi = t0 + pd.Timedelta(days=spell[0]), t0 + pd.Timedelta(days=spell[-1] + 1)
    for a in db.query(PlantAlert).all():
        assert not (lo <= pd.Timestamp(a.timestamp) < hi), a.message


def test_alerts_come_from_the_physics_detector(seeded):
    from solardoctor.physics.models import PlantAlert
    db = seeded["db"]
    alerts = db.query(PlantAlert).all()
    types = {(a.plant_id, a.alert_type) for a in alerts}
    pc, bh, pv = (_plant(db, n).id for n in ("PCCoE Rooftop", "Bhadla Block C", "Pavagada Unit 4"))
    assert (pc, "string_underperformance") in types
    assert (bh, "soiling_loss") in types and (pv, "soiling_loss") in types
    s04 = [a for a in alerts if a.alert_type == "string_underperformance"]
    assert len(s04) == 1 and "[S-04]" in s04[0].message and 10 <= s04[0].deviation_percent <= 15
    assert all(a.severity in ("WARNING", "CRITICAL") and a.deviation_percent >= 5 for a in alerts)
    assert any(a.is_resolved and a.resolved_at is not None for a in alerts)   # historical (Pavagada cleaning)
    assert not any(a.is_resolved for a in alerts if a.plant_id == pc)


# ------------------------------------------------------------------ users / auth / API
def test_users_roles_and_login(seeded, monkeypatch):
    monkeypatch.setenv("SOLARDOCTOR_AUTH_MODE", "users")
    from solardoctor.api.app import app
    c = TestClient(app)
    for email, pw, role in (("admin@solardoctor.example", ADMIN_PW, "admin"),
                            ("technician@solardoctor.example", TECH_PW, "technician")):
        r = c.post("/api/v1/auth/login", json={"email": email, "password": pw})
        assert r.status_code == 200, r.text
        assert r.json()["user"]["role"] == role
    assert c.post("/api/v1/auth/login", json={"email": "technician@solardoctor.example",
                                              "password": "wrong-password-xyz"}).status_code == 401

    tech = c.post("/api/v1/auth/login", json={"email": "technician@solardoctor.example", "password": TECH_PW}).json()
    h = {"Authorization": f"Bearer {tech['token']}"}
    me = c.get("/api/v1/auth/me", headers=h).json()
    assert me["role"] == "technician" and me["project_ids"]
    # technician sees only faults assigned to them
    seen = {}
    for park in ("PARK_PCCOE_ROOFTOP", "PARK_BHADLA_C", "PARK_PAVAGADA_U4"):
        r = c.get(f"/api/v1/parks/{park}/faults", headers=h)
        assert r.status_code == 200, r.text
        seen[park] = len(r.json()["faults"])
    assert seen == {"PARK_PCCOE_ROOFTOP": 1, "PARK_BHADLA_C": 1, "PARK_PAVAGADA_U4": 0}


def test_api_returns_seeded_numbers(seeded):
    from solardoctor.api.app import app
    c = TestClient(app)
    plants = c.get("/api/v1/plants").json()
    assert {p["name"] for p in plants} >= {"Bhadla Block C", "PCCoE Rooftop", "Pavagada Unit 4"}
    assert all(p["source"] == "SIMULATED" for p in plants)
    pid = next(p["id"] for p in plants if p["name"] == "PCCoE Rooftop")
    s = c.get(f"/api/v1/forecast/{pid}/summary").json()
    assert s["record_count"] == 192 and s["total_predicted_kwh"] > 0 and s["total_actual_kwh"] > 0
    alerts = c.get("/api/v1/alerts", params={"plant_id": pid}).json()
    assert [a["alert_type"] for a in alerts].count("string_underperformance") == 1


def test_manifest_written(seeded):
    import json
    m = json.loads((seeded["root"] / "cache" / "seed_manifest.json").read_text())
    assert m["source"] == "SIMULATED" and m["cadence_min"] == 15
    assert m["injected"]["string_faults"][0]["string"] == "S-04"


# ------------------------------------------------------------------ idempotency (keep last: mutates)
def test_second_run_is_a_no_op_and_reset_rebuilds(seeded):
    from solardoctor.db.models import PanelFault, User
    from solardoctor.physics.models import Forecast, PlantAlert, Telemetry
    from solardoctor.seed.builder import run_seed
    db, root = seeded["db"], seeded["root"]
    models = (Telemetry, PlantAlert, Forecast, PanelFault, User)
    before = [_count(db, m) for m in models]
    rep = run_seed(db, fetcher=mock_nasa, cache_dir=root / "cache", window_end=END, env=ENV)
    assert [_count(db, m) for m in models] == before
    assert all(v["status"] == "exists" for v in rep.plants.values())
    assert all(pw is None for _, pw in rep.created_users.values())
    # --reset drops SIMULATED rows only (users survive) and the rebuild gives identical counts
    run_seed(db, fetcher=mock_nasa, cache_dir=root / "cache", window_end=END, env=ENV, reset=True)
    assert [_count(db, m) for m in models] == before


# ------------------------------------------------------------------ fallback + CLI guard
def test_synthetic_fallback_is_labelled_and_deterministic(tmp_path):
    times = pd.date_range("2026-03-01", periods=96 * 3, freq="15min", tz="UTC")

    def boom(*a):
        raise ConnectionError("no network")

    a = irr_mod.get_irradiance(27.5, 71.9, 230, "x", times, 7, boom, tmp_path)
    b = irr_mod.get_irradiance(27.5, 71.9, 230, "x", times, 7, boom, tmp_path)
    assert a.source == irr_mod.SRC_SYNTH and "not measured" in a.note and "ConnectionError" in a.note
    pd.testing.assert_frame_equal(a.frame, b.frame)
    assert a.frame.ghi.max() > 300 and (a.frame.ghi >= 0).all()
    off = irr_mod.get_irradiance(27.5, 71.9, 230, "x", times, 7, mock_nasa, tmp_path, allow_network=False)
    assert off.source == irr_mod.SRC_SYNTH and "offline" in off.note


def test_nasa_path_uses_cache(tmp_path):
    times = pd.date_range("2026-03-01", periods=96 * 30, freq="15min", tz="UTC")
    calls = []

    def counting(*a):
        calls.append(a)
        return mock_nasa(*a)

    r1 = irr_mod.get_irradiance(27.5, 71.9, 230, "bh", times, 1, counting, tmp_path)
    r2 = irr_mod.get_irradiance(27.5, 71.9, 230, "bh", times, 1, counting, tmp_path)
    assert r1.source == r2.source == irr_mod.SRC_NASA and len(calls) == 1
    assert list(tmp_path.glob("nasa_power_bh_*.csv"))


def test_window_discovery_ends_on_last_complete_day(tmp_path):
    def partial(lat, lon, start, end):
        df = mock_nasa(lat, lon, start, end)
        df.loc[df.index >= pd.Timestamp("2026-02-20", tz="UTC"), "ghi"] = np.nan  # GHI lags behind
        return df

    start, note = irr_mod.discover_window(partial, tmp_path, 27.5, 71.9, 30, today=pd.Timestamp("2026-03-10", tz="UTC"))
    assert start == pd.Timestamp("2026-01-21", tz="UTC") and "2026-02-19" in note


def test_production_guard(monkeypatch):
    monkeypatch.setenv("SOLARDOCTOR_ENV", "production")
    spec = importlib.util.spec_from_file_location("seed_cli", REPO_ROOT / "scripts" / "seed.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.main([]) == 2
