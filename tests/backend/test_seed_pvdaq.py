"""PVDAQ importer mapping, tested on a FIXTURE (not real data) with the real OEDI column layout.

The fixture is generated here with obviously artificial values and the system name
``FIXTURE_NOT_REAL_DATA``.  The real 9068 import is run by hand (see docs/solardoctor/SEED_PLAN.md).
No network.
"""
from __future__ import annotations

import json
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


@pytest.fixture
def files(tmp_path):
    # FIXTURE, NOT REAL DATA: 2 days of 5-minute rows in local standard time (UTC-7).
    idx = pd.date_range("2024-06-01 00:05", "2024-06-03 00:00", freq="5min")
    hour = idx.hour + idx.minute / 60
    sun = np.clip(np.sin((hour - 6) / 12 * np.pi), 0, None)
    ac = pd.DataFrame({
        AC_COLS[0]: 100 * sun, AC_COLS[1]: 400 * sun, AC_COLS[2]: 300 * sun, AC_COLS[3]: 1.0}, index=idx)
    ac.loc[idx[10], AC_COLS[2]] = np.nan                       # one gap in inverter 2
    ac.loc[idx[20], AC_COLS[1]] = -2.0                         # night-time negative reading
    irr = pd.DataFrame({IRR_COLS[0]: 1000 * sun, IRR_COLS[1]: 999 * sun, IRR_COLS[2]: 800 * sun}, index=idx)
    ac.index.name = irr.index.name = "measured_on"
    ac.to_csv(tmp_path / "ac.csv")
    irr.to_csv(tmp_path / "irr.csv")
    meta = {
        "System": {"system_id": 1, "public_name": "FIXTURE_NOT_REAL_DATA", "power(kW DC)": 1000.0, "timezone_code": 7},
        "Site": {"location": "Nowhere, XX", "latitude": 40.0, "longitude": -105.0, "elevation(m)": 1500.0},
        "Mount": {"Mount 0": {"tracking": "t", "type": "single-axis tracker", "azimuth": 180.0, "tilt": 0.0}},
        "Inverters": {"Inverter 0": {"name": "fx_inv_1", "AC capacity(kW)": 500}, "Inverter 1": {"name": "fx_inv_2", "AC capacity(kW)": 400}},
        "Modules": {"Module 0": {"quantity": 100, "nameplate capacity(W)": 10.0, "temperature coefficient of maximum power(%C)": -0.28}},
    }
    (tmp_path / "meta.json").write_text(json.dumps(meta))
    return tmp_path


START, END = pd.Timestamp("2024-06-01", tz="UTC"), pd.Timestamp("2024-06-02", tz="UTC")


def test_mapping_units_and_aggregation(files):
    m = pvdaq.map_pvdaq(files / "ac.csv", files / "irr.csv", files / "meta.json", START, END)
    p = m.plant
    assert p["source"] == "PVDAQ" and p["name"] == "PVDAQ 1 FIXTURE_NOT_REAL_DATA"
    assert (p["dc_kw"], p["ac_kw"], p["lat"], p["lon"], p["altitude_m"]) == (1000.0, 900.0, 40.0, -105.0, 1500.0)
    assert p["temp_coeff"] == pytest.approx(-0.0028) and p["module_count"] == 100
    assert [i["name"] for i in m.inverters] == ["fx_inv_1", "fx_inv_2"]
    t = m.telemetry
    # 15-minute bins in UTC (local 00:00 MST = 07:00 UTC) and local noon (19:00 UTC) peaks near 700 kW
    assert set(t.index.to_series().diff().dropna()) <= {pd.Timedelta(minutes=15), pd.Timedelta(minutes=30)}
    assert t.index[0] >= pd.Timestamp("2024-06-01 07:00", tz="UTC")
    noon = t.loc["2024-06-01 19:00":"2024-06-01 19:00"].iloc[0]
    assert noon["plant_ac"] == pytest.approx(noon["inv_1"] + noon["inv_2"]) and 650 < noon["plant_ac"] <= 700
    assert 850 < noon["poa"] < 1000                      # mean of the two non-compensated pyranometers (900)
    assert (t[["inv_1", "inv_2"]] >= 0).all().all()      # negative night readings clipped
    assert t["plant_ac"].notna().all()                   # bins with a missing inverter are dropped, not zero-filled


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


def test_empty_window_is_an_error(files):
    with pytest.raises(pvdaq.PvdaqUnavailable):
        pvdaq.map_pvdaq(files / "ac.csv", files / "irr.csv", files / "meta.json",
                        pd.Timestamp("2030-01-01", tz="UTC"), pd.Timestamp("2030-01-02", tz="UTC"))


def test_cli_offline_mode(files, tmp_path):
    env = {"SOLARDOCTOR_DB_URL": f"sqlite:///{tmp_path / 'cli.db'}", "PYTHONSAFEPATH": "1",
           "PYTHONPATH": f"{REPO_ROOT / 'backend'}:{REPO_ROOT}", "PATH": "/usr/bin:/bin"}
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
