# Performance Benchmarks

Measured with `scripts/benchmark.py` against the targets in
[`AXALON_PLATFORM_SPEC.md` §15.3](AXALON_PLATFORM_SPEC.md).

```bash
# GPU (auto-detects CUDA, falls back to CPU)
PYTHONSAFEPATH=1 python scripts/benchmark.py --runs 20 --batch-runs 2 --json bench.json

# CPU-only, quick
PYTHONSAFEPATH=1 python scripts/benchmark.py --device cpu --runs 3 --warmup 1
```

How it measures:

- Every stage runs `--warmup` untimed calls, then `--runs` calls timed with `time.perf_counter`.
  Use at least 5 warm-up calls on GPU. With only 2, the detector p50 came out around 2x slower
  because CUDA/cuDNN had not warmed up yet.
- **detector**: `SolarDetector.predict()` on `tests/fixtures/sample_mission/thermal/img_001.jpg` (640×512).
- **pair**: `InspectionOrchestrator.inspect_pair()` (thermal + RGB): detection, GPS, panel lookup,
  annotated output and RGB fusion.
- **batch**: `InspectionOrchestrator.inspect_folder()` over the 20-pair synthetic fixture, with SQLite
  writes and dedup/reconcile included. The 100-pair target is checked by scaling the mean batch
  time linearly from 20 pairs to 100.
- **pdf**: `generate_pdf_report()` on the batch result (WeasyPrint).
- **ocr**: `PanelNumberOCR.extract_ids_from_rgb()` on one 640×512 RGB fixture image. This stage is skipped
  if EasyOCR is not installed or fails to start. The first run downloads the EasyOCR models to `~/.EasyOCR`.
- Per-item targets are judged on **p95**. A GPU target measured on CPU still gets PASS/FAIL, but the
  result is flagged as informational only.
- The fixture is synthetic, so the timings exercise the full code path but not real flight imagery.

## Results — 2026-09-13

Host: laptop, 13th Gen Intel Core i5-13500H, NVIDIA GeForce RTX 3050 4GB Laptop GPU.
Python 3.12.3, torch 2.11.0+cu130, Ultralytics 8.4.52, EasyOCR 1.7.2, WeasyPrint 68.1.
Weights: `ml/checkpoints/best.pt`: YOLO11x, 109.1 MB, sha256 prefix `fabb41c88f9d`.

### GPU (CUDA:0 RTX 3050 Laptop) — warmup 5, runs 20, batch runs 2

| Stage | n | p50 ms | p95 ms | mean ms | Target | Verdict |
|---|---|---|---|---|---|---|
| Single image inference | 20 | 76.4 | 83.9 | 77.4 | < 100 ms (GPU) | PASS |
| Single pair full pipeline | 20 | 79.5 | 86.1 | 80.6 | < 500 ms (GPU) | PASS |
| Batch, 20 pairs (per run) | 2 | 1,911 | 2,151 | 1,911 | — | — |
| Batch of 100 pairs (projected) | — | — | — | 9,555 | < 60 s (GPU) | PASS |
| PDF report generation | 20 | 823 | 1,720 | 1,023 | < 5 s | PASS |
| OCR panel-ID extraction / image | 20 | 95.1 | 100.0 | 92.5 | < 2 s | PASS |

### CPU only (i5-13500H) — warmup 1, runs 3, batch runs 1

| Stage | n | p50 ms | p95 ms | mean ms | Target | Verdict |
|---|---|---|---|---|---|---|
| Single image inference | 3 | 665 | 948 | 760 | < 100 ms (GPU) | FAIL (GPU target, informational) |
| Single pair full pipeline | 3 | 1,097 | 3,131 | 1,704 | < 500 ms (GPU) | FAIL (GPU target, informational) |
| Batch, 20 pairs (per run) | 1 | 16,076 | 16,076 | 16,076 | — | — |
| Batch of 100 pairs (projected) | — | — | — | 80,379 | < 60 s (GPU) | FAIL (GPU target, informational) |
| PDF report generation | 3 | 440 | 670 | 524 | < 5 s | PASS |
| OCR panel-ID extraction / image | 3 | 1,253 | 1,346 | 1,287 | < 2 s | PASS |

Notes:

- On the GPU, all five §15.3 targets pass. YOLO11x inference on an entry-level 4 GB laptop GPU
  takes about 77 ms, which leaves little headroom under the 100 ms target. A larger model or a
  thermally throttled GPU could exceed it.
- CPU-only (for example, a Hugging Face Space with no GPU) is roughly 8–10× slower for inference
  and does not meet the GPU targets. PDF generation and OCR stay within their targets.
- The first PDF generated in a fresh process takes much longer, because WeasyPrint loads its fonts
  on first use. A spot check with no warm-up (single pair, CPU) took 3.2 s, which is still under
  5 s but not by much. The warm-run numbers above exclude this.
- The CPU run used only 3 timed runs, so its p95 is noisy. The 3.1 s pair p95 comes from one outlier run.
