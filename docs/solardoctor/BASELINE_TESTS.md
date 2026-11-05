# Baseline tests (AxalonSystems @ axalon/main, before any SolarDoctor change)

Environment: Python 3.13, CPU torch + ultralytics installed, run as
`PYTHONSAFEPATH=1 python -m pytest` (the `platform/` dir shadows stdlib `platform` otherwise).

| Suite | Passed | Failed | Skipped |
|---|---|---|---|
| `tests/backend` (59 files, pytest.ini `testpaths`) | **632** | **10** | 0 |
| `tests/test_api.py` | 7 | 0 | 0 |
| `tests/test_db.py` | 5 | 0 | 0 |
| `tests/test_imports.py` | 5 | 0 | 0 |
| `tests/test_orchestrator.py` | 8 | 0 | 0 |
| `tests/test_ml_dataset.py`, `test_select_winner.py`, `test_train_ultralytics.py`, `test_yolo_to_coco.py` | script-style files that call `sys.exit()`; they abort pytest collection (`test_ml_dataset`: 24 pass / 1 fail / 22 skip by its own runner) | | |

## The 10 baseline failures (all need `ml/checkpoints/best.pt`)

`best.pt` is a Git LFS object (114 MB) that this sandbox cannot fetch (LFS proxy denies Parakh20/AxalonSystems),
so every test that runs the real YOLO model fails with "unknown" weights:

- test_api_contract: parks_includes_park_after_batch, park_summary_returns_park_metadata,
  inspect_single_thermal_returns_job_id, inspect_with_rgb_returns_rgb_filename, report_downloads_succeed[json],
  park_grid_default_inspection
- test_model_info::test_describe_weights_real_checkpoint_is_yolo11
- test_park_grid_endpoint: grid_endpoint_returns_grid_after_batch, grid_endpoint_uses_explicit_inspection_id
- test_pipeline_unit::test_orchestrator_processes_a_batch_directly

Rule for later phases: pass count must stay >= 632 and the failing set must not grow.
These 10 become runnable once the weights are served from Hugging Face (`scripts/fetch_weights.py`).

Note (Phase E, this sandbox): `tests/backend` shows 9 failed + 1 skipped (the real-checkpoint test is skipped when weights are absent), i.e. the same 10 weight-dependent tests.
