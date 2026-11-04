# Platform Phase 3 — Polish, Refactor, and Feature Completion

**Status:** Approved 2026-05-22
**Scope:** Phase 3 of 4. Takes the platform from "functional" to "demo-ready and maintainable." Covers page decomposition, UX polish, demo seed data, inspection diff, mobile layout, and CI wiring. Annotation editor deferred to Phase 3b.

## Goal

A visitor opening `/platform` on a fresh checkout sees a polished, populated UI at any viewport ≥768px. The codebase is split into focused, testable components. GitHub Actions keeps the test suite green automatically.

## Non-goals (deferred)

- Annotation editor (bbox drawing, correction persistence) — Phase 3b
- Auth, multi-user, persistent jobs across restarts — Phase 4
- Playwright e2e in CI (requires live services; stays in `scripts/test_all.sh`)
- Phone viewport (<768px) — Phase 4
- Docker / deployment hardening — Phase 4

## Scope

### 1. `page.tsx` decomposition

The current 2,584-line monolith is reduced to a ~100-line shell that owns only tab-switching state and renders the active tab component. All logic, data-fetching, and styles move out.

**Target structure:**

```
website/nextjs/
├── app/platform/
│   ├── page.tsx              ← ~100 lines: tab enum + renders <XTab />
│   └── platform.css          ← NEW: all inline styles extracted from page.tsx
│
└── components/Platform/
    ├── OperationsTab.tsx     ← NEW: batch upload, progress, AnomalyMap, report downloads
    ├── InspectTab.tsx        ← NEW: single-image upload + annotated result
    ├── HistoryTab.tsx        ← NEW: park dropdown, inspection list, HistoryChart
    ├── ParkMapTab.tsx        ← NEW: park/inspection selectors, ParkMapGrid, ParkPanelDetail
    ├── SettingsTab.tsx       ← NEW: settings form
    ├── DiffTab.tsx           ← NEW: inspection comparison
    ├── Skeleton.tsx          ← NEW: reusable skeleton variants
    ├── hooks/
    │   ├── useParks.ts       ← NEW: parks list + loading state
    │   ├── useJob.ts         ← NEW: batch job polling state
    │   └── useSettings.ts    ← NEW: settings load/save
    ├── ParkMapGrid.tsx       ← existing, unchanged
    ├── ParkPanelDetail.tsx   ← existing, unchanged
    ├── AnomalyMap.tsx        ← existing, unchanged
    └── Toast.tsx             ← existing, unchanged
```

The inline `<style>` block (~800 lines) moves to `platform.css` imported in `app/platform/layout.tsx`. No runtime behaviour changes — pure structural extraction.

### 2. Loading skeletons + empty states

`Skeleton.tsx` provides three variants: `line`, `block`, `circle`. Each tab composes these into a tab-shaped shimmer shown while the primary fetch is in-flight.

Loading state: driven by a `loading` boolean in each tab's local state, set `true` before the fetch and `false` in the `finally` block. Skeleton renders when `loading && !data`. Empty state renders when `!loading && data is empty`.

| Tab | Skeleton shape | Empty state message |
|---|---|---|
| Operations | block (map) + 4 line rows (job list) | "Upload a ZIP above to start your first inspection." |
| Inspect | block (image) + 3 lines (detections) | "Upload a thermal image above to see detection results." |
| History | 2 lines + block (chart) + 4 line rows | "No inspections yet for this park." |
| Park Map | 2 lines + block (grid) | "No inspections for this park yet. Run a batch from Operations." |
| Settings | 6 line rows | N/A — shows defaults on load failure |
| Diff | 2 lines + block (grid) | "Select two inspections above to compare." |

### 3. Demo seed data

`scripts/seed_demo_data.py` — idempotent, safe to re-run:

1. Drops and recreates `SOLAR_PARK_DEMO` park with a 6×8 grid (48 panels, `R1-C1` through `R6-C8`).
2. Inserts 3 inspection records with timestamps today, today−15d, today−30d (so the History chart shows a trend).
3. Each inspection gets synthetic `Detection` rows: ~10% CRITICAL, 15% HIGH, 50% MEDIUM, 25% LOW, spread across ~20 panels per inspection. No YOLO run required — inserted directly via SQLAlchemy.
4. Writes GPS coords on a synthetic grid around a fixed lat/lon so AnomalyMap has spatially distributed markers.
5. Prints a summary on completion: `Park: SOLAR_PARK_DEMO | Inspections: 3 | Detections: N`.

`docs/OPERATOR_RUNBOOK.md` gains a "Demo mode" section pointing to this script.

### 4. Inspection diff/comparison (new Diff tab)

**Backend:**

New pure function `platform/park/diff.py: build_diff(detections_a, detections_b)` compares two inspection detection sets by `panel_id + class`. Returns:
- `new`: detections in B not in A
- `resolved`: detections in A not in B
- `changed`: same panel + class, different severity

New endpoint:

```
GET /park/{park_id}/diff?inspection_a={id}&inspection_b={id}
```

Response:
```json
{
  "park_id": "SOLAR_PARK_DEMO",
  "inspection_a": "batch-001",
  "inspection_b": "batch-002",
  "summary": { "new": 4, "resolved": 2, "changed": 3 },
  "panels": [
    {
      "panel_id": "R2-C3",
      "status": "new" | "resolved" | "changed" | "unchanged",
      "severity_a": "MEDIUM" | null,
      "severity_b": "CRITICAL" | null,
      "detections_a": [...],
      "detections_b": [...]
    }
  ]
}
```

If `inspection_a` or `inspection_b` not found, returns 404. If park not found, returns 404.

**Frontend — `DiffTab.tsx`:**

- Park dropdown (defaults to first park or active Operations job's park).
- Two inspection dropdowns (A = older, B = newer), defaulting to the two most recent inspections.
- Three summary badges: `N new faults` (red), `N resolved` (green), `N changed severity` (orange).
- Panel grid reusing `rows × cols` layout: red = new, green = resolved, orange = changed, grey = unchanged.
- Click a cell → side panel with A detections left, B detections right. Empty side shows "No faults in this inspection."

**API client:** `api.parkDiff(parkId, inspectionA, inspectionB)` + `ParkDiff` / `DiffPanel` types added to `lib/api.ts`.

### 5. Mobile / responsive layout

Target: usable at **768px viewport width**. No changes below 768px (phones are Phase 4).

Breakpoint rules in `platform.css` at `@media (max-width: 768px)`:

| Element | Desktop | Mobile |
|---|---|---|
| Tab bar | single horizontal row | `overflow-x: auto` horizontal scroll |
| Operations: map + job panel | side by side | stacked vertically (map on top) |
| Park Map: grid + side panel | grid left, side panel right | side panel = bottom drawer (`position: fixed; bottom: 0`) |
| Diff: A/B columns | two columns | stacked, A above B with divider label |
| History chart | fixed 720px viewBox | `width: 100%`, `preserveAspectRatio="xMinYMid meet"` |
| General padding | 24px gutters | 12px gutters |
| Fixed-width containers | `max-width: 1280px` | `width: 100%`, no min-width |

The Park Map bottom drawer is CSS-only: `transform: translateY(100%)` collapsed, `translateY(0)` open, toggled by the existing `selectedPanel` state. No new JS needed.

Settings and Inspect tabs are already single-column — no changes needed.

### 6. GitHub Actions CI

`.github/workflows/ci.yml` — triggers on push and PR to `main`. Two independent parallel jobs:

```yaml
jobs:
  backend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.13' }
      - uses: actions/cache@v4  # pip cache
      - run: pip install -r requirements_platform.txt -r ml/requirements.txt
      - run: pytest tests/backend/ -ra --strict-markers

  frontend-unit:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20' }
      - uses: actions/cache@v4  # npm cache
      - run: cd website/nextjs && npm ci
      - run: cd website/nextjs && npm test
```

Playwright e2e is intentionally excluded — it requires live services and belongs in `scripts/test_all.sh` for local pre-push use. A comment in the workflow documents this.

`docs/OPERATOR_RUNBOOK.md` gains a "CI" section explaining what the workflow covers and how to read a failure.

## Components & touched files

| Area | File | Action |
|---|---|---|
| Page shell | `website/nextjs/app/platform/page.tsx` | Refactor: slim to ~100 lines |
| Styles | `website/nextjs/app/platform/platform.css` | New: extract inline styles + responsive breakpoints |
| | `website/nextjs/app/platform/layout.tsx` | Modify: add `import './platform.css'` (shell inline styles stay) |
| Tab components | `website/nextjs/components/Platform/OperationsTab.tsx` | New |
| | `website/nextjs/components/Platform/InspectTab.tsx` | New |
| | `website/nextjs/components/Platform/HistoryTab.tsx` | New |
| | `website/nextjs/components/Platform/ParkMapTab.tsx` | New |
| | `website/nextjs/components/Platform/SettingsTab.tsx` | New |
| | `website/nextjs/components/Platform/DiffTab.tsx` | New |
| Hooks | `website/nextjs/components/Platform/hooks/useParks.ts` | New |
| | `website/nextjs/components/Platform/hooks/useJob.ts` | New |
| | `website/nextjs/components/Platform/hooks/useSettings.ts` | New |
| Shared UI | `website/nextjs/components/Platform/Skeleton.tsx` | New |
| Backend | `platform/park/diff.py` | New: `build_diff()` pure function |
| Backend | `platform/api/app.py` | Add `GET /park/{id}/diff` endpoint |
| API client | `website/nextjs/lib/api.ts` | Add `api.parkDiff()` + `ParkDiff` / `DiffPanel` types |
| Seed data | `scripts/seed_demo_data.py` | New |
| CI | `.github/workflows/ci.yml` | New |
| Docs | `docs/OPERATOR_RUNBOOK.md` | Add "Demo mode" + "CI" sections |

## Acceptance criteria

- [ ] `page.tsx` is ≤150 lines after refactor; each tab is a named component in its own file.
- [ ] Every tab that loads async data shows a skeleton while in-flight and a meaningful empty state when the response is empty.
- [ ] `scripts/seed_demo_data.py` runs on a clean checkout; History, Park Map, and Diff tabs all show populated data without running a real batch.
- [ ] Diff tab: selecting two inspections renders a diff grid with correct cell colors; clicking a non-unchanged cell shows A vs B detections side by side.
- [ ] Platform UI is fully navigable at 768px viewport: no overflow, no clipped content, Park Map side panel becomes a bottom drawer.
- [ ] GitHub Actions CI passes on main: `pytest tests/backend/` and `npm test` (vitest) both green in separate parallel jobs.
- [ ] No regression in Phase 2 acceptance criteria (verified by `npm run test:e2e` locally).

## Risks

| Risk | Mitigation |
|---|---|
| Extracting tab components from page.tsx introduces import cycles or breaks shared state | Shared state (toast, parks list) lifted into hooks; page.tsx passes props down or hooks are called inside each tab |
| `build_diff` match logic (panel_id + class) produces false positives if panel IDs shift between inspections | Document the match key clearly; add a unit test asserting no spurious matches when panel grid changes |
| Seed data GPS grid overlaps with real parks in the DB | Use a fixed lat/lon far from real solar parks (e.g., 0°N, 0°E) with a note in the script |
| GitHub Actions pip install slow without cache | `actions/cache` keyed on `requirements_platform.txt` hash |
| Mobile bottom drawer z-index conflicts with Toast | Toast z-index set higher (9999); drawer at 1000 |

## Future phases

- **Phase 3b:** Annotation editor — canvas-based bbox drawing, class picker, correction persistence (new DB table + CRUD endpoints).
- **Phase 4:** Auth, persistent job queue (Redis or sqlite-backed), Docker compose, Playwright in CI, deployment runbook.
