# Solar Row Mode — v2 (correct design)

**Date:** 2026-06-03
**Status:** Approved design (replaces the v1 polyline solar mode, which was wrong).
**Reference:** Hammer Missions solar planner (user screenshots): draw area → set row angle → click each row → serpentine waypoints along the rows.

## The workflow (from the reference images)
1. **Define area of interest** — draw a polygon over the solar field, exactly like grid mode (Image 1).
2. **Params** (Image 2):
   - **Row Angle (α)** — the angle of the panel rows with the horizontal (0–180°).
   - **Drone Orientation** — the heading the drone body/camera faces along the pass (0–359°; default = travel direction).
   - **Gimbal Tilt** — camera pitch (reuse `gimbalPitchDeg`, 0 = horizon, −90 = nadir).
3. **Select solar rows** — a toggle button enters a click mode; the operator **clicks on each panel row** (one click per row). Each click drops a marker (Image 3's blue dots).
4. For each selected row: draw a line **through the clicked point at angle α, clipped to the area polygon**; place photo waypoints along it (front-overlap spacing); order rows by perpendicular position and **serpentine-connect** (Image 3's path).

## Why v1 was wrong
v1 reused the polyline draw (first 2 vertices = direction, rest = row centers) — one combined input, no area, no α param, no clipping. v2 separates **area polygon** from **clicked rows** and derives line orientation from the **α param**, clipping each line to the area.

## Geometry — `lib/missionGeometry.ts`
Replace `generateSolar` with:
```ts
generateSolar(area: LatLon[], rowCenters: LatLon[], camera: Camera, params: MissionParams): Waypoint[]
```
Algorithm (reuses existing `rotate` / `scanLineIntersections`):
1. `alpha = params.rowAngleDeg` (new) — convert to the math rotation used by the grid sweep.
2. Rotate the area polygon by `-alpha` so rows become horizontal.
3. For each `rowCenter`: rotate it by `-alpha`, take its `y`; `scanLineIntersections(rotatedArea, y)` → `[xMin, xMax]`. Endpoints `(xMin,y),(xMax,y)` = the clipped row line.
4. Sample photo points along each line at `footprintH·(1−frontOverlap)` (like grid emits, or just endpoints if trigger-by-distance).
5. Order rows by rotated `y`; serpentine (alternate endpoint order); rotate all back by `alpha` → lat/lon.
6. `heading` = Drone Orientation if set, else travel bearing; `gimbalPitch` = Gimbal Tilt.

New `MissionParams` fields: `rowAngleDeg?: number` (α), `droneHeadingDeg?: number | 'auto'`. (`gimbalPitchDeg` already exists.)

## State / UI
- **`PlanTab`**: `missionType==='solar'` uses the polygon draw for the **area** (not polyline), plus a separate `solarRows: LatLon[]` state. `waypoints = generateSolar(polygon, solarRows, camera, params)` when `polygon.length≥3 && solarRows.length≥1`.
- **`PlanMap`**: in solar mode, polygon draw stays for the area. Add a **"Select rows" toggle** (like the Measure tool pattern): when on, map clicks append to `solarRows` (reported up via `onSolarRowsChange`), drawn as blue dot markers; a Clear/Reset. Render the generated lines via the normal waypoint path.
- **`PlanSidebar`**: when solar — a "Select solar rows" toggle + count, and sliders for **Row Angle (α)**, **Drone Orientation**, **Gimbal Tilt**.

## Testing (vitest)
- `generateSolar`: lines clipped to the area (endpoints on polygon edges); correct count (rows×N); rows ordered + serpentine; α rotates the lines; gimbal/heading set.
- Empty area or no rows → `[]`.

## Migration note
Remove the v1 polyline interpretation in `PlanTab` and the `generateSolar(direction, rowCenters, params)` signature. Keep `mission_type:'solar'`.

## Why a fresh session
This is a multi-file interactive rework (two-input state, a new map click-mode, 3 params, clipped geometry). Build it with full context to avoid a half-wired state.
