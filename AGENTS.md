# AGENTS.md — Axalon Systems

Agent entry point for **Codex, Claude Code, and any AGENTS.md-aware tool**. Claude Code also reads `CLAUDE.md` (deeper detail) and auto-discovers the skills in `.claude/skills/`. Codex/others: read this file, then open the relevant skill in `.claude/skills/<feature>/SKILL.md`.

## What this is

Axalon is a solar-farm thermal-inspection product with three independent parts:

| Part | Path | Stack | Deploys to |
|------|------|-------|-----------|
| **Website** | `website/nextjs/` | Next.js 14, React Three Fiber | Vercel → `axalonsystems.com` |
| **ML model** | `ml/` | Ultralytics YOLO11m (thermal IR) | bundled into the backend image |
| **Platform** | `platform/` | FastAPI + SQLAlchemy | HF Space + Supabase Postgres |

The live platform UI is `axalonsystems.com/platform` (a route in the Next.js app) talking to the FastAPI backend on Hugging Face Spaces, with data in Supabase.

## Feature skills (read before working on a feature)

| Skill | Use when working on… |
|-------|----------------------|
| `.claude/skills/ml-detection/SKILL.md` | YOLO11m inference, classes, severity, detection dicts |
| `.claude/skills/platform-api/SKILL.md` | FastAPI endpoints, auth, request/response shapes |
| `.claude/skills/analysis-pipeline/SKILL.md` | ingest → detect → report orchestration |
| `.claude/skills/park-localization/SKILL.md` | panel numbering, GPS anchoring, OCR/auto-grid |
| `.claude/skills/reporting/SKILL.md` | PDF / Excel / GeoJSON report generation |
| `.claude/skills/database/SKILL.md` | SQLAlchemy models, Alembic, SQLite↔Postgres |
| `.claude/skills/mission-planner/SKILL.md` | drone mission planning + waypoint export |
| `.claude/skills/website-3d/SKILL.md` | scroll-driven R3F scene architecture |
| `.claude/skills/cloud-deployment/SKILL.md` | deploying website (Vercel) + backend (HF) + DB (Supabase) |

Architecture map: `docs/CODEMAP.md`. Full platform spec: `docs/AXALON_PLATFORM_SPEC.md`.

## Build / run / test

```bash
# Website (dev)
cd website/nextjs && npm run dev
# Website tests
cd website/nextjs && npm test            # vitest

# Platform API (local) — NOTE the platform/ shadow gotcha below
PYTHONSAFEPATH=1 uvicorn axalon.api.app:app --port 8000   # run from /tmp or repo root with safe path
# or: ./run.sh all   (API + Next.js platform UI together)

# Python tests
PYTHONSAFEPATH=1 python -m pytest        # pytest.ini, --import-mode=importlib

# Quick model smoke test
python -c "from ultralytics import YOLO; print(len(YOLO('ml/checkpoints/best.pt')('ml/data/images/test/', conf=0.25)))"
```

## Non-negotiable rules (see CLAUDE.md for the full list)

1. **Single source of truth for classes/severity:** import from `ml/src/utils.py` (`CANONICAL_CLASSES`, `CLASS2ID`, `SEVERITY_MAP`, …). Never redefine the 11 classes or severities anywhere else. In code the package is imported as `from ml.src.utils import ...`.
2. **`platform/` shadows the stdlib `platform` module.** The repo maps the directory `platform/` → Python package **`axalon`** (`pyproject.toml`), and anything running with the repo root on `sys.path` must use `PYTHONSAFEPATH=1` (and ideally cwd `/tmp`) or SQLAlchemy/uvicorn crash. App code imports as `from axalon.api… / axalon.core…`; ML utils as `from ml.src.utils …`.
3. **Module boundaries:** website ↔ platform never cross-import. Platform may import ML utils. Website is pure frontend.
4. **Primary model:** `ml/checkpoints/best.pt` (YOLO11m, 640×640, conf 0.25, thermal IR only — never RGB).
5. **Don't touch training code** (`ml/src/augmentation.py`, `ml/src/dataset.py`, notebooks) unless explicitly retraining.
6. **Deploy:** push to `main` → Vercel auto-deploys the website. The HF backend has its **own** file snapshot — update it with `huggingface_hub.upload_file(repo_type='space')` per changed file, not via git push. Details in the `cloud-deployment` skill.

## Conventions

- Python: PEP 8, type hints, `black`/`ruff`; tests with `pytest` (`--import-mode=importlib`).
- TS/React: typed props, no `any`; tests with `vitest`. Frontend files ≤ ~800 lines, organised by feature.
- Detection dicts and the 11-class order are fixed — see the `ml-detection` skill.
