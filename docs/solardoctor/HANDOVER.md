# SolarDoctor: handover (end of Prompt 1, "foundation")

**State:** foundation complete and merged to `main`, tag `v0.1.0-foundation`. CI is green (all 7 jobs).
**Next work:** Prompt 2 (intelligence) then Prompt 3 (hardening and launch), in `docs/solardoctor/prompts/`.

> **Important:** the git history was rewritten on 2026-11-05 (see `DECISIONS.md` #7). Every commit hash changed.
> **Delete any old local clone and run a fresh `git clone`.** Do not try to merge or rebase old branches onto `main`.

---

## 1. What SolarDoctor is

AI solar O&M platform from team Photosphere (PCCoE Pune). It closes the loop other projects leave open:

1. **Detect** silent yield loss: telemetry vs a physics expected-power baseline (pvlib).
2. **Diagnose** the cause from a panel photo (6-class RGB classifier; optional thermal YOLO).
3. **Explain** the diagnosis (LIME + Grad-CAM) and cross-check it against telemetry.
4. **Act**: kWh and ₹ recoverable, then Clean now / Wait / Field check / Replace, then a work order verified by yield recovery.

Foundation (done) = platform, auth, physics, seeded data, frontend shell, CI. Pillars 2-4 (image model, explainability,
fusion, ROI, work-order flow, the new screens) are **Prompt 2**. Hardening, deploy and release are **Prompt 3**.

## 2. Get it running (about 10 minutes)

Needs Python 3.11+, Node 20+.

```bash
git clone https://github.com/madhavzanwar/solar-doctor && cd solar-doctor
make setup     # venv, backend + frontend deps, .env from .env.example
make seed      # 3 demo plants + 30 days of SIMULATED telemetry (add: python scripts/seed.py --shift-to-now)
make dev       # API http://localhost:8000/docs  and  UI http://localhost:3000
make test      # backend pytest + frontend lint/tsc/vitest
```

Seeded logins: `admin@solardoctor.example` and `technician@solardoctor.example`. Passwords come from
`SOLARDOCTOR_SEED_ADMIN_PASSWORD` / `SOLARDOCTOR_SEED_TECH_PASSWORD`, otherwise they are generated and **printed once** when you seed.
Auth must be on: set `SOLARDOCTOR_AUTH_MODE=users` in `.env`.

## 3. What is built and verified

| Area | State | Evidence |
|---|---|---|
| Backend (FastAPI, package `solardoctor`) | Axalon platform, renamed, all routes under `/api/v1` | 817 backend tests pass without the weights file; the 10 weight tests are deselected only when `best.pt` is absent and all pass with it (787/787 verified when weights were placed) |
| Auth and roles | admin / operator / technician / viewer, rotating single-use refresh tokens, technician limited to assigned faults | `docs/solardoctor/API_AUTH.md`, 3 independent review rounds |
| Physics | pvlib PVWatts expected power, forecast, soiling, clipping, anomaly detection, diagnosis taxonomy, weather, SCADA + WebSocket; Alembic head `0011` | golden tests against SolarPulseAI originals, sanity tests, 3 review rounds |
| Seed and PVDAQ | 3 SIMULATED plants (known S-04 string fault, soiling ramps, cloudy spell); real PVDAQ system 9068 importer (CC BY 4.0) | 2 review rounds; `docs/solardoctor/SEED_PLAN.md` |
| Frontend | SolarPulseAI UI clone rebranded to SolarDoctor, 10-item nav, typed API client, auth guard, CSP headers, labelled state for tracker plants | 68 unit tests, axe 0 violations on 15 routes, 390 px overflow check, a real browser smoke test (`npm run test:smoke`, 47 checks against a live seeded API), visual gate with preset thresholds |
| CI (GitHub Actions) | ruff, mypy (physics), pytest, Alembic up/down on SQLite and Postgres, frontend lint/tsc/vitest/build, smoke, gitleaks, audits | all green on `main` |

Independent review reports (read these, they list every finding and how it was resolved): `docs/solardoctor/qa/REVIEW_*.md`.
How it was built: one agent builds on its own branch, a separate `sd-qa` agent reviews it, only a sign-off merges.
The agent definitions are in `.claude/agents/`.

**Visual fidelity:** `npm run test:visual` gates dashboard/auth screens at <= 2 % pixel difference (measured 0.1 to 1.05 %) and desktop landing at <= 3 % with photo and text masked (1.76 %). Mobile landing is **report-only** (13.7 % masked): the new copy re-wraps every section, so the reference text sits elsewhere (DECISIONS #8). Some mobile screens have no reference image. Fixtures were reverse-engineered from the 12 screenshots, so treat the numbers as indicative.

## 4. What is NOT built yet (Prompt 2 and 3)

No image classifier yet. No LIME / Grad-CAM. No fusion engine, ROI engine or work-order flow tied to diagnoses. Inspections,
Work orders, ROI, Map, Reports and Settings pages exist as real routes with headers and empty states only. No deployment
(nothing is hosted), no Hugging Face model or Space, no demo account.

## 5. Things only a human can do (blockers)

| Item | Why it matters |
|---|---|
| **`HF_TOKEN` (write scope)** | The thermal weights `best.pt` were **recovered** from the original project's public Hugging Face Space (sha256-pinned, verified; see `docs/solardoctor/WEIGHTS.md`) and all 10 weight-dependent tests pass with the file in place. They are still fetched from that third-party Space; publish our own copy with `scripts/publish_weights_hf.py` (needs your token) to remove the dependency. CI caches the file and runs those tests when it is present. |
| **Kaggle credentials** (`KAGGLE_USERNAME`, `KAGGLE_KEY`) | Prompt 2 downloads the 6-class panel dataset. Licence on Kaggle is "Unknown": train privately, never redistribute images. |
| **Hugging Face token (write scope)** | Publish the RGB model and the demo Space. |
| **Public demo blocked on dataset licence** | The RGB model is trained on `metalmerge/solar-panel-inspection` (a mirror of the Kaggle set; licence unknown). `solar-doctor/solar-doctor-rgb-defect` is therefore a **private** Hugging Face repo and no demo Space exists. Do not make the repo or a Space public until the data licence is resolved or the model is retrained on permissively licensed images. |
| **Photos and licences** | Only the hero photo ships (Unsplash licence, **not verified** from the sandbox). Four more are wanted (Indian rooftop, dusty close-up, technician cleaning, drone over a farm): the sandbox could not read Unsplash/Pexels pages, so none were added. Pick free-licence photos, check each page, and add them to `docs/IMAGE_CREDITS.md`. |
| **Real phone photos of panels (about 30)** | Prompt 3 asks for them to test the model honestly. |
| **Vercel / Hugging Face Spaces / Postgres accounts** | Prompt 3 deployment. |
| **Branch policy** | These sessions pushed straight to `main`. Decide whether to use pull requests from now on. |

**Tag:** `v0.1.0-foundation` could not be pushed from the sandbox (tag pushes and releases are blocked). Run `git tag -a v0.1.0-foundation <latest main commit> -m "SolarDoctor foundation" && git push origin v0.1.0-foundation` from a machine with push access.

Secrets go in GitHub / Hugging Face secrets or a local `.env`. **Never commit them.** Share tokens privately.

## 6. Known issues (all non-blocking, each reviewed)

Frontend:
- The topbar date range is stored but no page uses it yet. The Settings page is a skeleton with disabled fields.
- CSP keeps `script-src 'unsafe-inline'` (Next.js needs it). A nonce-based CSP is feasible via `middleware.ts` but makes pages dynamic; recommended follow-up.
- `next build` fetches Google Fonts and needs network. The frontend has no Lighthouse score yet.
- Unused photos ship in `public/`. dev-only npm audit advisories are unreviewed. axe packages are MPL-2.0 (dev only): add a notice line.

Backend / data:
- The PVDAQ plant is a **single-axis tracker**: forecasts, probabilistic forecast and diagnosis-without-values return 422 `baseline_unsupported_for_trackers`, no deficit alerts are raised for it, and the UI shows a labelled state. A pvlib tracker model was tried on real data and was too unstable (0.95-1.18x measured), so it is not enabled. Tracker status is a free-text marker in `plants.location` (API users cannot add or strip it); a real `mount` column and a `currency` column on `diagnoses` are recommended migrations (DECISIONS E15).
- Fresh-clone path (`make setup`, `make seed`, `make dev`) was run twice from brand-new clones and fixed (`make` now loads `.env`, migrates before seeding, and `scripts/dev.sh` handles busy ports). The Next.js dev server's Google Fonts fetch failed once transiently; retry.
- Seeded telemetry ends about 2 months ago (NASA POWER lags) unless you seed with `--shift-to-now` (labelled `NASA_POWER_TIME_SHIFTED`). The diagnosis endpoint rejects telemetry older than 24 h or SIMULATED unless `allow_simulated=true`; for demos set `SOLARDOCTOR_DIAGNOSIS_MAX_TELEMETRY_AGE_H=48` or re-seed daily.
- Healthy seeded strings read about 1.0 by construction (data and baseline share one physics model). The seed tests the pipeline, not model accuracy.
- Plants have no per-project scoping (any authenticated viewer sees all plants). The Timescale hypertable branch of migration `0011` has never been run (plain Postgres and SQLite pass).
- Forecast uncertainty bands are SolarPulse's fixed heuristic, labelled SIMULATED; no trained forecast model ships. With no tariff, money fields show `currency="unset"` and zero.
- Registration is open by default (`SOLARDOCTOR_ALLOW_REGISTRATION=0` closes it), the rate limiter is keyed on socket IP, password policy is length plus two weak-password checks, access tokens stay valid until expiry (12 h) after a refresh, a duplicate signup gets no signal.
- `db-migrate.yml` and `keepalive.yml` workflows are manual-only (they were aimed at the original project's production).
- Several docs under `docs/` (deployment guides, `.claude/skills/`) still describe the original project's hosting and names.

## 7. Where things live

```
backend/solardoctor/   API, DB, auth, physics/ (new), seed/ (new), reporting, park localisation, thermal detector
ml/thermal/            thermal YOLO tooling      ml/forecast/  forecast training code (no trained artifacts)
frontend/              Next.js 15 / React 19 / Tailwind 4 UI (globals.css and dashboard.css stay byte-identical to upstream)
legacy/axalon-nextjs/  old marketing/3D site; map and work-order components to port in Prompt 2, delete in Prompt 3
scripts/               seed.py, import_pvdaq.py, fetch_weights.py, publish_weights_hf.py
docs/solardoctor/      DESIGN.md (law), research report, prompts/, qa/ (reviews, a11y, visual), DECISIONS.md, BUILD_LOG.md
```

Rules (also in `CLAUDE.md`): no code from no-licence repos; nothing invented (simulated data is always labelled);
never weaken a test to make it pass; no secrets in git; Conventional Commits; run Python as `PYTHONSAFEPATH=1`.

## 8. Licences and credit

MIT. `LICENSE` keeps the upstream copyright notices, which MIT requires; `THIRD_PARTY_NOTICES.md` lists everything
incorporated (AxalonSystems, SolarPulseAI, PVDAQ, NASA POWER, libraries, fonts). The thermal weights are AGPL-3.0 and are
kept out of the repo.

## 9. How to run the remaining prompts

1. Read `docs/solardoctor/prompts/00-README.md`, then `02-intelligence.md`. Both start with an **Operating notes** block
   (lessons learned, what already exists, how to run subagents).
2. **Split Prompt 2 across sessions** (one per workstream) rather than one mega-session; usage limits stopped the agents
   four times during Prompt 1. Suggested split: (a) physics deficit engine, (b) RGB model + Hugging Face + explainability,
   (c) fusion + ROI + work orders, (d) new screens. (b) is mostly independent; (c) needs (a) and (b); (d) needs the APIs of (c).
3. Every agent must first run `git fetch origin && git checkout -B <branch> origin/main` (worktrees can start stale),
   commit after every step, and never push; the session lead merges only after the independent `sd-qa` review signs off.
4. Run Prompt 3 only after Prompt 2 is merged and tagged.
