# Platform Phase 1 — End-to-End Operator Flow

**Status:** Approved 2026-05-22
**Scope:** Phase 1 of 4. Foundation-first sequencing of the inspection-platform roadmap (Phase 2 = Streamlit-page parity, Phase 3 = polish, Phase 4 = production-grade ops).

## Goal

An operator opens `http://localhost:3000/platform`, walks every tab, runs one real (synthetic-data) batch inspection, and downloads all four report formats — without hitting a broken state.

## Non-goals (deferred to later phases)

- New features beyond what already exists in the UI scaffold
- Visual polish, animations, empty/loading skeletons
- Authentication, multi-user, persistent jobs across restarts
- Deployment story, Docker hardening
- Automated end-to-end tests (Phase 1 is bug discovery; tests prevent regressions, which comes after stability)

## Scope

### In scope

1. **Synthetic mission fixture.** Generate ~20 thermal + RGB image pairs under `tests/fixtures/sample_mission/` with planted hotspots so the YOLO model emits real detections. Reproducible via `scripts/make_sample_mission.py`.
2. **Tab-by-tab walkthrough fixes** for all four tabs in `app/platform/page.tsx`:
   - `Operations` — upload ZIP, start batch, poll status, render map, download reports
   - `Inspect` — upload single image, see annotated result + detection list
   - `History` — list parks, view past inspections, show summary
   - `Settings` — load settings.yaml, edit, save
3. **Thin API client** at `website/nextjs/lib/api.ts` — extract repeated `fetch(${API_BASE}/…)` calls into a single client with shared error handling. Keeps `page.tsx` from growing further and gives one place to surface errors.
4. **Visible error surface.** Every failed fetch shows a toast with HTTP status + first 200 chars of response body. One toast component, no retry logic.
5. **AnomalyMap real-data fixes.** Currently may assume demo-shaped data; fix to render from `/map/{job_id}` response.
6. **Report download verification.** All four formats (JSON, Excel, GeoJSON, PDF) either download successfully or fail loudly via the toast.
7. **Operator runbook** at `docs/OPERATOR_RUNBOOK.md` — click-by-click walk-through of the golden path.

### Out of scope

- Touching scenes in `components/Scene/` (marketing 3D)
- New API endpoints
- Refactoring `page.tsx` beyond extracting the API client
- New tabs or sections in the platform UI

## Components & touched files

| Area | File | Action |
|---|---|---|
| Test data | `tests/fixtures/sample_mission/` | New: ~20 thermal + RGB pairs |
| Test data | `scripts/make_sample_mission.py` | New: regenerates the fixture deterministically |
| API client | `website/nextjs/lib/api.ts` | New: typed wrapper around `fetch`, central error handling |
| Toast | `website/nextjs/components/Platform/Toast.tsx` | New: minimal toast container + `useToast` hook |
| Platform page | `website/nextjs/app/platform/page.tsx` | Bug fixes + replace inline `fetch` with `api.*` calls |
| Map | `website/nextjs/components/Platform/AnomalyMap.tsx` | Bug fixes for real-data shape |
| Backend | `platform/api/app.py` | Only fixes triggered by the walkthrough; no new endpoints |
| Docs | `docs/OPERATOR_RUNBOOK.md` | New |

## Data flow (golden path)

```
operator → /platform UI
        → POST /batch  (ZIP of tests/fixtures/sample_mission/)
        → poll GET /status/{job_id} every 2s
        → on success: GET /map/{job_id}  → AnomalyMap renders markers
                       4× GET /report/{job_id}?format=…  → download files
```

## Synthetic mission generator

`scripts/make_sample_mission.py`:

- Generates N pairs (default 20) of synthetic thermal IR + RGB JPEGs sized 640×512.
- Thermal: grayscale gradient base + 1–3 hot circular blobs per image at random positions, intensity tuned to trigger `hot-spot-high` / `hot-spot-low` from the YOLO model.
- RGB: simple panel-grid render so OCR and panel localization have something plausible.
- Writes EXIF GPS coords on a synthetic grid around a fixed lat/lon (so the map has spatially distributed markers).
- Output: `tests/fixtures/sample_mission/{thermal,rgb}/img_NNN.jpg`.

If the planted hotspots don't survive the YOLO threshold reliably, fall back to copying ~20 real thermal frames from `ml/data/images/test/` (if present).

## API client design

`website/nextjs/lib/api.ts` — small, no dependencies beyond `fetch`:

```ts
// pseudo-shape, not committed
async function request<T>(path: string, init?: RequestInit): Promise<T>
export const api = {
  health: () => request<Health>('/health'),
  batch: (form: FormData) => request<{job_id: string}>('/batch', {method: 'POST', body: form}),
  status: (jobId: string) => request<JobStatus>(`/status/${jobId}`),
  parks: () => request<Park[]>('/parks'),
  // …one method per endpoint actually used by the page
}
```

`request` throws an `ApiError` with `status` and `body` fields. Page components catch it and call `toast.error(err.message)`. No retry, no exponential backoff.

## Error handling rule

A failed fetch is **visible**, not silent. Visibility = toast notification with status code + truncated body. That's the entire bar for Phase 1. We can add structured error states (inline retry buttons, recovery flows) in Phase 3 once we know which errors are common.

## Acceptance criteria

Phase 1 is done when all of these are true on a clean checkout:

- [ ] `./run.sh all` boots API on :8000 and platform UI on :3000 with zero error logs.
- [ ] `scripts/make_sample_mission.py` regenerates the fixture without errors.
- [ ] Operations tab: upload the fixture ZIP → progress reaches 100% → map shows ≥1 marker → all 4 report downloads succeed.
- [ ] Inspect tab: upload one image from the fixture → annotated result renders.
- [ ] History tab: park list loads, selecting a park shows the inspection just completed.
- [ ] Settings tab: settings load, an edit + save round-trips.
- [ ] Every fetch error during the walkthrough produces a visible toast.
- [ ] `docs/OPERATOR_RUNBOOK.md` exists and matches the steps above.

## Risks

| Risk | Mitigation |
|---|---|
| Synthetic thermal images don't trigger YOLO detections | Fall back to real frames from `ml/data/images/test/` |
| `page.tsx` (2,404 lines) too tangled to debug safely | API-client extraction is the only refactor; everything else is targeted in-place fixes |
| Backend endpoints assume fields that the UI doesn't send (or vice versa) | Walkthrough will surface mismatches; fix at the boundary |
| AnomalyMap rewrite scope-creeps | Bounded to data-shape fixes only. If it needs a rewrite, that's Phase 2 |

## Future phases (sketch, not committed)

- **Phase 2:** Park Map detail page (severity-colored grid + anomaly drill-down) — the one Streamlit page we don't yet have parity with; add automated tests now that the flow is stable.
- **Phase 3:** Loading skeletons, empty states, transitions, demo seeded data, design pass.
- **Phase 4:** Auth, persistent job queue (Redis or sqlite-backed), Docker compose for prod, deployment runbook.
