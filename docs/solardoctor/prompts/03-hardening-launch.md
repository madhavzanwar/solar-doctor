# PROMPT 3 / 3 — Hardening & launch: validate everything, independent review, bug bash, polish, deploy, release

> Paste everything below this line into a fresh Claude Code session with push access to
> https://github.com/madhavzanwar/solar-doctor. Prompts 1 and 2 must be merged (tag `v0.2.0-intelligence`).

---

## Operating notes (v2, learned while running Prompt 1: read before planning)

**Start state.** `git fetch origin && git log --oneline -5 origin/main`; confirm the previous tag exists and read
`docs/solardoctor/HANDOVER.md`, `BUILD_LOG.md`, `DECISIONS.md` and `qa/` before touching anything.

**Subagent hygiene (these bit us):**
- A subagent's worktree may start on a STALE commit. Every agent's first command must be
  `git fetch origin && git checkout -B <branch> origin/main`. Agents never push; the lead merges after sign-off.
- Usage limits stop agents mid-task (it happened four times). Tell every agent to **commit after each step**, keep
  tasks small, and resume stopped agents with `SendMessage` instead of spawning new ones.
- The shared venv pattern: run Python as `PYTHONSAFEPATH=1 PYTHONPATH=backend:. python -m pytest ...` from the
  worktree so the worktree's code is imported, not an editable install elsewhere.
- Several large workstreams are better as **separate sessions** (one per workstream) than one mega-session.

**Independent review loop.** `sd-qa` never fixes what it reviews. Expect 2-3 rounds per branch; real findings so far
included: refresh/marker rows authenticating as bearer tokens, technician scope leaks, an API key printed by httpx's
own logger, a fabricated diagnosis when no telemetry existed, silent use of stale/SIMULATED telemetry, a 15x kWh bug
(assumed 1-minute spacing), a 1-hour DST error in an importer, CORS missing on 401s so token refresh never ran, a
horizontal-scroll bug only visible with real data. Ask reviewers to **run the author's new tests against the old code**
(they must fail there) and to reproduce, not just read.

**Facts about the current codebase (do not rebuild what exists):**
- Python package `solardoctor` in `backend/solardoctor/`; all routes under `/api/v1` (unprefixed paths are hidden
  deprecated aliases); legacy `AXALON_*` env vars are mirrored to `SOLARDOCTOR_*`.
- Auth contract: `docs/solardoctor/API_AUTH.md` (rotating single-use refresh tokens, token families, technician
  scoped to assigned faults and allowed to progress their own work orders). Roles: admin, operator, technician, viewer.
- Physics already exists (ported from SolarPulseAI, MIT): `physics/solar.py` (pvlib clear-sky, POA, Faiman, PVWatts DC
  -> AC clipping), plants/inverters/strings/telemetry/forecasts/plant_alerts/diagnoses/weather_cache tables
  (Alembic head `0011`), forecast + probabilistic (labelled SIMULATED scenario when no trained model), anomaly
  service (WARNING 10 %, CRITICAL 25 %: Prompt 2 asks for 5 %/10 % on QC'd clear-sky samples, so extend/replace
  deliberately and log it), diagnosis taxonomy, weather service (mock weather is labelled and never fed to models),
  SCADA ingest + WebSocket. Build ON these; do not re-port.
- `make seed` (`scripts/seed.py`, flags `--reset`, `--offline`, `--shift-to-now`) creates 3 SIMULATED plants + 30 days
  of telemetry with a known S-04 string fault, soiling ramps and a cloudy spell. `scripts/import_pvdaq.py` imports
  PVDAQ system 9068 (CC BY 4.0; a single-axis tracker, so the fixed-tilt baseline is invalid for it: flag/skip it).
  Diagnosis refuses telemetry older than 24 h or SIMULATED unless `allow_simulated=true` (see SEED_PLAN.md section 9).
- Responses use `currency="unset"` when a plant has no tariff (frontend shows "Not estimated"); never default to USD.
- Frontend: `frontend/` is the SolarPulseAI clone; `globals.css` and `dashboard.css` must stay byte-identical to
  upstream; additions go in `src/app/solardoctor.css`. Tests: Vitest, axe (`npm run test:a11y`, must stay at 0
  violations), visual harness (`npm run test:visual`, ~10 min), 390 px overflow check on every route.
- Weights: Git LFS is not used. Thermal weights come from Hugging Face (`make weights`); 9 backend tests need them
  and are deselected in CI only when the weights are missing (`tests/weights_required.txt`). The backend test count
  only goes up: check `docs/solardoctor/BASELINE_TESTS.md` and the latest merge commit for the current number.
- Branch policy: confirm with the repo owner where to push (this repo's sessions were restricted to one branch at
  first); never rewrite shared history. (Prompt 1 stripped one LFS pointer from unpublished history; see DECISIONS.md #6.)
- Licence rule and honesty rule are unchanged: nothing from no-licence repos; no invented data, metrics or citations;
  simulated data is labelled everywhere.

---

You are the **release lead** for **SolarDoctor** (team Photosphere, PCCoE Pune): an AI solar O&M platform that
**detects** silent yield loss with a physics baseline, **diagnoses** the cause from panel photos with a
Hugging Face–hosted model, **explains** it (LIME + Grad-CAM + telemetry cross-check) and **acts** (₹ ROI decision →
work order → verified fix). It is built on https://github.com/Parakh20/AxalonSystems (MIT) with the UI cloned from
https://github.com/anugrahpatil-creator/SolarPulseAI (MIT).

**Read first:** `CLAUDE.md`, `docs/solardoctor/BUILD_LOG.md`, `DECISIONS.md`, `qa/FINDINGS.md`,
`docs/solardoctor/design/DESIGN.md`, `ml/rgb/reports/BAKEOFF.md`, the model card on
https://huggingface.co/madhavzanwar/solar-doctor-rgb.

Your job: make it **correct, robust, beautiful and shippable**, with evidence for every claim. Use the subagents in
`.claude/agents/`. The verifier `sd-qa` must stay independent: it never fixes what it reviews. Create two extra
reviewer subagents for this phase:

- `sd-security` — read-only security reviewer (OWASP ASVS L1 for the API, upload handling, auth/session, RBAC,
  secrets, dependency CVEs, CORS/CSRF, SSRF in weather/PVDAQ fetchers, path traversal in reports/object store).
- `sd-design-critic` — read-only design reviewer that compares every screen with DESIGN.md and the reference
  screenshots and scores them (0–5) on hierarchy, spacing, typography, colour discipline, states, mobile, a11y.

## Phase 1 — Full audit (parallel, read-only)

Spawn `sd-qa`, `sd-security`, `sd-design-critic` in parallel on a clean checkout of `main`. Each writes a report:
`docs/solardoctor/qa/AUDIT_<agent>.md` with severity (blocker/major/minor), reproduction steps, file:line, and
suggested fix. Additionally `sd-qa` produces a **traceability matrix**
(`docs/solardoctor/qa/TRACEABILITY.md`): every feature promised in README/landing → the endpoint, UI, test(s) and
evidence that prove it works. Anything without evidence is a finding.

Checklist the audit must cover:

1. **Backend:** all routes have auth + RBAC tests (viewer cannot mutate; technician sees only assigned WOs);
   pagination limits; input validation (lat/lon ranges, tz names, tariffs ≥ 0, file types/sizes); idempotent
   jobs; Alembic upgrade → downgrade → upgrade on SQLite and Postgres; no N+1 queries on list endpoints (log query
   counts); timeouts + retries + circuit-breaker on NASA POWER / Open-Meteo / HF downloads; consistent error
   envelope; timezone correctness (store UTC, display plant tz, IST has no DST); structured logs; `/health`
   reports DB, migrations, model versions + sha256, weather provider status.
2. **Physics:** rerun the synthetic loss suite and PVDAQ golden tests; property-based tests (Hypothesis): expected
   power ≥ 0, = 0 at night, ≤ AC rating after clipping; deficit never computed on non-clear or clipped samples;
   seasonal sanity for Pune/Jodhpur/Tumakuru.
3. **ML:** reproduce the held-out metrics from a clean checkout with the published HF revision; leakage re-check
   (pHash test vs train); calibration ECE; OOD AUROC; XAI faithfulness (deletion/insertion); robustness on
   corrupted inputs (blur, JPEG 30, rotation, low light) — report accuracy drop; latency p50/p95 on CPU; memory.
   Try 30 real-world phone photos of panels if I provide them (ask me) — report honestly.
4. **Fusion/ROI:** every decision-table row tested; ROI numbers hand-verified for 3 cases; currency/units correct.
5. **Frontend:** `tsc --noEmit` strict, ESLint clean, no `any` in new code, React key/hydration warnings = 0, console
   errors = 0 on every route, Lighthouse (desktop + mobile) Performance ≥ 90, Accessibility ≥ 95, Best Practices
   ≥ 95, SEO ≥ 90 on landing; axe zero serious/critical; keyboard-only walkthrough of the e2e scenario; 390 px no
   page-level horizontal scroll; all states (loading/empty/error) present; images optimised (AVIF/WebP, `sizes`).
6. **Design fidelity:** visual diff of the 8 cloned routes vs `docs/solardoctor/design/reference/*.webp` in clone
   font mode; new screens scored by `sd-design-critic` ≥ 4/5 on every axis.
7. **Security:** dependency audit (pip-audit, npm audit, Trivy on images), gitleaks history scan, upload fuzzing
   (polyglot files, huge dimensions, zip bombs, SVG with script, EXIF bombs), auth (rate limits, session expiry,
   logout invalidates, password policy), headers (CSP, HSTS, X-Content-Type-Options, frame-ancestors), CORS allow-list.
8. **Licences:** `THIRD_PARTY_NOTICES.md` complete; no code copied from the no-licence repos
   (https://github.com/rithvik123/solar-panel-defect-detection, https://github.com/VishnuBhaiya/solarvision-inspection,
   https://github.com/mcomuniello/Apollo9, https://github.com/jkumarr10/veris-hackathon,
   https://github.com/Princeg1204/solar-panel-defect-classifier) — grep for distinctive identifiers/strings; AGPL
   YOLO weights isolated behind `ENABLE_THERMAL` with notice; dataset licence caveat in model + data cards; image
   credits complete.

## Phase 2 — Fix (parallel, owners only)

Triage all findings into `docs/solardoctor/qa/FIX_PLAN.md` (blockers first). Assign each to the owning subagent
(`sd-backend`, `sd-physics`, `sd-ml`, `sd-frontend`, `sd-architect`), each in its own worktree/branch. Every fix
ships with a regression test. `sd-qa` (and `sd-security` / `sd-design-critic` for their findings) re-verify each fix
independently before merge. Loop until **zero blockers and zero majors** remain; minors either fixed or listed in
`KNOWN_ISSUES.md` with rationale.

## Phase 3 — Polish (sd-frontend + sd-design-critic)

- Landing: final SolarDoctor story with real product screenshots (generated from the seeded app via Playwright at
  2× DPR), the 4-step loop diagram (Detect → Diagnose → Explain → Act) drawn as an inline SVG in the field/sun
  palette, a short "Why it matters in India" section (cite sources from the research report; no invented
  statistics), FAQ, and a "Try the model" link to the HF Space.
- Micro-interactions per DESIGN.md §4 (rise-in, pulse dot, 150 ms transitions) with `prefers-reduced-motion`.
- Empty-state line illustrations for each screen (consistent 1.5 px field stroke).
- Copy pass: numbers first, units always, provenance badges (`SIMULATED`, `PVDAQ`, `NASA POWER`, `MODEL vX`).
- Favicon/OG image from the logo mark; `metadata` per route; sitemap/robots for the landing.
- Delete `legacy/axalon-nextjs/` once all ported components are verified (keep history).

## Phase 4 — Deploy (sd-architect)

- **Backend:** Docker image (multi-stage, non-root, CPU torch wheels, weights fetched from HF at start with
  revision pin) deployed as a **Hugging Face Space (Docker SDK)** `madhavzanwar/solar-doctor-api` — Axalon already
  runs its API this way (see `docs/DEPLOYMENT.md`: repo-root `Dockerfile`, `sdk: docker`, `app_port: 7860`). Note
  their caveat that the Space keeps its own copy of the files: automate the sync with a GitHub Action that uploads
  the backend to the Space on every tagged release (`huggingface_hub.HfApi().upload_folder`) instead of manual
  uploads. Postgres: Neon/Supabase free tier or Azure (Axalon has
  `deploy/azure`); run Alembic on deploy. Object storage: HF dataset repo (private) or S3-compatible bucket.
- **Frontend:** Vercel (or HF Space static if Vercel is unavailable) with `NEXT_PUBLIC_API_URL` set; preview
  deployments on PRs.
- **Demo mode:** a read-only `demo@solardoctor.app` account and a "Load demo data" switch so judges can explore
  without uploading anything; nightly reset job.
- Smoke test the deployed URLs with the Playwright e2e scenario (pointed at production) and record a GIF of the
  full loop to `docs/solardoctor/media/demo.gif`.
- Uptime/keep-alive workflow (Axalon has `keepalive.yml`) for the HF Space.

## Phase 5 — Documentation & release

- `README.md`: one-paragraph pitch, live links (app, API docs, HF model, HF Space), screenshots, architecture
  diagram (Mermaid), feature list with what is real vs simulated, quick start (`make setup && make dev`), tests,
  credits, licence.
- `docs/ARCHITECTURE.md`, `docs/API.md` (generated from OpenAPI), `docs/solardoctor/ROI_METHOD.md`,
  `ml/rgb/DATA_CARD.md`, model card (synced with HF), `docs/OPERATOR_GUIDE.md` (with screenshots),
  `docs/DEPLOYMENT.md`, `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md` (Keep a Changelog).
- `docs/solardoctor/PITCH.md`: 3-minute hackathon demo script following the e2e scenario, the honest
  comparison table vs existing projects (from the research report: closest repos each cover 1–2 of 4 pillars;
  commercial tools like Raptor Maps/Zeitview target utility-scale thermal inspection), the 91.46 % → leak-free
  metric story, and limitations (RGB cannot see electrical faults → thermal/IV; inverter-level data localises to
  strings, not panels).
- Final CI green on `main`; create GitHub release **`v1.0.0`** with notes, the demo GIF and links.

## Guardrails (unchanged and non-negotiable)

- Never invent metrics, data, citations or testimonials. Simulated data is labelled everywhere.
- Never weaken or delete tests to go green. Never copy from no-licence repos.
- No secrets in git; rotate anything that leaked and note it.
- If the sandbox blocks a service (Vercel, HF, Kaggle, Google Fonts), state it plainly, apply the documented
  fallback, and list the exact command I must run myself.

## Definition of done for Prompt 3 (release gate)

- [ ] Audit reports + traceability matrix committed; **0 blockers, 0 majors** open; re-verified by the independent
      reviewers.
- [ ] Test suites green: backend (unit + property + integration on SQLite & Postgres), physics golden/synthetic,
      ML reproduction, frontend unit, e2e (local + production), visual diff, axe, Lighthouse thresholds met.
- [ ] Security: no high/critical CVEs unaddressed, headers/CSP set, upload fuzzing passed, gitleaks clean.
- [ ] Licences/credits complete; AGPL isolation documented.
- [ ] Live: app URL, API docs URL, HF model, HF Space demo — all listed in README and working.
- [ ] Docs complete; PITCH.md and demo GIF ready.
- [ ] Everything committed (Conventional Commits) and **pushed to the agreed branch (`origin main` unless the owner says otherwise)**; release **`v1.0.0`** published.

Finish with a release report: links, final metrics table, audit summary (found/fixed/deferred), known issues, and
the exact steps a judge should follow to see the full Detect → Diagnose → Explain → Act loop in under 3 minutes.
