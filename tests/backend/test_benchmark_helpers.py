"""Unit tests for the pure helpers in scripts/benchmark.py (not the timings)."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "benchmark.py"


@pytest.fixture(scope="module")
def bench():
    spec = importlib.util.spec_from_file_location("axalon_benchmark_script", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses resolve types via sys.modules
    try:
        spec.loader.exec_module(module)
        yield module
    finally:
        sys.modules.pop(spec.name, None)


# ── percentile / summarize ────────────────────────────────────────────────────

def test_percentile_interpolates_linearly(bench):
    samples = [1.0, 2.0, 3.0, 4.0, 5.0]

    assert bench.percentile(samples, 50) == 3.0
    assert bench.percentile(samples, 0) == 1.0
    assert bench.percentile(samples, 100) == 5.0
    assert bench.percentile(samples, 95) == pytest.approx(4.8)


def test_percentile_is_order_independent(bench):
    assert bench.percentile([5.0, 1.0, 3.0], 50) == 3.0


def test_percentile_single_sample(bench):
    assert bench.percentile([7.5], 95) == 7.5


def test_percentile_rejects_empty_and_out_of_range(bench):
    with pytest.raises(ValueError):
        bench.percentile([], 50)
    with pytest.raises(ValueError):
        bench.percentile([1.0], 101)


def test_summarize_converts_seconds_to_ms(bench):
    stats = bench.summarize([0.010, 0.020, 0.030])

    assert stats["n"] == 3
    assert stats["mean_ms"] == pytest.approx(20.0)
    assert stats["p50_ms"] == pytest.approx(20.0)
    assert stats["p95_ms"] == pytest.approx(29.0)
    assert stats["min_ms"] == pytest.approx(10.0)
    assert stats["max_ms"] == pytest.approx(30.0)


def test_summarize_does_not_mutate_input(bench):
    samples = [0.3, 0.1, 0.2]
    bench.summarize(samples)
    assert samples == [0.3, 0.1, 0.2]


def test_summarize_rejects_empty(bench):
    with pytest.raises(ValueError):
        bench.summarize([])


# ── evaluate_target ───────────────────────────────────────────────────────────

def test_evaluate_target_pass_and_fail(bench):
    target = bench.Target(stage="detector", label="x", limit_ms=100.0, gpu_target=True)

    assert bench.evaluate_target({"p95_ms": 99.9}, target, on_gpu=True)["verdict"] == "PASS"
    assert bench.evaluate_target({"p95_ms": 100.0}, target, on_gpu=True)["verdict"] == "FAIL"


def test_evaluate_target_uses_configured_statistic(bench):
    target = bench.Target(stage="batch", label="x", limit_ms=60_000.0, gpu_target=True,
                          statistic="projected_ms")

    result = bench.evaluate_target({"p95_ms": 1.0, "projected_ms": 61_000.0}, target, on_gpu=True)

    assert result["verdict"] == "FAIL"
    assert result["measured_ms"] == 61_000.0


def test_evaluate_target_adds_cpu_caveat_for_gpu_targets(bench):
    gpu_target = bench.Target(stage="detector", label="x", limit_ms=100.0, gpu_target=True)
    any_target = bench.Target(stage="pdf", label="x", limit_ms=5_000.0, gpu_target=False)

    on_cpu = bench.evaluate_target({"p95_ms": 50.0}, gpu_target, on_gpu=False)
    assert on_cpu["verdict"] == "PASS"
    assert "GPU" in on_cpu["caveat"]

    assert bench.evaluate_target({"p95_ms": 50.0}, gpu_target, on_gpu=True)["caveat"] == ""
    assert bench.evaluate_target({"p95_ms": 50.0}, any_target, on_gpu=False)["caveat"] == ""


def test_evaluate_target_missing_stat_is_skip(bench):
    target = bench.Target(stage="ocr", label="x", limit_ms=2_000.0, gpu_target=False)

    assert bench.evaluate_target(None, target, on_gpu=False)["verdict"] == "SKIP"


def test_targets_match_spec_section_15_3(bench):
    limits = {t.stage: t.limit_ms for t in bench.TARGETS}

    assert limits == {
        "detector": 100.0,
        "pair": 500.0,
        "batch": 60_000.0,
        "pdf": 5_000.0,
        "ocr": 2_000.0,
    }


# ── project_batch / time_callable ─────────────────────────────────────────────

def test_project_batch_scales_linearly_to_target_size(bench):
    assert bench.project_batch(total_s=10.0, n_pairs=20, target_pairs=100) == pytest.approx(50_000.0)


def test_project_batch_rejects_zero_pairs(bench):
    with pytest.raises(ValueError):
        bench.project_batch(total_s=1.0, n_pairs=0, target_pairs=100)


def test_time_callable_runs_warmup_then_timed(bench):
    calls = []

    samples = bench.time_callable(lambda: calls.append(1), warmup=2, runs=3)

    assert len(calls) == 5
    assert len(samples) == 3
    assert all(s >= 0 for s in samples)


def test_time_callable_requires_a_timed_run(bench):
    with pytest.raises(ValueError):
        bench.time_callable(lambda: None, warmup=0, runs=0)
