# Platform Phase 2 — Park Map Detail Tab + Automated Test Foundation

**Status:** Approved 2026-05-22
**Scope:** Phase 2 of 4. Adds the one Streamlit page we don't yet have parity with (panel-grid view) and locks the working flow under a four-layer automated test suite.

## Goal

1. Add a 5th tab to `/platform` showing the panel-grid view with click-to-drill-down per panel.
2. Lay down automated tests across four layers (backend API contract, backend unit, frontend e2e, frontend unit) so future changes have a safety net.

## Non-goals (deferred)

- Polish: loading skeletons, transitions, animations, mobile layout (Phase 3)
- Auth, multi-user, persistent jobs across restarts (Phase 4)
- Comparing two inspections via diff endpoint (UI deferred; endpoint exists)
- CI runner setup (the script lands; GitHub Actions wiring deferred)
- Demo seed data + empty states (Phase 3)

## Scope

### In scope — Park Map tab

1. **New tab "Park Map"** added to `/platform` (5th tab, after Settings).
2. **Park dropdown** at the top of the tab — defaults to the park from the active Operations job; user can override.
3. **Inspection dropdown** — defaults to the most recent inspection for the selected park.
4. **Grid view** — renders an `rows × cols` matrix of cells, one per panel, color-coded by worst severity (`CRITICAL` red, `HIGH` orange, `MEDIUM` yellow, `LOW` blue, clean grey).
5. **Click cell → side panel** — opens a right-side detail panel containing: `panel_id`, detection list (class, confidence, severity badge), annotated thermal thumbnail (linked via existing `/image/{job_id}/{filename}` endpoint), GPS coords.
6. **Legend** at the top of the grid showing the five color → severity mappings.
7. **Empty state** when a park has no inspections: "No inspections for this park yet. Run a batch from the Operations tab."

### In scope — Backend

1. **New endpoint** `GET /park/{park_id}/grid?inspection_id={id}` returning the panel-grid summary (shape below).
2. **Grid aggregator** — pure function in `platform/park/grid.py` that takes a list of `Detection` rows + park metadata and returns the grid payload. Used by the endpoint and by pytest unit tests.
3. **Fallback** when `Park.rows`/`Park.cols` are null: derive rows×cols by regex `R(\d+)-C(\d+)` over the panel_ids present in detections. If even that fails, return `rows=0, cols=0, panels=[…flat list…]` and the UI falls back to a flat grid.

### In scope — Tests (foundation)

1. **Backend pytest** in `tests/backend/`:
   - `conftest.py` — shared fixtures: synthetic mission zip from Phase 1, temp SQLite DB, FastAPI TestClient.
   - `test_api_contract.py` — at least 1 test per endpoint, asserting status code + response shape.
   - `test_pipeline_unit.py` — orchestrator (batch end-to-end), `ParkLayoutDetector`, grid aggregator.
   - `pytest.ini` at repo root: `testpaths = tests/backend`, `addopts = -ra --strict-markers`.
2. **Frontend Vitest** in `website/nextjs/tests/unit/`:
   - `api.test.ts` — `request()` happy-path + `ApiError` thrown on 4xx/5xx with body preserved.
   - `Toast.test.tsx` — `useToast()` push + auto-dismiss after 6s (fake timers).
   - `vitest.config.ts` + npm script `"test": "vitest run"`.
3. **Frontend Playwright** in `website/nextjs/tests/e2e/`:
   - `golden_path.spec.ts` — walks the full operator runbook (Operations batch → reports → Inspect → History → Settings → Park Map). Assumes API + Next.js dev server already running at `http://localhost:8000` / `http://localhost:3000`.
   - `playwright.config.ts` + npm script `"test:e2e": "playwright test"`.
4. **Shared runner** `scripts/test_all.sh` — runs pytest, then vitest, then playwright. Exits non-zero on any failure. No CI wiring yet.

### Out of scope

- New endpoints other than `/park/{id}/grid`
- Touching the marketing site (`app/(site)/`)
- Refactoring `app/platform/page.tsx` beyond adding the new tab wiring
- Persisting grid layouts in DB (computed on demand)
- Visual polish on the grid (animations, hover effects beyond cursor)

## Components & touched files

| Area | File | Action |
|---|---|---|
| Backend | `platform/park/grid.py` | New: `build_grid(detections, park)` pure function |
| Backend | `platform/api/app.py` | Modify: add `@app.get("/park/{park_id}/grid")` handler |
| Frontend API | `website/nextjs/lib/api.ts` | Modify: add `api.parkGrid(parkId, inspectionId?)` + `ParkGrid`/`Panel` types |
| Frontend UI | `website/nextjs/components/Platform/ParkMapGrid.tsx` | New: presentational grid renderer |
| Frontend UI | `website/nextjs/components/Platform/ParkPanelDetail.tsx` | New: side-panel detail view |
| Frontend page | `website/nextjs/app/platform/page.tsx` | Modify: add 5th tab + state for park/inspection selection + selected panel |
| Tests | `tests/backend/conftest.py` | New: shared fixtures |
| Tests | `tests/backend/test_api_contract.py` | New: per-endpoint contract tests |
| Tests | `tests/backend/test_pipeline_unit.py` | New: orchestrator + grid unit tests |
| Tests | `pytest.ini` | New: pytest config |
| Tests | `website/nextjs/tests/unit/api.test.ts` | New: api client tests |
| Tests | `website/nextjs/tests/unit/Toast.test.tsx` | New: toast tests |
| Tests | `website/nextjs/vitest.config.ts` | New |
| Tests | `website/nextjs/tests/e2e/golden_path.spec.ts` | New: full operator walk |
| Tests | `website/nextjs/playwright.config.ts` | New |
| Tests | `website/nextjs/package.json` | Modify: add `test`, `test:e2e` scripts + devDeps `vitest`, `@vitejs/plugin-react`, `@testing-library/react`, `jsdom`, `@playwright/test` |
| Runner | `scripts/test_all.sh` | New |

## API contract

`GET /park/{park_id}/grid?inspection_id={id}`

Response (200):

```json
{
  "park_id": "SOLAR_PARK_DEMO",
  "inspection_id": "batch-abc123",
  "rows": 6,
  "cols": 8,
  "panels": [
    {
      "panel_id": "R1-C1",
      "row": 0,
      "col": 0,
      "worst_severity": "CRITICAL",
      "detection_count": 3,
      "detections": [
        {
          "class": "hot-spot-high",
          "confidence": 0.87,
          "severity": "CRITICAL",
          "thermal_filename": "img_001.jpg",
          "bbox": [12, 34, 56, 78]
        }
      ],
      "gps": { "lat": 19.076, "lon": 72.877 }
    }
  ]
}
```

- If `inspection_id` omitted, defaults to the most recent for `park_id`. If the park has no inspections, returns `{"park_id":…, "inspection_id":null, "rows":0, "cols":0, "panels":[]}`.
- If `park_id` doesn't exist, returns 404.
- `worst_severity` is `null` when `detection_count == 0`.
- `gps` is null when no detection on that panel carried GPS.

## Frontend tab — data flow

```
mount → useEffect:
  if active Operations job has park_id → setSelectedPark(it)
  else → setSelectedPark(parks[0]?.id)

selectedPark change → fetch /park/{id} (already in api.park) → list inspections, default to inspections[0]
selectedInspection change → fetch /park/{id}/grid?inspection_id=... → setGrid(response)

ParkMapGrid props:
  rows, cols, panels, selectedPanelId, onSelect(panel_id)

ParkPanelDetail props:
  panel (full panel object) | null
```

## Error handling

Same rule as Phase 1: failed fetch → `toast.error(err.message)`. No retry, no fallback UI beyond the existing empty/loading states.

## Test design — concrete examples

**Backend API test:**

```python
def test_get_park_grid_returns_panel_summary(client, batch_fixture):
    job = batch_fixture("SOLAR_PARK_DEMO")
    r = client.get(f"/park/SOLAR_PARK_DEMO/grid?inspection_id={job.inspection_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["park_id"] == "SOLAR_PARK_DEMO"
    assert body["rows"] >= 1 and body["cols"] >= 1
    assert any(p["worst_severity"] for p in body["panels"])
```

**Pipeline unit test:**

```python
def test_build_grid_aggregates_worst_severity():
    detections = [
        {"panel_id": "R1-C1", "severity": "MEDIUM", ...},
        {"panel_id": "R1-C1", "severity": "CRITICAL", ...},
        {"panel_id": "R2-C3", "severity": "LOW", ...},
    ]
    park = SimpleNamespace(rows=2, cols=3)
    grid = build_grid(detections, park)
    cell = next(p for p in grid["panels"] if p["panel_id"] == "R1-C1")
    assert cell["worst_severity"] == "CRITICAL"
    assert cell["detection_count"] == 2
```

**Vitest api test:**

```ts
test('ApiError carries status and body on 500', async () => {
  vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
    new Response('boom', { status: 500 })
  )
  await expect(api.health()).rejects.toThrow(/HTTP 500/)
})
```

**Playwright e2e:**

```ts
test('golden path', async ({ page }) => {
  await page.goto('http://localhost:3000/platform')
  await page.getByRole('tab', { name: /Operations/i }).click()
  await page.setInputFiles('input[type=file]', 'tests/fixtures/sample_mission.zip')
  await page.getByRole('button', { name: /Start batch/i }).click()
  await expect(page.getByText(/100%/)).toBeVisible({ timeout: 120_000 })
  // …continue through other tabs
})
```

## Acceptance criteria

- [ ] `GET /park/SOLAR_PARK_DEMO/grid` returns a grid with ≥1 panel carrying a severity after a fresh batch.
- [ ] Park Map tab renders the grid; cells colored correctly; clicking a non-empty cell shows the side detail panel with detection list + annotated thermal thumbnail + GPS.
- [ ] Park dropdown switches grids; defaults to active Operations job's park; falls back to first park if no active job.
- [ ] Inspection dropdown lists all inspections for the selected park; defaults to the most recent.
- [ ] Empty state renders when a selected park has no inspections.
- [ ] `pytest tests/backend/` passes with ≥1 test per FastAPI endpoint and ≥1 unit test for each of: orchestrator (batch flow), `ParkLayoutDetector.assign_grid_ids`, `build_grid`.
- [ ] `cd website/nextjs && npm test` (vitest) passes — `api.test.ts` and `Toast.test.tsx`.
- [ ] `cd website/nextjs && npm run test:e2e` (playwright) passes the golden path assuming services running.
- [ ] `scripts/test_all.sh` runs all three suites sequentially and exits 0 on a clean repo.
- [ ] No regression in the Phase 1 acceptance list (verified by re-running the playwright golden path).

## Risks

| Risk | Mitigation |
|---|---|
| Panel-grid mapping fuzzy on un-numbered parks | Regex fallback over `R\d+-C\d+`; if no match, return flat panel list with `rows=cols=0` and the UI renders a flat wrapped grid |
| Playwright requires services running | Documented in spec test header; `scripts/test_all.sh` starts services if not running, stops them after if it started them |
| Vitest adds heavy devDeps to the Next.js package | Pin to small versions; document install via existing `npm install` |
| Existing `Detection.panel_id` may be missing on rows from older batches | Grid aggregator skips rows where `panel_id is None` |
| Inspection dropdown population requires inspection list endpoint that doesn't exist | Use `/park/{id}` which already returns inspection summaries; if it doesn't return enough fields, extend it (within Phase 2 scope) |

## Future phases

- **Phase 3:** Loading skeletons, empty states, transitions, demo seeded data, mobile layout, design pass.
- **Phase 4:** Auth, persistent job queue (Redis or sqlite-backed), Docker compose for prod, GitHub Actions CI calling `scripts/test_all.sh`, deployment runbook.
