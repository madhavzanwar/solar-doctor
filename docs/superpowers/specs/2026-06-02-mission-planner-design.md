# Mission Planner — Design Spec

**Date:** 2026-06-02
**Status:** Approved (reconciled 2026-06-02). Backend persistence already implemented; remaining work = frontend geometry engine + UI + multi-format export.
**Goal:** Add a full drone mission planner to the Axalon platform — a new "Plan" tab that lets operators draw a survey area on a satellite map, configure flight and camera parameters, preview the generated waypoint path, export the mission (Litchi CSV, KML, QGroundControl `.plan`), and save/reload missions.

**Architecture decision — frontend-only geometry:** all waypoint math runs in the browser (TypeScript), recomputed synchronously on every parameter change. Rationale: instant live redraw (Hammer Missions UX), and it keeps working when the backend is asleep (HF free Spaces cold-start). The backend only persists missions. This supersedes an earlier "backend Python compute" suggestion.

---

## Reference

Hammer Missions (hammermissions.com) is the UX reference. Key properties to match:
- Live path redraw as parameters change (no submit button)
- Stats bar always visible (area, images, flight time, GSD)
- Camera footprint shown on map as context

---

## Architecture

**Frontend-only geometry engine.** All lawnmower/perimeter/corridor math lives in TypeScript. The browser recomputes waypoints synchronously on every slider change — zero latency. Backend handles only persistence (save/load).

**UI:** Matches the existing platform design language — light background `#f4f5f7`, white panels, `panel`/`cmdbar`/`chip` CSS classes, `primary`/`secondary` buttons, Inter font, teal accent `#0ea5e9`.

---

## File Map

### New Files

| File | Responsibility |
|---|---|
| `website/nextjs/components/Platform/PlanTab.tsx` | Top-level tab component; wires PlanMap + PlanSidebar together; holds all shared state |
| `website/nextjs/components/Platform/PlanMap.tsx` | Leaflet map with Leaflet.draw polygon/polyline tools; renders waypoint path overlay and footprint preview |
| `website/nextjs/components/Platform/PlanSidebar.tsx` | Mission type selector, camera picker, param sliders, live stats, saved missions list, export/save actions |
| `website/nextjs/lib/missionGeometry.ts` | Pure geometry functions: `generateGrid`, `generatePerimeter`, `generateCorridor`, `computeStats`, `computeFootprint` |
| `website/nextjs/lib/waypointExport.ts` | Serialises a mission to Litchi CSV, KML, or QGC `.plan`; triggers browser download |
| `website/nextjs/lib/cameras.ts` | Camera preset library (5 cameras + Custom) |
| `alembic/versions/0004_missions.py` | DB migration: create `missions` table |

### Modified Files

| File | Change |
|---|---|
| `website/nextjs/app/platform/page.tsx` | Add `'plan'` to `Tab` type; add `Navigation2` rail button; add `<PlanTab />` to tab switch |
| `website/nextjs/app/platform/platform.css` | Add `.plan-layout`, `.plan-sidebar`, `.plan-param`, `.plan-stats-bar`, `.plan-camera-card` using existing CSS tokens |
| `platform/db/models.py` | Add `Mission` model |
| `platform/api/app.py` | Add 4 mission CRUD endpoints |
| `website/nextjs/package.json` | Add `leaflet-draw` and `@types/leaflet-draw` |

---

## Section 1 — Geometry Engine (`lib/missionGeometry.ts`)

All functions are pure (no side effects, no imports beyond standard math). Every parameter slider change calls them fresh.

### Types

```ts
export type LatLon = { lat: number; lon: number }
export type Waypoint = { lat: number; lon: number; alt: number }
export type MissionType = 'grid' | 'perimeter' | 'corridor'

export type MissionParams = {
  altitudeM: number         // 10–120 m
  frontOverlap: number      // 0.5–0.95
  sideOverlap: number       // 0.5–0.95
  speedMs: number           // 3–15 m/s
  headingDeg: number | 'auto'  // 'auto' = long axis of polygon
}

export type MissionStats = {
  gsdCm: number
  footprintWM: number
  footprintHM: number
  areaHa: number
  imageCount: number
  distanceM: number
  flightTimeSec: number
}
```

### `generateGrid(polygon: LatLon[], camera: Camera, params: MissionParams): Waypoint[]`

1. Compute polygon centroid and bounding box
2. If `headingDeg === 'auto'`, find the minimum-area bounding rectangle and use its long axis as heading — minimises number of turns
3. Rotate polygon vertices into heading-aligned local frame (flat-earth approximation valid for areas < 50 km²)
4. Line spacing = `footprintWM × (1 − sideOverlap)`
5. Sweep parallel lines across bounding box at that spacing
6. Clip each line segment to the polygon (Cohen–Sutherland or equivalent)
7. Drop empty clips; alternate direction for lawnmower order
8. Rotate waypoints back to WGS84
9. Prepend TAKEOFF at polygon vertex[0], append RTL

### `generatePerimeter(polygon: LatLon[], camera: Camera, params: MissionParams): Waypoint[]`

Trace polygon vertices at flight altitude with a half-footprint inset so the camera edge covers the boundary. Returns closed loop (last waypoint = first). Prepend TAKEOFF, append RTL.

### `generateCorridor(line: LatLon[], camera: Camera, params: MissionParams): Waypoint[]`

Input: user-drawn polyline (arbitrary number of vertices). Computes a parallel return pass offset by `footprintWM × (1 − sideOverlap)`. Useful for row-by-row re-inspection of flagged strings. Prepend TAKEOFF, append RTL.

### `computeStats(waypoints: Waypoint[], polygon: LatLon[], camera: Camera, params: MissionParams): MissionStats`

```
gsd_cm         = (altM × sensorWidthMm) / (focalLengthMm × resW) × 10
footprint_w_m  = altM × sensorWidthMm / focalLengthMm / 1000
footprint_h_m  = altM × sensorHeightMm / focalLengthMm / 1000
trigger_dist_m = footprint_h_m × (1 − frontOverlap)
area_ha        = polygon area via shoelace formula (WGS84 → m² via haversine scale)
image_count    = floor(distance_m / trigger_dist_m)
distance_m     = sum of haversine distances between consecutive waypoints
flight_time_s  = distance_m / speedMs + 30   (30 s takeoff overhead)
```

### `computeFootprint(camera: Camera, params: MissionParams): { w: number; h: number }`

Returns footprint dimensions in metres at current altitude. Used by the sidebar to show the live "Footprint @ Xm" card.

---

## Section 2 — Camera Library (`lib/cameras.ts`)

```ts
export type Camera = {
  id: string
  name: string
  sensorWidthMm: number
  sensorHeightMm: number
  focalLengthMm: number
  resolutionW: number
  resolutionH: number
  custom?: boolean
}

export const CAMERAS: Camera[] = [
  {
    id: 'itl612r-pro',
    name: 'iTL612R Pro',
    sensorWidthMm: 7.68,
    sensorHeightMm: 6.144,
    focalLengthMm: 25,
    resolutionW: 640,
    resolutionH: 512,
  },
  {
    id: 'dji-xt2',
    name: 'DJI Zenmuse XT2',
    sensorWidthMm: 8.8,
    sensorHeightMm: 7.04,
    focalLengthMm: 13,
    resolutionW: 640,
    resolutionH: 512,
  },
  {
    id: 'flir-vue-pro-r',
    name: 'FLIR Vue Pro R',
    sensorWidthMm: 10.88,
    sensorHeightMm: 8.704,
    focalLengthMm: 13,
    resolutionW: 640,
    resolutionH: 512,
  },
  {
    id: 'dji-h20t',
    name: 'DJI Zenmuse H20T',
    sensorWidthMm: 8.0,
    sensorHeightMm: 6.0,
    focalLengthMm: 58,
    resolutionW: 640,
    resolutionH: 512,
  },
  {
    id: 'custom',
    name: 'Custom…',
    sensorWidthMm: 0,
    sensorHeightMm: 0,
    focalLengthMm: 0,
    resolutionW: 640,
    resolutionH: 512,
    custom: true,
  },
]
```

Selecting `custom` renders inline number inputs for `sensorWidthMm`, `sensorHeightMm`, `focalLengthMm`, `resolutionW`, `resolutionH`. All other cameras render read-only spec cards.

---

## Section 3 — Export (`lib/waypointExport.ts`)

Three export formats, all serialised client-side (no server round-trip). A format picker next to the Export button selects which file to download.

### 3a. Litchi CSV

Litchi Mission Hub CSV. One row per waypoint. Columns (subset used):
`latitude, longitude, altitude(m), heading(deg), curvesize(m), rotationdir, gimbalmode, gimbalpitchangle, actiontype1, actionparam1, …, speed(m/s), poi_latitude, poi_longitude, poi_altitude(m), photo_timeinterval, photo_distinterval`

- `gimbalpitchangle = -90` (nadir), `actiontype1 = 1` (takePhoto), `speed = params.speedMs`.
- `photo_distinterval = trigger_dist_m` (distance-triggered capture).
- Header row required; filename `${slug}_litchi.csv`.

### 3b. KML

OGC KML for Google Earth / generic viewers. A `<LineString>` of the full path plus one `<Placemark>` per waypoint (start/end styled). Altitude mode `relativeToGround`. Filename `${slug}.kml`.

### 3c. QGroundControl `.plan`

QGC/ArduPilot `.plan` JSON (`fileType: "Plan"`, `version: 1`). `mission.items[]` = `MAV_CMD_NAV_WAYPOINT` (16) per waypoint, preceded by `MAV_CMD_NAV_TAKEOFF` (22) and `MAV_CMD_DO_SET_CAM_TRIGG_DIST` (206), with `MAV_CMD_NAV_RETURN_TO_LAUNCH` (20) last. `plannedHomePosition` = polygon vertex[0]. Filename `${slug}.plan`.

### Download helper

```ts
type ExportFormat = 'litchi' | 'kml' | 'plan'

export function downloadMission(
  waypoints: Waypoint[], params: MissionParams, name: string, format: ExportFormat,
): void {
  const slug = name.replace(/\s+/g, '_') || 'mission'
  const { text, ext, mime } = serialiseMission(waypoints, params, slug, format)
  const blob = new Blob([text], { type: mime })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `${slug}.${ext}`
  a.click()
  URL.revokeObjectURL(url)
}
```

`serialiseMission` dispatches to `toLitchiCsv` / `toKml` / `toQgcPlan`. Each is a pure function, unit-tested.

---

## Section 4 — UI Components

### `PlanTab.tsx`

Holds all shared state:
- `polygon: LatLon[] | null` — drawn polygon/line from PlanMap
- `missionType: MissionType`
- `camera: Camera`
- `params: MissionParams`
- `waypoints: Waypoint[]` — derived via `useMemo` from above
- `stats: MissionStats` — derived via `useMemo`
- `savedMissions: MissionSummary[]` — fetched from `GET /missions?park_id=X`

Layout: `display: flex; flex-direction: row` — PlanMap takes remaining width, PlanSidebar is fixed 280px. Uses existing `.panel` and `.cmdbar` classes.

### `PlanMap.tsx`

- Leaflet map, same tile source as `AnomalyMap.tsx` (Mapbox satellite if token present, ESRI fallback)
- `leaflet-draw` plugin: polygon tool for Grid/Perimeter, polyline tool for Corridor
- Drawn shape rendered as semi-transparent teal fill + dashed border
- Waypoint path rendered as a `L.Polyline` in teal — updates whenever `waypoints` prop changes
- Waypoint markers: start (blue circle), end (green circle), turns (small dots)
- Bottom stats bar overlay: area, images, distance, time, GSD — positioned absolute inside map container

### `PlanSidebar.tsx`

Sections (top to bottom), all using existing `.panel`, `.panel-head.compact`, `.form-row` classes:

1. **Mission header** — name input (`<input>`) + park ID + mission type buttons (Grid / Perimeter / Corridor) styled like existing filter buttons
2. **Camera** — `<select>` with camera names; spec card below (read-only or editable if Custom)
3. **Flight params** — four sliders with label + live value: Altitude, Front overlap, Side overlap, Speed; heading toggle (Auto / Manual degrees)
4. **Saved missions** — scrollable list of `queue-item`-styled cards; click loads mission back into map
5. **Actions** — `Export .waypoints` (primary button) + `Save Mission` (secondary button)

### `platform.css` additions

```css
.plan-layout { display: flex; height: 100%; gap: 0; overflow: hidden; }
.plan-map    { flex: 1; position: relative; min-width: 0; }
.plan-sidebar {
  width: 280px; overflow-y: auto; background: #fff;
  border-left: 1px solid #e2e8f0; display: flex; flex-direction: column;
}
.plan-param  { padding: 0 16px 12px; }
.plan-param label { font-size: 12px; color: #64748b; display: flex; justify-content: space-between; }
.plan-param input[type=range] { width: 100%; accent-color: #0ea5e9; }
.plan-stats-bar {
  position: absolute; bottom: 12px; left: 50%; transform: translateX(-50%);
  background: rgba(255,255,255,.92); border: 1px solid #e2e8f0;
  border-radius: 6px; padding: 6px 16px; display: flex; gap: 16px;
  box-shadow: 0 2px 8px rgba(15,23,42,.12); z-index: 800;
}
.plan-camera-card {
  background: #f8fafc; border-radius: 6px; padding: 10px 12px;
  font-size: 11px; color: #64748b; margin-top: 8px;
}
```

---

## Section 5 — Backend Persistence  ✅ ALREADY IMPLEMENTED

> This section is **already built** in the codebase: the `Mission` model (`platform/db/models.py:130`), the `POST/GET/DELETE /missions` endpoints (`platform/api/app.py`), and migration `0004` are live (Supabase at `alembic_version=0004`). No work remains here except wiring the frontend to it. Documented below for reference.

### `Mission` model (`platform/db/models.py`)

```python
class Mission(Base):
    __tablename__ = "missions"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    name         = Column(String, nullable=False)
    park_id      = Column(String, ForeignKey("parks.id"), nullable=True, index=True)
    mission_type = Column(String, default="grid")   # grid | perimeter | corridor
    camera_id    = Column(String, nullable=True)
    params       = Column(Text, nullable=True)       # JSON MissionParams
    polygon      = Column(Text, nullable=True)       # JSON LatLon[] — drawn shape
    waypoints    = Column(Text, nullable=True)       # JSON Waypoint[]
    area_ha      = Column(Float, nullable=True)
    image_count  = Column(Integer, nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow)
```

### API endpoints (`platform/api/app.py`)

```
POST   /missions              → 201 { id, name, created_at }
GET    /missions?park_id=X    → 200 [ { id, name, mission_type, area_ha, image_count, created_at } ]
GET    /missions/{id}         → 200 full Mission (all fields)
DELETE /missions/{id}         → 204
```

No update endpoint — if user changes a saved mission they save as new (simpler, avoids version confusion).

### Migration (`alembic/versions/0004_missions.py`)

`down_revision = '0003'`. Creates `missions` table and index on `park_id`.

---

## Section 6 — Platform Tab Integration

`app/platform/page.tsx`:
- Add `'plan'` to `Tab` type
- Import `Navigation2` from lucide-react
- Add rail button between `diff` and settings:
  ```tsx
  <button className={`rail-link ${tab === 'plan' ? 'active' : ''}`}
          onClick={() => setTab('plan')} title="Plan">
    <Navigation2 size={16} />
    <span>Plan</span>
  </button>
  ```
- Add `{tab === 'plan' && <PlanTab />}` to content area

---

## Data Flow Summary

```
User draws polygon on PlanMap
  → polygon state in PlanTab
  → useMemo: generateGrid(polygon, camera, params) → waypoints
  → useMemo: computeStats(waypoints, ...) → stats
  → PlanMap re-renders waypoint polyline
  → PlanSidebar stats bar updates
  → User clicks Export → downloadWaypoints() → browser download
  → User clicks Save → POST /missions → saved to DB
  → Saved missions list refreshes → mission card appears in sidebar
  → User clicks mission card → polygon + params loaded back into state
```

---

## Testing

- Unit tests for `missionGeometry.ts`: grid covers polygon, no waypoints outside polygon bounds, perimeter closes loop, stats formulas match hand calculations
- Unit test for `waypointExport.ts`: output parses as valid QGC WPL 110 (correct header, RTL as last row, camera trigger present)
- Backend tests for all 4 mission endpoints (create, list, get, delete)
- E2E (Playwright): draw polygon → verify stats bar shows non-zero values → export button triggers download

---

## Out of Scope

- Wind/obstacle avoidance simulation
- Multi-battery mission splitting (shown in stats, not enforced)
- Live telemetry / MAVLink connection
- Uploading missions directly to a drone (export files only)
- Terrain-following / AGL elevation modelling (constant altitude only)
- Mapbox base layer (Leaflet now; provider abstracted for a later swap)
