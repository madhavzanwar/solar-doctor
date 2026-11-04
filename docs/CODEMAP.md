# Axalon — Code Map

A fast orientation to where things live and how data flows. Pair this with `AGENTS.md` (rules + commands) and the per-feature skills in `.claude/skills/`.

## Three independent parts

```
AxalonSystems/
├── website/nextjs/     Next.js 14 site + /platform UI   → Vercel (axalonsystems.com)
├── ml/                 YOLO11m thermal model + utils     → bundled into backend image
└── platform/           FastAPI backend (pkg name: axalon)→ HF Space + Supabase
```

`website` ↔ `platform` never cross-import. `platform` imports `ml.src.utils`. The directory `platform/` is the Python package **`axalon`** (see `pyproject.toml [tool.setuptools.package-dir]`).

## platform/ (Python package `axalon`)

| Dir | Responsibility | Skill |
|-----|----------------|-------|
| `api/app.py` | FastAPI app: all REST endpoints, auth (`require_auth`), CORS | `platform-api` |
| `core/` | `detector.py` (YOLO wrapper), `fusion.py`, `geo.py` | `ml-detection`, `analysis-pipeline` |
| `pipeline/` | ingest → detect → report orchestration | `analysis-pipeline` |
| `park/` | panel localization: OCR numbering + synthetic auto-grid | `park-localization` |
| `reporting/` | PDF (WeasyPrint), Excel (openpyxl), GeoJSON | `reporting` |
| `db/` | SQLAlchemy models, session, `migrate.py` (dialect-agnostic checks) | `database` |
| `config/settings.yaml` | platform configuration | — |

## ml/

| Path | Responsibility |
|------|----------------|
| `checkpoints/best.pt` | **primary model** — YOLO11m, 640×640, conf 0.25, thermal IR only |
| `src/utils.py` | **canonical** classes (11), severity map, detection dict, drawing utils — single source of truth |
| `src/dataset.py`, `src/augmentation.py` | training-only (do not edit unless retraining) |
| `thermal_dataset.yaml`, `configs/thermal.yaml` | class names + training config |

## website/nextjs/

| Path | Responsibility | Skill |
|------|----------------|-------|
| `app/(site)/` | scroll-driven marketing site (700vh, 6 R3F scenes) | `website-3d` |
| `app/platform/` | the platform UI route (auth gate, tabs) | `platform-api` (client), `mission-planner` |
| `components/Scene/` | R3F components (one Canvas, scroll-driven) | `website-3d` |
| `components/Platform/` | platform tabs incl. Plan (mission planner) | `mission-planner` |
| `lib/` | `api.ts` (backend client), `missionGeometry.ts`, `waypointExport.ts`, `cameras.ts` | `mission-planner` |
| `scrollStore.ts` | module singleton mutated by scroll; R3F reads it in `useFrame` | `website-3d` |

## Data flow (inspection)

```
thermal images ──▶ pipeline/ingest ──▶ core/detector (YOLO11m) ──▶ detections[]
   ──▶ park/ localization (GPS-anchored panel IDs) ──▶ db/ (Supabase Postgres)
   ──▶ reporting/ (PDF / Excel / GeoJSON) ──▶ API ──▶ /platform UI
```

## Deploy flow

```
git push main ──▶ Vercel builds website/nextjs ──▶ axalonsystems.com
HF Space (parakh20/axalon-api) ◀── huggingface_hub.upload_file (per changed backend file)
Supabase Postgres ◀── AXALON_DB_URL secret on the Space (session pooler, aws-1-ap-south-1)
```

See the `cloud-deployment` skill for the exact runbook and gotchas.
