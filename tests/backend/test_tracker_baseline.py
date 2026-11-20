"""Test generalized single-axis tracker baseline model."""
from __future__ import annotations

import pandas as pd
from types import SimpleNamespace
from solardoctor.physics.tracker_baseline import compute_tracker_expected_power


def test_tracker_expected_power_curve():
    plant = SimpleNamespace(
        latitude=18.65,
        longitude=73.76,
        capacity_kw=100.0,
        inverter_capacity_kw=90.0,
        altitude_m=560.0,
        temp_coeff=-0.004,
    )
    # Mid-day in Pune: 06:00 to 12:00 UTC (11:30 to 17:30 IST)
    times = pd.date_range("2026-11-20 06:00", "2026-11-20 12:00", freq="1h", tz="UTC")
    ghi = pd.Series([800.0, 950.0, 900.0, 750.0, 500.0, 200.0, 50.0], index=times)

    df = compute_tracker_expected_power(plant, times, ghi=ghi)

    assert "p_ac_kw" in df.columns
    assert "poa_global" in df.columns
    assert "tracker_tilt" in df.columns
    assert len(df) == len(times)
    # Midday peak should generate substantial power
    assert df["p_ac_kw"].max() > 40.0
    # Tilt angles should be within [-60, 60] max angle range
    assert (df["tracker_tilt"] >= 0).all() and (df["tracker_tilt"] <= 60.0).all()
