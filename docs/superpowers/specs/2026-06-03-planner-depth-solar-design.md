# Mission Planner — Solar-Aware Planning Depth (Area A)

**Date:** 2026-06-03
**Status:** Approved (brainstorm). Closes the most visible gap vs Hammer Missions for solar inspection.
**Scope:** frontend-only (`website/nextjs`), low compute. Terrain/AGL follow is **deferred to phase 2**.

## Problem

The live Mission Planner does generic grid/perimeter/corridor surveys. To rival Hammer Missions for **solar** work it needs: flight lines aligned to the **panel rows** (not an arbitrary grid), a realistic **flight path with drone-facing direction**, an **orbit/POI** pattern for structures, and **battery-aware** multi-flight splitting.

## Goals

1. **Row-aligned grid via α (alpha) angle** — sweep lines run parallel to the panel rows at a user-set azimuth, so the drone flies *along* the rows.
2. **Actual flight path + drone-facing arrows** — render the true ordered serpentine route with arrowheads showing heading per leg.
3. **Orbit / POI pattern** — ring around a center point, camera aimed inward.
4. **Battery-aware splitting** — break the route into legs that each fit the battery budget; show count + color the legs.
5. Carry **heading / gimbal / leg** into all four export formats.

## Non-Goals (this spec)

- Terrain/AGL terrain-follow (phase 2 — needs an elevation source).
- Facade/vertical and true 3D planning.
- Obstacle/no-fly-zone awareness.

## Data model changes (`lib/missionGeometry.ts`)

```ts
export type MissionType = 'grid' | 'perimeter' | 'corridor' | 'orbit'

export type Waypoint = {
  lat: number; lon: number; alt: number
  heading?: number       // deg, 0=N, drone/camera facing (for arrows + α alignment + export)
  gimbalPitch?: number   // deg, negative = down (orbit aims by atan2(alt,radius))
  leg?: number           // 0-based battery leg index
}

export type MissionParams = {
  altitudeM: number
  frontOverlap: number
  sideOverlap: number
  speedMs: number
  headingDeg: number | 'auto'   // α: panel-row azimuth for grid (already supported by engine)
  // new:
  batteryMinutes?: number       // usable flight time per battery (default 18)
  batteryReservePct?: number    // reserve margin (default 20)
  orbitRadiusM?: number         // orbit pattern (default 30)
  orbitPhotoCount?: number      // orbit pattern (default 16)
}

export type MissionStats = {
  /* existing: gsdCm, footprintWM, footprintHM, areaHa, imageCount, distanceM, flightTimeSec */
  legCount: number       // new
  batteryCount: number   // new (= legCount)
}
```

### Functions
- `generateGrid(...)` — already rotates to `headingDeg`. **Add per-waypoint `heading`** = the sweep-line azimuth, flipped 180° on alternating serpentine legs (true travel direction). `'auto'` keeps the min-area-rectangle long axis; a numeric value = α (panel-row angle).
- `generateOrbit(center: LatLon, camera, params) -> Waypoint[]` — `orbitPhotoCount` points evenly on a circle of `orbitRadiusM` around `center` at `altitudeM`; each waypoint `heading` points to center, `gimbalPitch = -atan2(altitudeM, orbitRadiusM)` (deg).
- `splitByBattery(waypoints: Waypoint[], params, footprintH) -> { waypoints: Waypoint[]; legCount: number }` — walk cumulative flight time (`segment_dist / speedMs`), start a new `leg` when the next segment would exceed `batteryMinutes·(1 − reserve)`; tag each waypoint with `leg`. Used for coloring + export RTL breaks. Pure; no waypoints inserted into the geometry (legs are a tag), RTL insertion happens at export time.
- `computeStats(...)` — add `legCount`/`batteryCount` from `splitByBattery` (or from `flightTimeSec / budget`, rounded up).

`generateCorridor`/`generatePerimeter` also set `heading` (travel bearing) so arrows work everywhere.

## Map UI (`components/Platform/PlanMap.tsx`)

- **Actual path:** keep the ordered `waypoints` polyline (already the real route). Color **per `leg`** (cycle a small palette) so battery legs are visually distinct.
- **Drone-facing arrows:** at intervals along the path, place a rotated arrow marker (`L.divIcon` with CSS `transform: rotate(<heading>deg)`, no new dependency) pointing in the waypoint `heading`. Cap the count (e.g. every Nth waypoint) for performance.
- **Orbit drawing:** when `missionType === 'orbit'`, switch the draw tool to a **single marker** (center point); show the radius circle (`L.circle`). Reuse the coordinate-jump box.
- Stats bar gains **Batteries: N**.

## Sidebar (`components/Platform/PlanSidebar.tsx`)

- Add `'orbit'` to the mission-type buttons.
- **Panel row angle (α):** a numeric input + an "Auto" toggle bound to `headingDeg` (number ↔ `'auto'`). Show the current value in degrees.
- **Battery:** usable minutes + reserve % sliders.
- **Orbit:** radius + photo-count inputs (shown only for `orbit`).

## Export (`lib/waypointExport.ts`)

Emit per-waypoint `heading` and `gimbalPitch` (fall back to current nadir/0 when absent), and insert an **RTL between legs** (when `leg` changes):
- **Litchi CSV:** `heading(deg)` column = `wp.heading ?? 0`; `gimbalpitchangle` = `wp.gimbalPitch ?? -90`.
- **KML:** unchanged geometry; legs optional.
- **QGC `.plan` / `.waypoints`:** set waypoint yaw (param4 / heading) from `wp.heading`; on `leg` change insert `RTL` then a new takeoff at the next waypoint.

## Error handling / validation

- α in [0,180); battery minutes > 0; reserve in [0,0.9); orbit radius ≥ one footprint, photo count ≥ 3. Bad input → inline error, no crash.
- Orbit with no center point → empty path (no waypoints), like the current "draw an area first" guard.

## Testing (vitest, `tests/unit/`)

- `generateGrid` sets alternating headings (leg N vs N+1 differ by 180°) and aligns line azimuth to a given α.
- `generateOrbit`: count = `orbitPhotoCount`, ring closes, headings point at center (±tolerance), gimbal = `-atan2(alt,radius)`.
- `splitByBattery`: each leg's flight time ≤ budget; `legCount` correct for a known path.
- exporters: heading/gimbal land in the right Litchi columns / QGC params; an RTL appears between legs.

## Rollout

Frontend-only → ships via `git push origin main` (Vercel). No backend/Supabase change. Persisted missions already store `params`/`waypoints` as JSON, so the new fields round-trip without a schema change.
