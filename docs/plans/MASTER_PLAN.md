# Axalon Systems — Master Improvement Plan
**Date:** 2026-06-13  
**Purpose:** Structured work plan for Qwen2.5-assisted coding sessions.  
**Priority order:** P0 (blocking) → P1 (high) → P2 (medium) → P3 (nice-to-have)

---

## Current State Summary

| Area | Status | Problem |
|------|--------|---------|
| `platform/api/app.py` | Built, working | **2,976 lines** — must be split into routers |
| Request validation | Missing | All endpoints accept raw `dict`, no Pydantic schemas |
| `park/locator.py` | Missing | Referenced in spec, not implemented |
| Test coverage | Partial | ~23 backend tests; large areas of app.py untested |
| ML evaluation | Basic | No structured evaluation tooling or regression testing |
| Next.js frontend | Functional | Minor UX gaps in several tabs |

---

## Plan Index

| Plan | File | Priority | Effort |
|------|------|----------|--------|
| 1. Split app.py into routers | [plan-01-api-routers.md](plan-01-api-routers.md) | P0 | Large |
| 2. Pydantic request/response schemas | [plan-02-pydantic-schemas.md](plan-02-pydantic-schemas.md) | P0 | Medium |
| 3. Add `park/locator.py` | [plan-03-park-locator.md](plan-03-park-locator.md) | P1 | Medium |
| 4. Expand test coverage to 80% | [plan-04-test-coverage.md](plan-04-test-coverage.md) | P1 | Large |
| 5. ML evaluation tooling | [plan-05-ml-eval.md](plan-05-ml-eval.md) | P2 | Medium |
| 6. Frontend UX improvements | [plan-06-frontend-ux.md](plan-06-frontend-ux.md) | P2 | Medium |
| 7. Performance & async hardening | [plan-07-perf-async.md](plan-07-perf-async.md) | P2 | Small |

---

## Execution Order for Qwen2.5

1. Start with **Plan 01** (router split) — all other backend plans depend on a sane file structure.
2. Do **Plan 02** (Pydantic) in the same pass — routers + schemas go together.
3. **Plan 03** (park/locator) is self-contained — can run after Plan 01.
4. **Plan 04** (tests) after schemas exist — tests validate schemas.
5. Plans 05–07 are independent of each other.

---

## Repository Layout (reference)

```
AxalonSystems/
├── platform/
│   ├── api/
│   │   ├── app.py          ← MONOLITH (2,976 lines) — split first
│   │   └── routers/        ← CREATE: one file per domain
│   ├── core/               ← detector, fusion, geo, map_renderer, object_store
│   ├── db/                 ← models.py, session.py, migrate.py
│   ├── park/               ← grid, layout, numbering, diff, trend, recurring
│   ├── pipeline/           ← ingest.py, orchestrator.py, tracking.py
│   └── reporting/          ← report.py, geojson_writer.py
├── website/nextjs/
│   ├── app/platform/       ← Platform UI route
│   ├── app/track/          ← Track workspace route
│   └── components/Platform/← ~30 tab components
├── ml/
│   ├── checkpoints/best.pt ← YOLO11m primary model
│   └── src/utils.py        ← CANONICAL source of truth
└── tests/backend/          ← ~23 test files
```
