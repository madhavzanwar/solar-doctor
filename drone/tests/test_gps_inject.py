# drone/tests/test_gps_inject.py
import pytest
from drone.agent.gps_inject import nearest_fix, TelemetryFix


def _log():
    return [
        TelemetryFix(ts=100.0, lat=28.40, lon=77.10, alt_rel_m=40.0),
        TelemetryFix(ts=100.5, lat=28.41, lon=77.10, alt_rel_m=40.0),
        TelemetryFix(ts=101.0, lat=28.42, lon=77.10, alt_rel_m=41.0),
    ]


def test_picks_closest_sample_in_time():
    fix = nearest_fix(_log(), frame_ts=100.6, tolerance_s=0.5)
    assert fix is not None
    assert fix.lat == 28.41  # 100.5 is nearest to 100.6


def test_returns_none_outside_tolerance():
    assert nearest_fix(_log(), frame_ts=200.0, tolerance_s=0.5) is None


def test_empty_log_returns_none():
    assert nearest_fix([], frame_ts=100.0, tolerance_s=0.5) is None


def test_exact_match():
    fix = nearest_fix(_log(), frame_ts=101.0, tolerance_s=0.5)
    assert fix.alt_rel_m == 41.0
