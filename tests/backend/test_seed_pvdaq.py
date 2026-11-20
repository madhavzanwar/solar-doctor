"""PVDAQ importer mapping, tested on a FIXTURE (not real data) with the real OEDI column layout.

The fixture is generated here with obviously artificial values and the system name
``FIXTURE_NOT_REAL_DATA``.  The real 9068 import is run by hand (see docs/solardoctor/SEED_PLAN.md).
No network.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
import sqlalchemy as sa

from solardoctor.seed import pvdaq

REPO_ROOT = Path(__file__).resolve().parents[2]

AC_COLS = [
    "inverter_module_1.1_ac_power_(kw)_inv_1", "inverter_1_ac_power_(kw)_inv_150143",
    "inverter_2_ac_power_(kw)_inv_150144", "inverter_1_power_factor_inv_150145",
]
IRR_COLS = [
    "pyranometer_(class_a)_pad_1_poa_irradiance_(w/m2)_o_149723",
    "pyranometer_(class_a)_pad_1_poa_irradiance_temp_compensated_(w/m2)_o_149724",
    "pyranometer_(class_a)_pad_2_poa_irradiance_(w/m2)_o_149725",
]


LAT, LON = 40.3864, -104.5512  # Kersey, CO (from the 9068 metadata)


def make_files(tmp_path, utc_start: str, days: int = 2):
    """FIXTURE, NOT REAL DATA.  Artificial 5-minute rows whose diurnal shape follows the true pvlib sun
    position at Kersey, written the way the PVDAQ loggers do: on the DST-observing America/Denver wall clock
    (so the fall-back hour appears twice, the spring-forward hour is missing)."""
    import pvlib
    utc = pd.date_range(pd.Timestamp(utc_start, tz="UTC"), periods=days * 288, freq="5min")
    elev = pvlib.solarposition.get_solarposition(utc, LAT, LON)["apparent_elevation"].to_numpy()
    sun = np.clip(np.sin(np.radians(elev)), 0, None)
    idx = utc.tz_convert("America/Denver").tz_localize(None)
    ac = pd.DataFrame({
        AC_COLS[0]: 100 * sun, AC_COLS[1]: 400 * sun, AC_COLS[2]: 300 * sun, AC_COLS[3]: 1.0}, index=idx)
    ac.iloc[10, 2] = np.nan                                    # one gap in inverter 2
    ac.iloc[20, 1] = -2.0                                      # night-time negative reading
    irr = pd.DataFrame({IRR_COLS[0]: 1000 * sun, IRR_COLS[1]: 999 * sun, IRR_COLS[2]: 800 * sun}, index=idx)
    ac.index.name = irr.index.name = "measured_on"
    ac.to_csv(tmp_path / "ac.csv")
    irr.to_csv(tmp_path / "irr.csv")
    meta = {
        "System": {"system_id": 1, "public_name": "FIXTURE_NOT_REAL_DATA", "power(kW DC)": 1000.0, "timezone_code": 7},
        "Site": {"location": "Nowhere, XX", "latitude": LAT, "longitude": LON, "elevation(m)": 1500.0},
        "Mount": {"Mount 0": {"tracking": "t", "type": "single-axis tracker", "azimuth": 180.0, "tilt": 0.0}},
        "Inverters": {"Inverter 0": {"name": "fx_inv_1", "AC capacity(kW)": 500}, "Inverter 1": {"name": "fx_inv_2", "AC capacity(kW)": 400}},
        "Modules": {"Module 0": {"quantity": 100, "nameplate capacity(W)": 10.0, "temperature coefficient of maximum power(%C)": -0.28}},
    }
    (tmp_path / "meta.json").write_text(json.dumps(meta))
    return tmp_path


@pytest.fixture
def files(tmp_path):
    return make_files(tmp_path, "2024-06-01 06:00", days=2)


START, END = pd.Timestamp("2024-06-01", tz="UTC"), pd.Timestamp("2024-06-02", tz="UTC")


def _solar_noon_utc(day: str) -> pd.Timestamp:
    import pvlib
    t = pd.date_range(pd.Timestamp(day, tz="UTC"), periods=1440, freq="1min")
    el = pvlib.solarposition.get_solarposition(t, LAT, LON)["apparent_elevation"]
    return el.idxmax()


@pytest.mark.parametrize("day", ["2024-01-10", "2024-06-20"])  # MST (UTC-7) and MDT (UTC-6)
def test_diurnal_peak_lines_up_with_solar_noon_in_both_seasons(tmp_path, day):
    d0 = pd.Timestamp(day, tz="UTC")
    make_files(tmp_path, f"{day} 00:00", days=2)
    m = pvdaq.map_pvdaq(tmp_path / "ac.csv", tmp_path / "irr.csv", tmp_path / "meta.json", d0, d0 + pd.Timedelta(days=1))
    # one solar day in UTC: 08:00 on day d0 to 08:00 the next day (June sunset is after 00:00 UTC)
    t = m.telemetry.loc[d0 + pd.Timedelta(hours=8):d0 + pd.Timedelta(hours=32)]
    mins = np.asarray((t.index - d0) / pd.Timedelta(minutes=1), dtype=float)
    centroid = d0 + pd.Timedelta(minutes=float((mins * t["poa"]).sum() / t["poa"].sum()))
    assert abs(centroid - _solar_noon_utc(day)) <= pd.Timedelta(minutes=20), (centroid, _solar_noon_utc(day))
    assert abs(t["poa"].idxmax() - _solar_noon_utc(day)) <= pd.Timedelta(minutes=30)
    # the generator wrote local wall-clock noon at 12:00 (MST) / 13:00 (MDT) -> UTC 19:00 / 19:00 +- sun position
    assert any("America/Denver" in n for n in m.meta_notes)


def test_fall_back_hour_is_dropped_not_shifted(tmp_path):
    make_files(tmp_path, "2024-11-02 12:00", days=2)          # spans 2024-11-03 fall-back (01:00-02:00 twice)
    d0, d1 = pd.Timestamp("2024-11-02", tz="UTC"), pd.Timestamp("2024-11-04", tz="UTC")
    m = pvdaq.map_pvdaq(tmp_path / "ac.csv", tmp_path / "irr.csv", tmp_path / "meta.json", d0, d1)
    assert m.telemetry.index.is_unique and m.telemetry.index.is_monotonic_increasing
    # the repeated wall-clock hour (24 five-minute rows per file, 2 files) is dropped and reported
    assert any(n.startswith("timestamps:") and " 48 ambiguous" in n for n in m.meta_notes), m.meta_notes
    # daytime values still line up with the sun on both sides of the change
    noon_before = _solar_noon_utc("2024-11-02")
    noon_after = _solar_noon_utc("2024-11-03")
    for noon in (noon_before, noon_after):
        w = m.telemetry.loc[noon - pd.Timedelta(hours=3):noon + pd.Timedelta(hours=3), "poa"]
        assert abs(w.idxmax() - noon) <= pd.Timedelta(minutes=30)


def test_mapping_units_and_aggregation(files):
    m = pvdaq.map_pvdaq(files / "ac.csv", files / "irr.csv", files / "meta.json", START, END)
    p = m.plant
    assert p["source"] == "PVDAQ" and p["name"] == "PVDAQ 1 FIXTURE_NOT_REAL_DATA"
    assert (p["dc_kw"], p["ac_kw"], p["lat"], p["lon"], p["altitude_m"]) == (1000.0, 900.0, LAT, LON, 1500.0)
    assert p["tz"] == "America/Denver" and "single-axis tracker" in p["location"] and "baseline invalid" in p["location"]
    assert p["temp_coeff"] == pytest.approx(-0.0028) and p["module_count"] == 100
    assert [i["name"] for i in m.inverters] == ["fx_inv_1", "fx_inv_2"]
    t = m.telemetry
    assert set(t.index.to_series().diff().dropna()) <= {pd.Timedelta(minutes=15), pd.Timedelta(minutes=30)}
    noon = t.loc[_solar_noon_utc("2024-06-01").floor("15min")]
    assert noon["plant_ac"] == pytest.approx(noon["inv_1"] + noon["inv_2"]) and 650 < noon["plant_ac"] <= 700
    assert 850 < noon["poa"] < 1000                      # mean of the two non-compensated pyranometers (~900)
    assert (t[["inv_1", "inv_2"]] >= 0).all().all()      # negative night readings clipped ...
    assert any("1 negative inverter-AC" in n for n in m.meta_notes)  # ... and counted
    assert t["plant_ac"].notna().all()                   # bins with a missing inverter are dropped, not zero-filled


def test_bins_need_two_of_three_samples(tmp_path):
    make_files(tmp_path, "2024-06-01 06:00", days=1)
    ac = pd.read_csv(tmp_path / "ac.csv", index_col=0)
    # blank two of the three samples of one daytime bin for BOTH inverters, one sample of the next bin
    ac.iloc[130:132, [1, 2]] = np.nan
    ac.iloc[135, [1, 2]] = np.nan
    ac.to_csv(tmp_path / "ac.csv")
    m = pvdaq.map_pvdaq(tmp_path / "ac.csv", tmp_path / "irr.csv", tmp_path / "meta.json", START, END)
    raw = pd.DatetimeIndex(pd.read_csv(tmp_path / "ac.csv", index_col=0, parse_dates=True).index)
    bin_bad = raw[130].tz_localize("America/Denver").tz_convert("UTC").floor("15min")
    bin_ok = raw[135].tz_localize("America/Denver").tz_convert("UTC").floor("15min")
    assert bin_bad not in m.telemetry.index          # 1 of 3 samples: rejected
    assert bin_ok in m.telemetry.index               # 2 of 3 samples: kept


def test_write_is_idempotent_and_labelled(files, tmp_path, monkeypatch):
    monkeypatch.setenv("SOLARDOCTOR_DB_URL", f"sqlite:///{tmp_path / 'p.db'}")
    from solardoctor.db import session as s
    s._engine = s._SessionLocal = None
    from solardoctor.db.session import get_session, init_db
    from solardoctor.physics.models import Inverter, Plant, Telemetry
    init_db()
    db = get_session()
    m = pvdaq.map_pvdaq(files / "ac.csv", files / "irr.csv", files / "meta.json", START, END)
    r1 = pvdaq.write_mapped(db, m)
    n1 = db.scalar(sa.select(sa.func.count()).select_from(Telemetry))
    r2 = pvdaq.write_mapped(db, m)
    assert n1 == db.scalar(sa.select(sa.func.count()).select_from(Telemetry)) == r1["rows"] == r2["rows"] > 100
    assert db.query(Plant).count() == 1 and db.query(Inverter).count() == 2
    assert db.scalar(sa.select(sa.func.count()).select_from(Telemetry).where(Telemetry.source != "PVDAQ")) == 0
    assert db.query(Plant).one().source == "PVDAQ"
    # real data must never overwrite a differently-sourced plant of the same name
    pl = db.query(Plant).one()
    pl.source = "SIMULATED"
    db.commit()
    with pytest.raises(RuntimeError):
        pvdaq.write_mapped(db, m)
    db.close()
    s._engine = s._SessionLocal = None


def test_imported_pvdaq_plant_is_a_tracker_with_no_deficit_scan(files, tmp_path, monkeypatch):
    monkeypatch.setenv("SOLARDOCTOR_DB_URL", f"sqlite:///{tmp_path / 'pt.db'}")
    from solardoctor.db import session as s
    s._engine = s._SessionLocal = None
    from solardoctor.db.session import get_session, init_db
    from solardoctor.physics import deficit
    from solardoctor.physics.models import Plant, PlantAlert
    from solardoctor.physics.tracker import BASELINE_UNSUPPORTED_STATUS, is_tracker_plant
    init_db()
    db = get_session()
    pvdaq.write_mapped(db, pvdaq.map_pvdaq(files / "ac.csv", files / "irr.csv", files / "meta.json", START, END))
    plant = db.query(Plant).one()
    assert is_tracker_plant(plant)
    res = deficit.scan_and_persist(db, plant.id, START, END)
    assert res["status"] == BASELINE_UNSUPPORTED_STATUS == "baseline_unsupported_for_trackers" and res["events"] == []
    assert db.query(PlantAlert).count() == 0
    db.close()
    s._engine = s._SessionLocal = None


def test_empty_window_is_an_error(files):
    with pytest.raises(pvdaq.PvdaqUnavailable):
        pvdaq.map_pvdaq(files / "ac.csv", files / "irr.csv", files / "meta.json",
                        pd.Timestamp("2030-01-01", tz="UTC"), pd.Timestamp("2030-01-02", tz="UTC"))


def test_cli_offline_mode(files, tmp_path):
    env = {"SOLARDOCTOR_DB_URL": f"sqlite:///{tmp_path / 'cli.db'}", "PYTHONSAFEPATH": "1",
           "PYTHONPATH": os.pathsep.join([str(REPO_ROOT / "backend"), str(REPO_ROOT)]),
           # a scrubbed environment, keeping only what the interpreter needs to start (Windows needs SYSTEMROOT)
           **{k: os.environ[k] for k in ("PATH", "SYSTEMROOT") if k in os.environ}}
    run = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "import_pvdaq.py"), "--ac-csv", str(files / "ac.csv"),
         "--irr-csv", str(files / "irr.csv"), "--metadata", str(files / "meta.json"),
         "--start", "2024-06-01", "--end", "2024-06-02"], capture_output=True, text=True, env=env)
    assert run.returncode == 0, run.stderr
    assert "[PVDAQ] plant 'PVDAQ 1 FIXTURE_NOT_REAL_DATA'" in run.stdout
    partial = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "import_pvdaq.py"), "--ac-csv", str(files / "ac.csv")],
        capture_output=True, text=True, env=env)
    assert partial.returncode != 0
