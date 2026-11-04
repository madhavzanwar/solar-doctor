# Axalon Systems

[![CI](https://github.com/Parakh20/AxalonSystems/actions/workflows/ci.yml/badge.svg)](https://github.com/Parakh20/AxalonSystems/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

Axalon is a drone-based thermal inspection platform for solar parks. A drone
flies a park, captures thermal IR + RGB image pairs, and Axalon detects panel
faults (hot spots, bypass diodes, string outages, soiling, ...), maps each
fault to a physical panel, and produces operator reports (JSON, Excel,
GeoJSON, PDF).

The repository holds the full stack:

| Layer | Directory | What it is |
|---|---|---|
| **ML model** | `ml/` | Ultralytics YOLO11x thermal anomaly detector (11 fault classes), training + evaluation tooling |
| **Platform API** | `platform/` (Python package `axalon`) | FastAPI backend: ingest, detection, thermal/RGB fusion, panel localization, reporting, persistence |
| **Operator dashboard** | `website/nextjs/` | Next.js 14 app: marketing site at `/` and the operator platform UI at `/platform` |
| Drone ops (optional) | `drone/` | On-drone agent (MAVLink, WebRTC video) and a WebSocket relay for live operations |

## How the layers connect

```
 drone / mission folder                 Next.js dashboard (:3000/platform)
 thermal + RGB JPEGs (EXIF GPS)          upload, job queue, park map, reports
            │                                        │  HTTP (NEXT_PUBLIC_AXALON_API_URL)
            ▼                                        ▼
 ┌──────────────────────────────────────────────────────────────────┐
 │ FastAPI  (platform/api, :8000)                                   │
 │   pipeline/  ingest → detect → fuse → localize → report          │
 │   core/      detector (loads ml/checkpoints/best.pt), fusion, geo│
 │   park/      panel numbering (OCR + auto-grid)                   │
 │   reporting/ JSON · Excel · GeoJSON · PDF  → output/{batch_id}/  │
 │   db/        SQLAlchemy + Alembic (SQLite locally, Postgres prod)│
 └──────────────────────────────────────────────────────────────────┘
            ▲
            │ imports ml.src.utils (class list, severity map, drawing)
 ml/  YOLO11x weights + training/eval scripts
```

- The **ML layer** owns the model and the canonical class/severity
  definitions (`ml/src/utils.py`). The platform imports them and never
  redefines them.
- The **platform** loads `ml/checkpoints/best.pt` once, runs batch
  inspections as background jobs, and stores parks, panels, detections and
  jobs in the database. `GET /health` reports the model actually on disk
  (architecture, size, sha256 prefix), the DB state and migration status.
- The **dashboard** is a pure client of the REST API. It talks to the backend
  at `NEXT_PUBLIC_AXALON_API_URL` (default `http://localhost:8000`).

## Model

`ml/checkpoints/best.pt` is a YOLO11x checkpoint (109 MB, tracked with
Git LFS) trained with Ultralytics 8.4.84 on a merged corpus of three thermal
PV datasets. It takes 640x640 thermal IR input (do not run it on RGB)
with a default confidence threshold of 0.25.

On the held-out combined test split (2,834 images) it scores **mAP@0.5 0.792**
and **mAP@0.5:0.95 0.669**. The full bake-off against YOLOv8s, RT-DETR-x and
Co-DETR, with per-class AP and caveats, is in
[docs/MODEL_COMPARISON_YOLOV8_VS_YOLO11X.md](docs/MODEL_COMPARISON_YOLOV8_VS_YOLO11X.md).

| ID | Class | Severity | | ID | Class | Severity |
|---|---|---|---|---|---|---|
| 0 | cell | MEDIUM | | 6 | vegetation-shading | LOW |
| 1 | cell-multi | MEDIUM | | 7 | soiling | LOW |
| 2 | module | MEDIUM | | 8 | short-circuit | HIGH |
| 3 | string | CRITICAL | | 9 | hot-spot-low | HIGH |
| 4 | bypass-diode | CRITICAL | | 10 | hot-spot-high | CRITICAL |
| 5 | offline-module | HIGH | | | | |

## Quick start

Requirements: Python 3.10+ (CI uses 3.13), Node.js 20+, Git LFS, and the
WeasyPrint system libraries for PDF reports (see
[docs/INSTALLATION.md](docs/INSTALLATION.md)).

```bash
git lfs install
git clone https://github.com/Parakh20/AxalonSystems.git
cd AxalonSystems
cp .env.example .env                    # optional; every setting has a default
```

> `platform/` has the same name as Python's stdlib `platform` module. The
> package is installed as `axalon`, and Python commands run with
> `PYTHONSAFEPATH=1` so the repo root is not put on `sys.path`. `run.sh`
> handles this for you.

### Everything at once

```bash
./run.sh setup     # pip install ML + platform deps and `pip install -e .`
./run.sh doctor    # check Python deps and model weights
./run.sh all       # API on :8000 + dashboard on :3000
./run.sh status    # what is running
./run.sh stop      # stop background services
```

- Dashboard: http://localhost:3000/platform
- API: http://localhost:8000 (interactive docs at http://localhost:8000/docs)

Or with Docker:

```bash
docker compose up --build              # api :8000 + nextjs :3000
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up --build   # with NVIDIA GPU
```

### Layer 1: ML model only

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r ml/requirements.txt -e .

# Inference uses the bundled weights in ml/checkpoints/best.pt.
# Training and evaluation need the raw datasets under ml/Datasets/ (not in git):
PYTHONSAFEPATH=1 python ml/scripts/prepare_dataset.py --help
PYTHONSAFEPATH=1 python ml/scripts/train_ultralytics.py --help
PYTHONSAFEPATH=1 python -m ml.eval.evaluate --help
```

`ml/notebooks/solar_thermal_detection.ipynb` is the original training and
inference notebook. The stock COCO-pretrained base weights it starts from
(`yolov8s.pt`) are downloaded by Ultralytics on first use.

### Layer 2: Platform API only

```bash
pip install -r requirements_platform.txt -r ml/requirements.txt -e .
./run.sh api                        # or: cd /tmp && PYTHONSAFEPATH=1 python -m uvicorn axalon.api.app:app --port 8000
curl http://localhost:8000/health
```

The CLI drives the same pipeline without the web UI:

```bash
python scripts/make_sample_mission.py          # synthetic thermal+RGB pairs in tests/fixtures/sample_mission/
python main.py inspect --thermal t.jpg --rgb r.jpg --park-id PARK_01
python main.py batch --folder tests/fixtures/sample_mission --park-id PARK_01 --altitude 45 --device cpu
```

Reports land in `output/{batch_id}/` (override with `AXALON_OUTPUT_DIR`).
Schema migrations run automatically on API startup (Alembic, `alembic/`).

### Layer 3: Operator dashboard only

```bash
cd website/nextjs
cp .env.example .env.local      # optional: map tokens, API URL
npm ci
npm run dev                     # http://localhost:3000/platform
```

Operator flow: enter a park ID and a mission folder, review the preflight
summary, run the batch inspection, inspect the park map, and download the
reports. See [docs/HOW_TO_USE.md](docs/HOW_TO_USE.md) and
[docs/OPERATOR_RUNBOOK.md](docs/OPERATOR_RUNBOOK.md).

## Configuration

All settings are environment variables with defaults. Copy the templates and
fill in only what you need:

- [`.env.example`](.env.example): backend (`AXALON_DB_URL`,
  `AXALON_API_KEY`, `AXALON_USE_ENGINE`, CORS, output dir/TTL, alert
  webhook/SMTP, NodeODM orthomosaics, Sentry).
- [`website/nextjs/.env.example`](website/nextjs/.env.example): dashboard
  (`NEXT_PUBLIC_AXALON_API_URL`, optional Mapbox / Google Maps keys).
- [`deploy/env.relay.example`](deploy/env.relay.example): drone relay tokens.

Never commit real `.env` files; they are gitignored.

## Project structure

```
AxalonSystems/
├── ml/                     ML layer
│   ├── checkpoints/best.pt   trained YOLO11x weights (Git LFS)
│   ├── src/                  canonical classes, dataset + augmentation utils
│   ├── scripts/              dataset prep, training, YOLO→COCO, TensorRT export
│   ├── eval/                 evaluation, model comparison, saved metrics
│   ├── configs/              training configs
│   └── notebooks/            training / inference notebook
├── platform/               Platform API (installed as `axalon`)
│   ├── api/                  FastAPI app, routers, schemas
│   ├── core/                 detector, thermal/RGB fusion, geo, auth
│   ├── pipeline/             batch orchestration
│   ├── park/                 panel localization and numbering
│   ├── reporting/            PDF / Excel / GeoJSON writers
│   └── db/                   SQLAlchemy models and sessions
├── alembic/                DB migrations
├── website/nextjs/         Next.js marketing site + /platform operator UI
├── drone/                  drone agent + live-ops relay
├── scripts/                sample-mission generator, benchmarks, demo data
├── tests/                  backend (tests/backend), root-level and fixtures
├── deploy/                 Azure, GCP, Fly.io, Hugging Face deploy scripts
├── docs/                   spec, API reference, deployment, hardware guides
├── main.py                 CLI entrypoint
└── run.sh                  local dev launcher
```

## Tests

```bash
# Backend API, pipeline, DB, reporting (uses temp SQLite; no GPU needed)
PYTHONSAFEPATH=1 python -m pytest tests/backend/

# Root-level platform + ML tests
PYTHONSAFEPATH=1 python -m pytest tests/test_api.py tests/test_db.py tests/test_imports.py tests/test_orchestrator.py
for t in test_ml_dataset test_select_winner test_train_ultralytics test_yolo_to_coco; do
  PYTHONSAFEPATH=1 python tests/$t.py
done

# Drone agent + relay (pip install -r drone/requirements.txt first)
PYTHONSAFEPATH=1 python -m pytest drone/tests

# Dashboard unit tests (Vitest) and end-to-end tests (Playwright, needs the stack running)
cd website/nextjs && npm test
cd website/nextjs && npm run test:e2e
```

Tests that need external resources are skipped with a reason: the raw-dataset
checks in `tests/test_ml_dataset.py` run only when `ml/Datasets/` is present,
and the ArduPilot SITL end-to-end tests need `RUN_SITL_E2E=1`.

CI (`.github/workflows/ci.yml`) runs all of the above on every push and PR to
`main`. The e2e job builds the Docker Compose stack and runs Playwright
against it.

## Deployment

The production API runs as a Hugging Face Space with Azure PostgreSQL;
`db-migrate.yml` applies Alembic migrations on schema changes and
`keepalive.yml` pings the Space health endpoint. Guides:

- [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md): API, database, dashboard
- [docs/DEPLOY_DRONE_OPS.md](docs/DEPLOY_DRONE_OPS.md): drone relay and live ops
- [docs/HARDWARE_INTEGRATION.md](docs/HARDWARE_INTEGRATION.md): cameras, drone platform, IEC 62446-3 capture
- [docs/API_REFERENCE.md](docs/API_REFERENCE.md), [docs/AXALON_PLATFORM_SPEC.md](docs/AXALON_PLATFORM_SPEC.md)

## License

Code is MIT licensed, see [LICENSE](LICENSE). The model was trained with
[Ultralytics](https://github.com/ultralytics/ultralytics), which is AGPL-3.0;
check its terms before distributing the weights or a service built on them.
