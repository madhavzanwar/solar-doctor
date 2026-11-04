"""benchmark.py — measure the platform against the performance targets.

Targets come from docs/AXALON_PLATFORM_SPEC.md §15.3:

    single image inference   < 100 ms   (GPU)
    single pair pipeline     < 500 ms   (GPU)
    batch of 100 pairs       < 60 s     (GPU)
    PDF report generation    < 5 s
    OCR panel-ID extraction  < 2 s / image

Each stage does warm-up runs, then N timed runs with time.perf_counter, and
reports p50 / p95 / mean. Per-item targets are judged on p95. The batch target
is judged on the mean batch time over the synthetic fixture
(tests/fixtures/sample_mission, 20 pairs) projected linearly to 100 pairs.
GPU targets measured on CPU still get PASS/FAIL, flagged with a caveat.

Usage:
    PYTHONSAFEPATH=1 python scripts/benchmark.py --device auto --runs 10
    PYTHONSAFEPATH=1 python scripts/benchmark.py --device cpu --runs 3 --json out.json
    PYTHONSAFEPATH=1 python scripts/benchmark.py --stages detector,pdf
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import platform as _stdlib_platform  # PYTHONSAFEPATH=1 keeps this the stdlib module
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "sample_mission"
BATCH_TARGET_PAIRS = 100
ALL_STAGES = ("detector", "pair", "batch", "pdf", "ocr")


@dataclass(frozen=True)
class Target:
    stage: str
    label: str
    limit_ms: float
    gpu_target: bool
    statistic: str = "p95_ms"


TARGETS: tuple[Target, ...] = (
    Target("detector", "Single image inference", 100.0, gpu_target=True),
    Target("pair", "Single pair full pipeline", 500.0, gpu_target=True),
    Target("batch", f"Batch of {BATCH_TARGET_PAIRS} pairs (projected)", 60_000.0,
           gpu_target=True, statistic="projected_ms"),
    Target("pdf", "PDF report generation", 5_000.0, gpu_target=False),
    Target("ocr", "OCR panel-ID extraction / image", 2_000.0, gpu_target=False),
)


# ── Pure helpers (unit-tested) ───────────────────────────────────────────────

def percentile(samples: list[float], pct: float) -> float:
    """Linear-interpolated percentile (same as numpy's default method)."""
    if not samples:
        raise ValueError("percentile of empty sample set")
    if not 0 <= pct <= 100:
        raise ValueError(f"percentile must be within [0, 100], got {pct}")
    ordered = sorted(samples)
    rank = (len(ordered) - 1) * pct / 100
    lo, hi = math.floor(rank), math.ceil(rank)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (rank - lo)


def summarize(samples_s: list[float]) -> dict:
    """p50/p95/mean/min/max in milliseconds for a list of durations in seconds."""
    if not samples_s:
        raise ValueError("no samples to summarize")
    ms = [s * 1000 for s in samples_s]
    return {
        "n": len(ms),
        "mean_ms": sum(ms) / len(ms),
        "p50_ms": percentile(ms, 50),
        "p95_ms": percentile(ms, 95),
        "min_ms": min(ms),
        "max_ms": max(ms),
    }


def project_batch(total_s: float, n_pairs: int, target_pairs: int) -> float:
    """Linearly project a batch wall time (s) over n_pairs to target_pairs (ms)."""
    if n_pairs <= 0:
        raise ValueError("n_pairs must be positive")
    return total_s / n_pairs * target_pairs * 1000


def evaluate_target(stats: dict | None, target: Target, on_gpu: bool) -> dict:
    """PASS/FAIL/SKIP for one target, with a caveat when a GPU target ran on CPU."""
    result = {**asdict(target), "measured_ms": None, "verdict": "SKIP", "caveat": ""}
    if stats is None or stats.get(target.statistic) is None:
        return result
    measured = stats[target.statistic]
    result["measured_ms"] = measured
    result["verdict"] = "PASS" if measured < target.limit_ms else "FAIL"
    if target.gpu_target and not on_gpu:
        result["caveat"] = "GPU target measured on CPU (informational only)"
    return result


def time_callable(fn: Callable[[], object], warmup: int, runs: int) -> list[float]:
    """Call fn `warmup` times untimed, then `runs` times; return durations (s)."""
    if runs < 1:
        raise ValueError("runs must be >= 1")
    for _ in range(max(warmup, 0)):
        fn()
    samples = []
    for _ in range(runs):
        t0 = time.perf_counter()
        fn()
        samples.append(time.perf_counter() - t0)
    return samples


# ── Environment ──────────────────────────────────────────────────────────────

def resolve_device(requested: str) -> tuple[str, bool, str]:
    """Return (ultralytics device arg, on_gpu, human-readable device name)."""
    import torch

    cpu_name = _stdlib_platform.processor() or _stdlib_platform.machine()
    try:
        with open("/proc/cpuinfo") as fh:
            cpu_name = next(line.split(":", 1)[1].strip() for line in fh if line.startswith("model name"))
    except (OSError, StopIteration):
        pass

    wants_gpu = requested != "cpu" and torch.cuda.is_available()
    if requested not in ("auto", "cpu") and not torch.cuda.is_available():
        print(f"[warn] CUDA device '{requested}' requested but unavailable — using CPU", file=sys.stderr)
    if not wants_gpu:
        return "cpu", False, f"CPU: {cpu_name}"
    index = 0 if requested == "auto" else int(requested)
    return str(index), True, f"CUDA:{index} {torch.cuda.get_device_name(index)} (host CPU: {cpu_name})"


def ensure_fixture() -> Path:
    if not (FIXTURE_DIR / "thermal").is_dir():
        raise SystemExit(
            f"Fixture missing at {FIXTURE_DIR}. Generate it with:\n"
            f"  PYTHONSAFEPATH=1 python scripts/make_sample_mission.py"
        )
    return FIXTURE_DIR


# ── Stages ───────────────────────────────────────────────────────────────────

class Bench:
    def __init__(self, device: str, weights: Path, workdir: Path, warmup: int, runs: int, batch_runs: int):
        from axalon.pipeline.orchestrator import InspectionOrchestrator

        self.warmup, self.runs, self.batch_runs = warmup, runs, batch_runs
        self.fixture = ensure_fixture()
        self.thermal = sorted((self.fixture / "thermal").glob("*.jpg"))[0]
        self.rgb = self.fixture / "rgb" / self.thermal.name
        self.workdir = workdir
        self.orch = InspectionOrchestrator(
            weights_path=weights,
            device=device,
            output_dir=workdir / "output",
            db_url=f"sqlite:///{workdir / 'bench.db'}",
        )
        self.batch_result: dict | None = None

    def detector(self) -> dict:
        return summarize(time_callable(lambda: self.orch.detector.predict(self.thermal), self.warmup, self.runs))

    def pair(self) -> dict:
        run = lambda: self.orch.inspect_pair(self.thermal, self.rgb, park_id="BENCH")
        return summarize(time_callable(run, self.warmup, self.runs))

    def batch(self) -> dict:
        from axalon.pipeline.ingest import find_image_pairs

        n_pairs = len(find_image_pairs(self.fixture))
        results: list[dict] = []
        counter = iter(range(10_000))
        run = lambda: results.append(self.orch.inspect_folder(self.fixture, park_id=f"BENCH_{next(counter)}"))
        stats = summarize(time_callable(run, warmup=0, runs=self.batch_runs))
        self.batch_result = results[-1]
        stats["pairs_per_run"] = n_pairs
        stats["projected_ms"] = project_batch(stats["mean_ms"] / 1000, n_pairs, BATCH_TARGET_PAIRS)
        return stats

    def pdf(self) -> dict:
        from axalon.reporting.report import generate_pdf_report

        source = self.batch_result or {
            "park_id": "BENCH",
            "results": [self.orch.inspect_pair(self.thermal, self.rgb, park_id="BENCH")],
        }
        out = self.workdir / "bench_report.pdf"
        stats = summarize(time_callable(lambda: generate_pdf_report(source, out), self.warmup, self.runs))
        stats["source"] = "batch result" if self.batch_result else "single pair result"
        return stats

    def ocr(self, on_gpu: bool) -> dict:
        import importlib.util

        if importlib.util.find_spec("easyocr") is None:
            return {"skipped": "easyocr not installed"}
        from ml.src.utils import load_bgr
        from axalon.park.numbering import PanelNumberOCR

        try:
            reader = PanelNumberOCR(gpu=on_gpu)
        except Exception as exc:  # model download / CUDA init failures
            return {"skipped": f"EasyOCR init failed: {exc}"}
        if reader.reader is None:
            return {"skipped": "easyocr import failed"}
        image = load_bgr(self.rgb)
        return summarize(time_callable(lambda: reader.extract_ids_from_rgb(image), self.warmup, self.runs))


# ── Reporting ────────────────────────────────────────────────────────────────

def format_report(report: dict) -> str:
    lines = [
        f"Axalon benchmark — {report['timestamp']}",
        f"Device : {report['device']}",
        f"Weights: {report['weights']['weights_path']} — {report['weights']['name']}, "
        f"{report['weights']['size_mb']} MB, sha256 {report['weights']['sha256']}",
        f"Runs   : warmup={report['config']['warmup']} runs={report['config']['runs']} "
        f"batch_runs={report['config']['batch_runs']}",
        "",
        f"{'stage':<10}{'n':>4}{'p50 ms':>11}{'p95 ms':>11}{'mean ms':>11}",
    ]
    for stage, stats in report["stages"].items():
        if "skipped" in stats:
            lines.append(f"{stage:<10}  skipped: {stats['skipped']}")
            continue
        lines.append(f"{stage:<10}{stats['n']:>4}{stats['p50_ms']:>11.1f}{stats['p95_ms']:>11.1f}{stats['mean_ms']:>11.1f}")
    lines += ["", f"{'target':<40}{'limit ms':>10}{'measured':>11}  verdict"]
    for t in report["targets"]:
        measured = "-" if t["measured_ms"] is None else f"{t['measured_ms']:.1f}"
        caveat = f"  ({t['caveat']})" if t["caveat"] else ""
        lines.append(f"{t['label']:<40}{t['limit_ms']:>10.0f}{measured:>11}  {t['verdict']}{caveat}")
    return "\n".join(lines)


def _timed_stats(results: dict[str, dict], stage: str) -> dict | None:
    """Stats for a stage that actually ran; None if not selected or skipped."""
    stats = results.get(stage)
    return None if stats is None or "skipped" in stats else stats


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--device", default="auto", help="auto | cpu | CUDA index (e.g. 0)")
    p.add_argument("--runs", type=int, default=10, help="timed runs per stage")
    p.add_argument("--warmup", type=int, default=5,
                   help="untimed warm-up runs per stage (<5 leaves CUDA/cuDNN cold: ~2x p50)")
    p.add_argument("--batch-runs", type=int, default=1, help="timed runs of the full fixture batch")
    p.add_argument("--stages", default=",".join(ALL_STAGES), help=f"comma list from {ALL_STAGES}")
    p.add_argument("--weights", type=Path, default=REPO_ROOT / "ml" / "checkpoints" / "best.pt")
    p.add_argument("--json", type=Path, dest="json_out", help="write the full report as JSON")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    stages = [s.strip() for s in args.stages.split(",") if s.strip()]
    unknown = set(stages) - set(ALL_STAGES)
    if unknown:
        raise SystemExit(f"Unknown stage(s): {sorted(unknown)}")

    logging.disable(logging.INFO)  # per-image INFO logs would drown the table
    from axalon.core.model_info import describe_weights

    device, on_gpu, device_name = resolve_device(args.device)
    results: dict[str, dict] = {}
    with tempfile.TemporaryDirectory(prefix="axalon-bench-") as tmp:
        bench = Bench(device, args.weights, Path(tmp), args.warmup, args.runs, args.batch_runs)
        for stage in ALL_STAGES:  # fixed order: pdf reuses the batch result
            if stage not in stages:
                continue
            print(f"[bench] {stage} ...", file=sys.stderr, flush=True)
            results[stage] = bench.ocr(on_gpu) if stage == "ocr" else getattr(bench, stage)()

    report = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "device": device_name,
        "on_gpu": on_gpu,
        "python": sys.version.split()[0],
        "weights": describe_weights(args.weights),
        "config": {"warmup": args.warmup, "runs": args.runs, "batch_runs": args.batch_runs},
        "stages": results,
        "targets": [
            evaluate_target(_timed_stats(results, t.stage), t, on_gpu)
            for t in TARGETS
        ],
    }
    print(format_report(report))
    if args.json_out:
        args.json_out.write_text(json.dumps(report, indent=2))
        print(f"\nJSON written to {args.json_out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
