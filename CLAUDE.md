# SolarDoctor — Claude Code project context

Built by team Photosphere (PCCoE Pune). Base: AxalonSystems (MIT) + SolarPulseAI (MIT). Agent rules for
Codex/others: this file is the single entry point. Axalon's original docs are kept in `legacy/AXALON_*.md`.

## Product definition (do not dilute)
SolarDoctor closes the loop no existing project closes:
1. **Detect** silent yield loss: telemetry vs a physics expected-power baseline (pvlib clear-sky + PVWatts,
   NASA POWER / site irradiance); flag sustained >5–10 % deficits on QC'd clear-sky periods.
2. **Diagnose** the cause from a drone/phone RGB photo: Clean, Dusty, Bird-drop, Snow-covered,
   Electrical-damage, Physical-damage (optional thermal module from AxalonSystems).
3. **Explain** every diagnosis (LIME superpixels + Grad-CAM) and cross-check against telemetry.
4. **Act**: kWh and ₹ recoverable -> Clean now / Wait / Field check / Replace -> work order, verified by yield recovery.

## Repo map
```
backend/solardoctor/   FastAPI app (package `solardoctor`, was Axalon `platform/`). Routes under /api/v1
  api/ core/ db/ pipeline/ park/ reporting/   from Axalon;  physics/ (PVlib+ML)  vision/ fusion/ roi/ workers/  new
ml/thermal/            Axalon YOLO11x thermal tooling (package ml.thermal);  ml/rgb, ml/forecast  new
frontend/              SolarPulseAI-clone Next.js 15 / React 19 / Tailwind 4 (no UI libs)
legacy/axalon-nextjs/  Axalon marketing/3D site + map/workflow components, read-only until ported
drone/  alembic/  scripts/  deploy/  tests/  docs/solardoctor/{design,research,prompts,qa}
```
Env vars: `SOLARDOCTOR_*` (legacy `AXALON_*` mirrored at import). Weights are not in git: `make weights`.

## Commands
```bash
make setup      # venv + backend deps + frontend deps
make dev        # API :8000 + frontend :3000
make test       # backend pytest + frontend lint/tsc/vitest
make lint       # ruff + eslint
make seed       # demo plants + simulated telemetry (labelled SIMULATED)
```
Always run Python with `PYTHONSAFEPATH=1` (the Makefile does). Python 3.11+, Node 20+.

## Rules
- **Licence rule (hard):** MIT/Apache/BSD code may be copied with an entry in `THIRD_PARTY_NOTICES.md`. Repos with no
  licence (rithvik123/solar-panel-defect-detection, VishnuBhaiya/solarvision-inspection, mcomuniello/Apollo9) are
  study-only: never copy code, text, images or CSS.
- **Design rule:** `docs/solardoctor/design/DESIGN.md` is law. In `frontend/`, `globals.css` and `dashboard.css`
  stay byte-identical to SolarPulseAI; additions go in `src/app/solardoctor.css`.
- Never invent data, metrics or citations. Simulated data is labelled `SIMULATED`; model accuracy is only what was measured.
- Never weaken or delete a test to make it pass. Baseline: `docs/solardoctor/BASELINE_TESTS.md` (632 pass; 10 need weights).
- No secrets in git. Conventional Commits, small commits, tests before every commit.
- Thermal rules from Axalon still apply: import classes/severity only from `ml.thermal.src.utils`; 11 fixed class IDs;
  thermal model must not be run on RGB; don't touch `ml/thermal/src/{augmentation,dataset}.py` unless retraining.

## Definition of done (Prompt 1)
Axalon history + docs on the branch; package renamed; weights served from HF; `make dev` works and dashboard routes
render seeded data; visual diff vs references passes (8 routes, desktop + mobile, clone font mode); ported physics
endpoints return real pvlib numbers with golden + sanity tests; backend tests >= baseline; frontend lint/types/unit/build
green; CI green; `THIRD_PARTY_NOTICES.md` complete; README rewritten; Conventional Commits.

## Agents (`.claude/agents/`)
sd-architect (layout/CI) · sd-frontend (`frontend/`) · sd-backend (`backend/` except physics/vision) ·
sd-physics (`physics/`, `ml/forecast`) · sd-ml (`ml/rgb`, `vision/`) · sd-qa (independent verifier, never fixes what it reviews).
Skills in `.claude/skills/` describe Axalon subsystems (paths there predate the rename: `platform/` = `backend/solardoctor/`).
