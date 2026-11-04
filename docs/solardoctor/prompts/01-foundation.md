# PROMPT 1 / 3 — Foundation: base repo, exact UI clone, unified backend, multi-agent setup

> Paste everything below this line into a fresh Claude Code session that has push access to
> https://github.com/madhavzanwar/solar-doctor.

---

You are the **lead engineer and coordinator** for **SolarDoctor**, an AI solar O&M platform built by team
Photosphere (PCCoE Pune). You will work with **multiple subagents in parallel** and you own the final quality of
everything they produce. Work autonomously; ask me only for secrets or decisions that cannot be undone.

## 0. What SolarDoctor is (product definition — do not dilute)

SolarDoctor closes the loop that no existing project closes (verified by our research, see
`docs/solardoctor/research/landscape-report.md`):

1. **Detect** silent yield loss: compare inverter/string telemetry with a **physics expected-power baseline**
   (pvlib clear-sky + PVWatts, irradiance from NASA POWER / site sensors) and flag sustained **> 5–10 % deficits**
   on QC'd clear-sky periods.
2. **Diagnose** the cause from a drone/phone **RGB photo** with a 6-class classifier: Clean, Dusty, Bird-drop,
   Snow-covered, Electrical-damage, Physical-damage (optional thermal module from AxalonSystems).
3. **Explain** every diagnosis visually (LIME superpixels + Grad-CAM) and cross-check it against telemetry.
4. **Act**: convert the diagnosis into recoverable kWh and **₹**, decide **Clean now / Wait / Field check /
   Replace**, and dispatch a **work order** whose fix is later verified by yield recovery.

## 1. Repositories you will use (open each README before using it)

| Repo | Licence | Use |
|---|---|---|
| **https://github.com/Parakh20/AxalonSystems** | MIT (+ AGPL note on YOLO weights) | **Starting codebase.** FastAPI platform (`platform/`, package `axalon`), SQLAlchemy + Alembic (10 migrations), routers for faults/work orders/analytics/park/map/auth/users/reports, fault workflow rules (`platform/core/fault_workflow.py`), PDF/Excel/GeoJSON reporting, session auth, drone relay, Docker + HF Space deploy, CI, 55 backend test files + 8 root test files. |
| **https://github.com/anugrahpatil-creator/SolarPulseAI** | MIT | **Clone its frontend exactly** (`frontend/`, Next 15.5 + React 19 + Tailwind 4, no UI libs, hand-made SVG charts). **Port its physics/ML backend** (`backend/ml/features/pvlib_features.py`, `ml/models/{lightgbm_model,probabilistic_model,online_residual_adapter}.py`, `ml/postprocessing/{clipping,soiling,ramp_risk}.py`, `app/services/{anomaly,soiling,clipping,forecast,weather,diagnosis,scada}_service.py`, `app/api/websockets/scada_ws.py`). |
| https://github.com/VisionExpo/solar-panel-fault-detection | Apache-2.0 | Reference for the 6-class inference + LIME/SHAP explainer API (`src/solar_fault_detector/models/explainer.py`, `apps/api/fastapi_app.py`). Code may be reused with NOTICE. |
| https://github.com/dunglt69/solar-anomaly-detection | Apache-2.0 | Reference for incident/ticket lifecycle, RBAC, WebSocket live updates, ISA-101 operator views. |
| https://github.com/rithvik123/solar-panel-defect-detection | No licence — study only | Inspection UX ideas (single/batch, priority queue, "review reasons"). |
| https://github.com/VishnuBhaiya/solarvision-inspection | No licence — study only | Work-order lifecycle + schedule pages. |
| https://github.com/mcomuniello/Apollo9 | No licence — study only | LIME with SLIC + multi-XAI tabs. |

**Licence rule (hard):** code from MIT/Apache/BSD repos may be copied with attribution recorded in
`THIRD_PARTY_NOTICES.md`. Repos with **no licence** are all-rights-reserved: read them for ideas, never copy code,
text, images or CSS. Re-implement from scratch.

## 2. Inputs already in the target repo

`https://github.com/madhavzanwar/solar-doctor` already contains one planning commit:

- `docs/solardoctor/design/DESIGN.md` — **the design system. Read it fully before any frontend work.**
- `docs/solardoctor/design/reference/*.webp` — 12 screenshots of the SolarPulseAI UI (desktop 1440 px + mobile
  390 px) rendered from its real code with mocked data. These are the visual acceptance target.
- `docs/solardoctor/research/landscape-report.{md,pdf}` — competitive + technical research.
- `docs/solardoctor/prompts/` — this prompt and the next two.

## 3. Step-by-step plan

### Phase A — Import the base with history (you, not a subagent)

```bash
git clone https://github.com/madhavzanwar/solar-doctor && cd solar-doctor
git remote add axalon https://github.com/Parakh20/AxalonSystems.git
git fetch axalon main
git merge axalon/main --allow-unrelated-histories -m "chore: import AxalonSystems (MIT) as SolarDoctor base"
```

- If the merge conflicts (it should not — our files live under `docs/solardoctor/`), keep both.
- **Model weights:** `ml/checkpoints/best.pt` is a 114 MB Git LFS object. Do **not** push it into our repo's LFS.
  Instead: `git lfs fetch axalon main` → upload the file to a Hugging Face model repo
  `madhavzanwar/solar-doctor-thermal-yolo11x` (model card must state: trained with Ultralytics, AGPL-3.0, from
  AxalonSystems, mAP@0.5 0.792 on their split), replace the pointer with a `scripts/fetch_weights.py` that downloads
  it via `huggingface_hub.hf_hub_download`, and add `ml/checkpoints/*.pt` to `.gitignore`. If `HF_TOKEN` is not
  available yet, ask me for it; meanwhile keep thermal detection behind `ENABLE_THERMAL=false`.
- Run Axalon's own test suite **before changing anything** and save the baseline result to
  `docs/solardoctor/BASELINE_TESTS.md` (pass/fail/skip counts). Every later phase must not regress it.

### Phase B — Create the subagent team

Create these project subagents in `.claude/agents/` (Markdown with YAML frontmatter: `name`, `description`,
`tools`, optional `model`). Each one must state: owned directories, forbidden directories, definition of done,
the licence rule, and "commit small, Conventional Commits, run tests before every commit".

| Agent | Owns | Mission |
|---|---|---|
| `sd-architect` | repo layout, `pyproject.toml`, `docker-compose*.yml`, `.github/workflows/`, `Makefile` | Monorepo structure, packaging, CI, env templates |
| `sd-frontend` | `frontend/` | Pixel-exact SolarPulseAI clone + new SolarDoctor screens per DESIGN.md |
| `sd-backend` | `backend/` (except `physics/`, `vision/`) | API, DB models, Alembic migrations, auth, work orders, reports |
| `sd-physics` | `backend/solardoctor/physics/`, `ml/forecast/` | pvlib / RdTools / pvanalytics engine, ported SolarPulse ML |
| `sd-ml` | `ml/rgb/`, `backend/solardoctor/vision/` | RGB classifier, XAI, OOD guard, HF Hub/Space (used in Prompt 2) |
| `sd-qa` | `tests/`, `frontend/tests/`, read-only elsewhere | **Independent verifier**: never fixes code it reviews, files findings, runs all suites, visual diff vs reference screenshots |

Also write a root `CLAUDE.md` (merge with Axalon's existing `CLAUDE.md`/`AGENTS.md` — keep their useful rules,
replace product description) containing: product definition (§0), repo map, commands, the licence rule, design
rule ("DESIGN.md is law"), and the definition of done (§6).

### Phase C — Restructure into the SolarDoctor monorepo (`sd-architect`, then `sd-backend`)

Target layout:

```
solar-doctor/
├── backend/solardoctor/          # was platform/ (package "axalon") → renamed package "solardoctor"
│   ├── api/ (routers, schemas)   # all public routes under /api/v1
│   ├── core/ db/ pipeline/ park/ reporting/      # from Axalon
│   ├── physics/                  # NEW (Phase E): ported SolarPulse physics + pvlib/rdtools/pvanalytics
│   ├── vision/                   # NEW (Prompt 2): RGB classifier inference, XAI, OOD
│   ├── fusion/ roi/              # NEW (Prompt 2)
│   └── workers/                  # background jobs
├── ml/thermal/                   # was ml/ (Axalon YOLO11x tooling)
├── ml/rgb/                       # NEW (Prompt 2): training pipeline for the 6-class model
├── ml/forecast/                  # NEW: SolarPulse LightGBM + probabilistic + online adapter training code
├── frontend/                     # NEW: SolarPulseAI clone (Phase D)
├── legacy/axalon-nextjs/         # was website/nextjs — kept read-only until its map/workflow components are ported (deleted in Prompt 3)
├── drone/                        # from Axalon, unchanged
├── alembic/ scripts/ deploy/ docs/ tests/
└── docker-compose.yml, Makefile, CLAUDE.md, README.md, THIRD_PARTY_NOTICES.md, LICENSE (MIT, list both upstream copyrights)
```

Rules:
- Rename the Python package `axalon` → `solardoctor` in **one isolated commit** using a scripted rename
  (imports, `pyproject.toml` `package-dir`, Alembic env, Dockerfiles, `run.sh`, tests, env var prefixes
  `AXALON_*` → `SOLARDOCTOR_*` with backward-compatible fallbacks). The new directory name `backend/` also removes
  Axalon's stdlib `platform` name clash; keep `PYTHONSAFEPATH=1` anyway.
- Re-run the full backend suite: results must equal the Phase A baseline. If the rename cannot reach parity within a
  reasonable effort, revert it and keep the `axalon` package name internally (record the decision in
  `docs/solardoctor/DECISIONS.md`) — parity beats cosmetics.
- Mount every router under `/api/v1` (keep old unprefixed paths as deprecated aliases only if tests need them).
- `make setup`, `make dev` (API :8000 + frontend :3000), `make test`, `make lint`, `make seed` must work.
- Python 3.11+, Node 20+. Pin versions. One `.env.example` at root + `frontend/.env.example`.

### Phase D — Clone the SolarPulseAI UI exactly (`sd-frontend`)

1. Copy `frontend/` from SolarPulseAI (MIT) into `solar-doctor/frontend/` **file by file as listed in
   DESIGN.md §12**, keeping `globals.css` and `dashboard.css` byte-identical. All SolarDoctor additions go into
   `src/app/solardoctor.css` (imported after `dashboard.css`) and new components.
2. Fonts per DESIGN.md §3.2: Bricolage Grotesque (display), Geist (text), Geist Mono (data), Instrument Serif
   (landing accent only) via `next/font/google`, exposed as the same CSS variables (`--font-display`, `--font-sans`)
   plus new `--font-mono`. Keep a `NEXT_PUBLIC_FONT_MODE=clone` path that restores Syne + Source Sans 3.
   If Google Fonts cannot be fetched at build time in your sandbox, use the `@fontsource*` npm packages instead —
   the result must be identical.
3. Images per DESIGN.md §9: download licensed Unsplash/Pexels photos into `frontend/public/images/`, convert to
   AVIF/WebP, record each in `docs/IMAGE_CREDITS.md` (title, author, licence URL). Never hotlink. If the image CDN is
   blocked in your sandbox, ask me to drop the files in, and meanwhile use the gradient placeholder described in
   DESIGN.md.
4. Rebrand: "SolarPulse AI" → "SolarDoctor" wordmark (DESIGN.md §9 logo), metadata, copy. Landing copy tells the
   4-step story (Detect → Diagnose → Explain → Act). Keep the structure: hero, numbered features 01–04, 5-step
   "How it works" timeline, field-green footer.
5. Navigation: implement the 10-item numbered sidebar from DESIGN.md §5. Pages that are built in Prompt 2
   (Inspections, Work orders, ROI, Map, Reports, Performance) get a **real** route with the page header, an empty
   state and a loading state now — no "coming soon" lorem.
6. Replace `src/lib/api.ts` with a typed client generated from the backend OpenAPI schema
   (`openapi-typescript` + a thin `fetch` wrapper with auth + refresh + error normalisation). Add `npm run gen:api`.
7. Auth: wire login/register/logout to the backend (Phase F). Protect `/dashboard/**` with Next.js middleware
   (redirect to `/login`), not only a client `useEffect`.
8. **Visual acceptance:** `sd-qa` builds a Playwright script that renders `/`, `/login`, `/register`,
   `/dashboard`, `/dashboard/plants`, `/dashboard/plants/[id]`, `/dashboard/alerts`, `/dashboard/performance`
   (old Forecasts) at 1440×900 and 390×844 with the **same mock fixtures** used for the references
   (create them in `frontend/tests/fixtures/` mirroring the SolarPulse API shapes) and compares against
   `docs/solardoctor/design/reference/*.webp` with `NEXT_PUBLIC_FONT_MODE=clone`. Layout, spacing, colours and
   component structure must match; only text content and the hero photo may differ. Save diffs to
   `docs/solardoctor/qa/visual/`.

### Phase E — Port the SolarPulseAI physics/ML backend (`sd-physics`)

- Port (copy with attribution, MIT) into `backend/solardoctor/physics/` and `ml/forecast/`: pvlib feature
  pipeline, LightGBM hybrid forecaster, probabilistic (P10/P50/P90) model, online residual adapter, clipping,
  soiling (time-since-rain), ramp-risk, anomaly thresholds/severity, diagnosis taxonomy (inverter error codes →
  root cause → technician steps), weather service, SCADA ingestion + WebSocket.
- Convert SolarPulse's **async SQLAlchemy/asyncpg** code to Axalon's **sync SQLAlchemy 2.0** session pattern (one
  ORM, one `Base`, one Alembic history). New tables via new Alembic revisions only: `plants` (lat, lon, tz, tilt,
  azimuth, dc_kw, ac_kw, module_count, module_wp, temp_coeff, tariff_inr_kwh), `strings`/`inverters`,
  `telemetry` (ts, plant_id, inverter_id/string_id, p_ac_kw, p_dc_kw, v, i, poa_wm2, ghi_wm2, t_amb, t_mod —
  indexed on (plant_id, ts); TimescaleDB hypertable when Postgres+Timescale is available, plain table otherwise),
  `forecasts`, `alerts`, `diagnoses`, `weather_cache`.
- Link the two worlds: an Axalon `Park` ↔ SolarDoctor `Plant` (1:1, migrate with a foreign key), so thermal
  inspections, panel faults and work orders attach to plants.
- Keep SolarPulse's endpoint shapes (`/api/v1/plants`, `/forecast/{id}`, `/forecast/{id}/summary`,
  `/forecast/{id}/probabilistic`, `/forecast/{id}/online-status`, `/alerts`, `/alerts/{id}/resolve`,
  `/diagnosis/*`, `/weather/{id}/current|forecast`) so the cloned frontend works unchanged, and add them to the
  OpenAPI schema with Pydantic v2 models.
- Unit-test every ported function against the SolarPulse originals with the same inputs (golden tests), and add
  physical sanity tests (e.g. clear-sky GHI at solar noon in Pune in March within 900–1100 W/m²; expected power is 0
  at night; clipping never exceeds AC rating).

### Phase F — Unified auth, roles, seed data (`sd-backend`)

- Keep **Axalon's opaque session-token auth** (`backend/solardoctor/core/auth.py`, SHA-256 hashed tokens, rate
  limiting, roles). Expose `/api/v1/auth/{register,login,logout,me,refresh}` in the shape the cloned frontend
  expects (token + refresh). Roles: `admin`, `operator`, `technician`, `viewer` (map Axalon roles; technicians see
  only assigned work orders).
- `make seed` creates: 1 admin + 1 technician user, three plants that mirror the reference screenshots
  (Bhadla Block C 50 MW Rajasthan, PCCoE Rooftop 120 kW Pune, Pavagada Unit 4 25 MW Karnataka), 30 days of
  **simulated** telemetry generated with pvlib from NASA POWER irradiance for each location (cache the downloaded
  CSV under `data/cache/`), with injected soiling ramps, one string fault and a cloudy spell; plus alerts. Mark all
  seeded data `source="SIMULATED"` and show the `MOCK`/`SIMULATED` badge in the UI.
- Also implement `scripts/import_pvdaq.py` using `pvdaq_access` (https://github.com/NatLabRockies/pvdaq_access)
  to import one real public system (start with PVDAQ system 9068, used in pvlib's gallery) as a fourth plant with
  `source="PVDAQ"`.

### Phase G — CI and quality gates (`sd-architect` + `sd-qa`)

GitHub Actions on push/PR: backend lint (ruff) + types (mypy on new modules) + pytest; frontend lint + `tsc
--noEmit` + Vitest + `next build`; Playwright smoke against `docker compose up`; Alembic upgrade/downgrade test on
SQLite **and** Postgres service container; secret scan (gitleaks); dependency audit (`pip-audit`, `npm audit
--omit=dev`). Cache everything. Badge in README.

## 4. How to run the subagents

- Phases A–C are sequential (you + `sd-architect`). Then run **in parallel**: `sd-frontend` (Phase D),
  `sd-physics` (Phase E), `sd-backend` (Phase F). Give each its own **git worktree and branch**
  (`feat/frontend-clone`, `feat/physics-port`, `feat/auth-seed`). They must not edit each other's directories;
  the API contract between them is the OpenAPI schema — `sd-backend` publishes it first, `sd-frontend` generates the
  client from it.
- When a subagent reports done, **`sd-qa` reviews it independently** (fresh context, reads the diff, runs the
  suites, checks the definition of done). You merge to `main` only when `sd-qa` signs off. Fix → re-review loops
  until clean.
- Keep a running log in `docs/solardoctor/BUILD_LOG.md` (what was done, decisions, open issues).

## 5. Guardrails

- Never invent data, metrics or citations. Simulated data is labelled. Model accuracy is only what you measured.
- Never weaken a test to make it pass. Never delete Axalon tests unless the feature is intentionally removed (log
  it).
- No secrets in git. `.env*` ignored. Use GitHub/HF secrets.
- Accessibility per DESIGN.md §11 from day one (focus rings, labels, contrast tokens `--sun-ink`).
- If the sandbox blocks a network resource (Google Fonts, Unsplash, Kaggle, HF), say so plainly, use the documented
  fallback, and list it in BUILD_LOG — do not silently skip.

## 6. Definition of done for Prompt 1

- [ ] `main` contains Axalon history + our docs; package renamed (or decision logged); weights served from HF.
- [ ] `make dev` starts API + frontend; `/` and all dashboard routes render with seeded data; login works.
- [ ] Visual diff vs references passes for the 8 cloned routes (desktop + mobile) in clone font mode.
- [ ] Upgraded fonts + licensed images in default mode; IMAGE_CREDITS.md complete.
- [ ] Ported physics endpoints return real pvlib-based numbers for the seeded plants; golden + sanity tests pass.
- [ ] Backend tests ≥ Axalon baseline; frontend lint/type/unit/build green; CI green on GitHub.
- [ ] `THIRD_PARTY_NOTICES.md` lists AxalonSystems, SolarPulseAI and every library/asset with licence.
- [ ] `README.md` rewritten for SolarDoctor (what, architecture diagram, quick start, screenshots).
- [ ] Everything committed with Conventional Commits and **pushed to `origin main`**; tag `v0.1.0-foundation`.

Finish with a short report: what was built, test counts before/after, visual-diff results, open issues for Prompt 2.
