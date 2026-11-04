# Platform — Analytics Overview Dashboard (Area D)

**Date:** 2026-06-03
**Status:** Approved (brainstorm). Frontend-only v1 reusing existing endpoints. New "Overview" tab.

## Context (avoid duplication)
Per-park analytics already exist: `HistoryTab` (trend + recurring + summary via `parkTrend`/`parkRecurring`/`park`), `ParkMapTab`/`ParkMapGrid` (severity grid), and the hand-rolled SVG `TrendChart`. D adds a **portfolio-level overview**, not another per-park view.

## Goals (v1, frontend-only)
1. **Portfolio KPIs** — total parks, total inspections, total faults by **severity** (CRITICAL/HIGH/MEDIUM/LOW).
2. **Severity breakdown** — horizontal bars (reuse the `TrendChart` color tokens).
3. **Parks ranked by CRITICAL** faults — sortable list, click → deep-links into the existing History/ParkMap tab for that park.
4. **Fleet trend** — reuse `TrendChart` (aggregate of per-park trends, or the largest park as a representative until an aggregate endpoint exists).
5. Graceful **empty state** (DB currently has 0 parks).

## Data (no new backend in v1)
Aggregate client-side from existing API:
- `api.parks()` → list of parks.
- `api.park(parkId)` → summary (`total_inspections`, latest inspection, fault counts) for each park (parallel fetch, bounded concurrency).
- `api.parkTrend(parkId)` → `TrendPoint[]` for the trend.
Compute portfolio totals by summing per-park summaries. Cache in component state; show skeletons while loading.

## Components
- `components/Platform/OverviewTab.tsx` — the dashboard (KPIs + bars + ranked list + trend). Container owns data fetching.
- Small presentational helpers: `SeverityBars` (inline SVG/divs using TrendChart colors), reuse `Chip`/`TrendChart`/`Skeleton`.
- `app/platform/page.tsx` — add `'overview'` to the `Tab` union, a rail button (lucide `LayoutDashboard`), and `{tab === 'overview' && <OverviewTab />}`. Place it first (default landing) or after Operations.

## Error handling
- Per-park fetch failures degrade gracefully (skip that park, show a subtle warning), never blank the whole dashboard.
- Empty DB → friendly empty state with a pointer to run an inspection.

## Phase 2 (noted, not built now)
- Backend `GET /analytics/overview` for one-call aggregation (faster than N per-park calls).
- True **geo fault heatmap** (needs per-fault GPS in the API).
- Demo-data seeding into Supabase so the dashboard is populated for demos.

## Testing
- Unit-test the pure aggregation helper (`aggregatePortfolio(parkSummaries) → { byseverity, totals, ranked }`).
- Empty-input and partial-failure cases.

## Rollout
Frontend-only → `git push origin main` (Vercel). No backend/Supabase change in v1.
