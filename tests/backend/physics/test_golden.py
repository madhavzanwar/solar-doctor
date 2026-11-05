"""Golden tests: the SolarDoctor port must reproduce SolarPulseAI outputs for identical inputs.

* test_matches_captured: compares against outputs captured from the original code
  (golden/solarpulse_golden.json; regenerate with make_golden.py).
* test_matches_live_original: compares directly against the SolarPulse clone when present.
"""
import json
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))

import golden_cases  # noqa: E402
import sp_original  # noqa: E402

GOLDEN = HERE / "golden" / "solarpulse_golden.json"


def _assert_close(a, b, path="root"):
    if isinstance(b, dict):
        assert isinstance(a, dict) and set(a) == set(b), f"{path}: keys {sorted(set(a) ^ set(b))}"
        for k in b:
            _assert_close(a[k], b[k], f"{path}.{k}")
    elif isinstance(b, list):
        assert isinstance(a, list) and len(a) == len(b), f"{path}: length"
        for i, (x, y) in enumerate(zip(a, b)):
            _assert_close(x, y, f"{path}[{i}]")
    elif isinstance(b, float) or isinstance(a, float):
        assert a == pytest.approx(b, rel=1e-6, abs=1e-6), path
    else:
        assert a == b, path


@pytest.fixture(scope="module")
def ported():
    return golden_cases.run_cases(golden_cases.ours())


def test_matches_captured(ported):
    captured = json.loads(GOLDEN.read_text())
    assert set(ported) == set(captured)
    for key in captured:
        _assert_close(json.loads(json.dumps(ported[key])), captured[key], key)


@pytest.mark.skipif(not sp_original.available(), reason="SolarPulseAI clone not present")
def test_matches_live_original(ported):
    original = golden_cases.run_cases(golden_cases.original())
    _assert_close(json.loads(json.dumps(ported)), json.loads(json.dumps(original)))


def test_golden_covers_every_ported_function():
    captured = json.loads(GOLDEN.read_text())
    for key in ("pvlib_features", "pipeline_21", "clip_array", "clip_metrics", "clip_service",
                "soiling_series", "soiling_metrics", "soiling_service", "ramp_points", "ramp_summary",
                "adapter_status", "adapter_adjust", "lgbm_pred", "prob_pred", "deviation", "severity",
                "diagnosis", "taxonomy", "irradiance_estimate", "weather_hourly", "physics_power"):
        assert captured[key], key
    assert len(captured["pipeline_21"]) == 21
