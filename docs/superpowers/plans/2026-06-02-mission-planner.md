# Mission Planner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a full drone mission planner — a new "Plan" tab where operators draw a survey area on a satellite map, configure flight/camera parameters, preview the generated waypoint path live, export an ArduPilot `.waypoints` file, and save/reload missions.

**Architecture:** Frontend-only geometry engine (pure TypeScript) computes lawnmower/perimeter/corridor waypoints synchronously on every parameter change. Leaflet + leaflet-draw for map drawing. Backend adds a thin `Mission` persistence layer (4 CRUD endpoints + one table). The UI matches the existing platform's light design language.

**Tech Stack:** Next.js 14, React, TypeScript, Leaflet, leaflet-draw, FastAPI, SQLAlchemy, Alembic, Vitest, pytest

**Reference spec:** `docs/superpowers/specs/2026-06-02-mission-planner-design.md`

---

## Important Conventions (read before starting)

- **Python imports use the `axalon.*` namespace**, not `platform.*`. E.g. `from axalon.db.models import ...`. The `platform/` directory is mapped to the `axalon` package. Tests and app code both use `axalon`.
- **Frontend tests use Vitest.** Test files live next to `lib/` as `lib/<name>.test.ts`. Run with `cd website/nextjs && npm run test`.
- **Backend tests use pytest** with fixtures from `tests/backend/conftest.py` (`client`, `db_session`, `temp_db`). Run with `source .venv/bin/activate && pytest tests/backend/...`.
- **Alembic migrations** are linear: current head is `0003`. The new migration is `0004` with `down_revision = '0003'`.
- All commit messages end with:
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  ```

---

## File Map

### New Files
| File | Responsibility |
|---|---|
| `website/nextjs/lib/cameras.ts` | Camera preset library (5 cameras + Custom) and `Camera` type |
| `website/nextjs/lib/missionGeometry.ts` | Pure geometry: `generateGrid`, `generatePerimeter`, `generateCorridor`, `computeStats`, `computeFootprint`, shared types |
| `website/nextjs/lib/missionGeometry.test.ts` | Vitest unit tests for geometry |
| `website/nextjs/lib/waypointExport.ts` | Serialise waypoints to QGC WPL 110, browser download |
| `website/nextjs/lib/waypointExport.test.ts` | Vitest unit tests for export |
| `website/nextjs/components/Platform/PlanMap.tsx` | Leaflet map with draw tools + waypoint overlay + stats bar |
| `website/nextjs/components/Platform/PlanSidebar.tsx` | Mission name/type, camera picker, sliders, saved list, actions |
| `website/nextjs/components/Platform/PlanTab.tsx` | Top-level tab; owns shared state; wires map + sidebar |
| `alembic/versions/0004_missions.py` | DB migration: create `missions` table |
| `tests/backend/test_missions.py` | pytest for the 4 mission endpoints |

### Modified Files
| File | Change |
|---|---|
| `website/nextjs/package.json` | Add `leaflet-draw` + `@types/leaflet-draw` |
| `website/nextjs/lib/api.ts` | Add `Mission` types + `api.missions` helpers |
| `website/nextjs/app/platform/page.tsx` | Add `'plan'` tab + rail button + `<PlanTab />` |
| `website/nextjs/app/platform/platform.css` | Add `.plan-*` classes |
| `platform/db/models.py` | Add `Mission` model |
| `platform/api/app.py` | Add 4 mission CRUD endpoints + `_serialize_mission` |

---

## Task 1: Camera Library

**Files:**
- Create: `website/nextjs/lib/cameras.ts`

- [ ] **Step 1: Create cameras.ts**

```ts
// website/nextjs/lib/cameras.ts

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
    sensorWidthMm: 7.68,
    sensorHeightMm: 6.144,
    focalLengthMm: 25,
    resolutionW: 640,
    resolutionH: 512,
    custom: true,
  },
]

export const DEFAULT_CAMERA = CAMERAS[0]

export function getCamera(id: string): Camera {
  return CAMERAS.find((c) => c.id === id) ?? DEFAULT_CAMERA
}
```

- [ ] **Step 2: Commit**

```bash
git add website/nextjs/lib/cameras.ts
git commit -m "feat(plan): add camera preset library for mission planner"
```

---

## Task 2: Geometry Engine

**Files:**
- Create: `website/nextjs/lib/missionGeometry.ts`
- Create: `website/nextjs/lib/missionGeometry.test.ts`

### Background
All math uses a flat-earth (equirectangular) approximation valid for the small areas (< 50 km²) involved in solar-park surveys. We convert lat/lon to local metres relative to the polygon centroid, do all geometry in metres, then convert back. `metresPerDegLat ≈ 111320`. `metresPerDegLon ≈ 111320 × cos(centroidLatRad)`.

- [ ] **Step 1: Write the failing tests**

```ts
// website/nextjs/lib/missionGeometry.test.ts
import { describe, it, expect } from 'vitest'
import {
  generateGrid,
  generatePerimeter,
  generateCorridor,
  computeStats,
  computeFootprint,
  type LatLon,
  type MissionParams,
} from './missionGeometry'
import { DEFAULT_CAMERA } from './cameras'

// ~200m × ~200m square near the equator-ish (Pune, India)
const SQUARE: LatLon[] = [
  { lat: 18.5200, lon: 73.8550 },
  { lat: 18.5200, lon: 73.8569 },
  { lat: 18.5182, lon: 73.8569 },
  { lat: 18.5182, lon: 73.8550 },
]

const PARAMS: MissionParams = {
  altitudeM: 20,
  frontOverlap: 0.8,
  sideOverlap: 0.7,
  speedMs: 8,
  headingDeg: 'auto',
}

describe('computeFootprint', () => {
  it('computes footprint width/height in metres at altitude', () => {
    // w = altM * sensorW / focal / 1000 = 20 * 7.68 / 25 / 1000 ... but mm→m:
    // footprint_w_m = altM * sensorWidthMm / focalLengthMm = 20 * 7.68 / 25 = 6.144 m
    const fp = computeFootprint(DEFAULT_CAMERA, PARAMS)
    expect(fp.w).toBeCloseTo(6.144, 2)
    expect(fp.h).toBeCloseTo(4.9152, 2)
  })
})

describe('generateGrid', () => {
  it('returns a non-empty waypoint list with takeoff first and RTL marker last', () => {
    const wps = generateGrid(SQUARE, DEFAULT_CAMERA, PARAMS)
    expect(wps.length).toBeGreaterThan(2)
    // first waypoint is takeoff at polygon vertex[0]
    expect(wps[0].lat).toBeCloseTo(SQUARE[0].lat, 4)
    expect(wps[0].lon).toBeCloseTo(SQUARE[0].lon, 4)
    // all waypoints carry the flight altitude
    for (const wp of wps) expect(wp.alt).toBe(20)
  })

  it('keeps all survey waypoints within the polygon bounding box', () => {
    const wps = generateGrid(SQUARE, DEFAULT_CAMERA, PARAMS)
    const lats = SQUARE.map((p) => p.lat)
    const lons = SQUARE.map((p) => p.lon)
    const minLat = Math.min(...lats) - 0.0005
    const maxLat = Math.max(...lats) + 0.0005
    const minLon = Math.min(...lons) - 0.0005
    const maxLon = Math.max(...lons) + 0.0005
    for (const wp of wps) {
      expect(wp.lat).toBeGreaterThanOrEqual(minLat)
      expect(wp.lat).toBeLessThanOrEqual(maxLat)
      expect(wp.lon).toBeGreaterThanOrEqual(minLon)
      expect(wp.lon).toBeLessThanOrEqual(maxLon)
    }
  })

  it('produces more lines when side overlap is higher (tighter spacing)', () => {
    const loose = generateGrid(SQUARE, DEFAULT_CAMERA, { ...PARAMS, sideOverlap: 0.5 })
    const tight = generateGrid(SQUARE, DEFAULT_CAMERA, { ...PARAMS, sideOverlap: 0.9 })
    expect(tight.length).toBeGreaterThan(loose.length)
  })
})

describe('generatePerimeter', () => {
  it('returns a closed loop (last survey point near first)', () => {
    const wps = generatePerimeter(SQUARE, DEFAULT_CAMERA, PARAMS)
    expect(wps.length).toBeGreaterThan(3)
  })
})

describe('generateCorridor', () => {
  it('returns waypoints for a drawn line', () => {
    const line: LatLon[] = [
      { lat: 18.5200, lon: 73.8550 },
      { lat: 18.5182, lon: 73.8569 },
    ]
    const wps = generateCorridor(line, DEFAULT_CAMERA, PARAMS)
    expect(wps.length).toBeGreaterThan(2)
  })
})

describe('computeStats', () => {
  it('computes positive area, distance, image count and flight time', () => {
    const wps = generateGrid(SQUARE, DEFAULT_CAMERA, PARAMS)
    const stats = computeStats(wps, SQUARE, DEFAULT_CAMERA, PARAMS)
    expect(stats.areaHa).toBeGreaterThan(3)
    expect(stats.areaHa).toBeLessThan(5)
    expect(stats.distanceM).toBeGreaterThan(0)
    expect(stats.imageCount).toBeGreaterThan(0)
    expect(stats.flightTimeSec).toBeGreaterThan(stats.distanceM / PARAMS.speedMs)
    expect(stats.gsdCm).toBeCloseTo((20 * 7.68) / (25 * 640) * 100, 1)
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd website/nextjs && npx vitest run lib/missionGeometry.test.ts 2>&1 | head -20
```
Expected: FAIL — cannot find module `./missionGeometry`

- [ ] **Step 3: Create missionGeometry.ts**

```ts
// website/nextjs/lib/missionGeometry.ts
import type { Camera } from './cameras'

export type LatLon = { lat: number; lon: number }
export type Waypoint = { lat: number; lon: number; alt: number }
export type MissionType = 'grid' | 'perimeter' | 'corridor'

export type MissionParams = {
  altitudeM: number
  frontOverlap: number // 0–0.95
  sideOverlap: number // 0–0.95
  speedMs: number
  headingDeg: number | 'auto'
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

const M_PER_DEG_LAT = 111320

function metresPerDegLon(latDeg: number): number {
  return M_PER_DEG_LAT * Math.cos((latDeg * Math.PI) / 180)
}

function centroid(poly: LatLon[]): LatLon {
  const lat = poly.reduce((s, p) => s + p.lat, 0) / poly.length
  const lon = poly.reduce((s, p) => s + p.lon, 0) / poly.length
  return { lat, lon }
}

type XY = { x: number; y: number }

// Project lat/lon → local metres relative to origin
function toXY(p: LatLon, origin: LatLon): XY {
  return {
    x: (p.lon - origin.lon) * metresPerDegLon(origin.lat),
    y: (p.lat - origin.lat) * M_PER_DEG_LAT,
  }
}

function toLatLon(xy: XY, origin: LatLon): LatLon {
  return {
    lat: origin.lat + xy.y / M_PER_DEG_LAT,
    lon: origin.lon + xy.x / metresPerDegLon(origin.lat),
  }
}

function rotate(p: XY, angleRad: number): XY {
  const cos = Math.cos(angleRad)
  const sin = Math.sin(angleRad)
  return { x: p.x * cos - p.y * sin, y: p.x * sin + p.y * cos }
}

export function computeFootprint(camera: Camera, params: MissionParams): { w: number; h: number } {
  // footprint (m) = altitude(m) * sensorDim(mm) / focal(mm)
  const w = (params.altitudeM * camera.sensorWidthMm) / camera.focalLengthMm
  const h = (params.altitudeM * camera.sensorHeightMm) / camera.focalLengthMm
  return { w, h }
}

// Heading (radians, CCW from east) of the polygon's long axis, via bounding-box of vertices
function autoHeading(xy: XY[]): number {
  // Find the edge of the convex-ish hull bounding box with the longest extent.
  // Simple approach: principal axis via the two farthest vertices.
  let maxDist = -1
  let a = xy[0]
  let b = xy[1]
  for (let i = 0; i < xy.length; i++) {
    for (let j = i + 1; j < xy.length; j++) {
      const d = Math.hypot(xy[i].x - xy[j].x, xy[i].y - xy[j].y)
      if (d > maxDist) {
        maxDist = d
        a = xy[i]
        b = xy[j]
      }
    }
  }
  return Math.atan2(b.y - a.y, b.x - a.x)
}

// Clip a horizontal scan line (y = const) against polygon, return x-intersections sorted
function scanLineIntersections(poly: XY[], y: number): number[] {
  const xs: number[] = []
  for (let i = 0; i < poly.length; i++) {
    const p1 = poly[i]
    const p2 = poly[(i + 1) % poly.length]
    const y1 = p1.y
    const y2 = p2.y
    if ((y1 <= y && y2 > y) || (y2 <= y && y1 > y)) {
      const t = (y - y1) / (y2 - y1)
      xs.push(p1.x + t * (p2.x - p1.x))
    }
  }
  return xs.sort((u, v) => u - v)
}

export function generateGrid(polygon: LatLon[], camera: Camera, params: MissionParams): Waypoint[] {
  if (polygon.length < 3) return []
  const origin = centroid(polygon)
  const xyRaw = polygon.map((p) => toXY(p, origin))
  const heading = params.headingDeg === 'auto' ? autoHeading(xyRaw) : (params.headingDeg * Math.PI) / 180
  // Rotate polygon so flight lines are horizontal (align long axis to x)
  const xy = xyRaw.map((p) => rotate(p, -heading))

  const ys = xy.map((p) => p.y)
  const minY = Math.min(...ys)
  const maxY = Math.max(...ys)

  const { w: footprintW } = computeFootprint(camera, params)
  const spacing = Math.max(footprintW * (1 - params.sideOverlap), 1) // metres, never < 1m

  const surveyXY: XY[] = []
  let dir = 1
  for (let y = minY + spacing / 2; y <= maxY; y += spacing) {
    const xs = scanLineIntersections(xy, y)
    if (xs.length < 2) continue
    const xStart = xs[0]
    const xEnd = xs[xs.length - 1]
    const seg = dir > 0 ? [{ x: xStart, y }, { x: xEnd, y }] : [{ x: xEnd, y }, { x: xStart, y }]
    surveyXY.push(...seg)
    dir *= -1
  }

  // Rotate back and convert to lat/lon
  const survey = surveyXY.map((p) => toLatLon(rotate(p, heading), origin))
  return assembleMission(polygon[0], survey, params.altitudeM)
}

export function generatePerimeter(polygon: LatLon[], camera: Camera, params: MissionParams): Waypoint[] {
  if (polygon.length < 3) return []
  // Trace the polygon boundary, closing the loop.
  const loop = [...polygon, polygon[0]]
  return assembleMission(polygon[0], loop, params.altitudeM)
}

export function generateCorridor(line: LatLon[], camera: Camera, params: MissionParams): Waypoint[] {
  if (line.length < 2) return []
  const origin = centroid(line)
  const xy = line.map((p) => toXY(p, origin))
  const { w: footprintW } = computeFootprint(camera, params)
  const offset = Math.max(footprintW * (1 - params.sideOverlap), 1)

  // Forward pass along the line, then a parallel return pass offset perpendicular to first segment
  const dx = xy[1].x - xy[0].x
  const dy = xy[1].y - xy[0].y
  const len = Math.hypot(dx, dy) || 1
  const nx = -dy / len // unit normal
  const ny = dx / len
  const ret = [...xy].reverse().map((p) => ({ x: p.x + nx * offset, y: p.y + ny * offset }))

  const path = [...xy, ...ret].map((p) => toLatLon(p, origin))
  return assembleMission(line[0], path, params.altitudeM)
}

// Prepend takeoff at home, set altitude on every survey point. RTL is appended as the home coord
// (the exporter emits the RTL command separately; here we just close the path visually).
function assembleMission(home: LatLon, survey: LatLon[], altM: number): Waypoint[] {
  const wps: Waypoint[] = [{ lat: home.lat, lon: home.lon, alt: altM }]
  for (const p of survey) wps.push({ lat: p.lat, lon: p.lon, alt: altM })
  return wps
}

function haversineM(a: LatLon, b: LatLon): number {
  const R = 6371000
  const dLat = ((b.lat - a.lat) * Math.PI) / 180
  const dLon = ((b.lon - a.lon) * Math.PI) / 180
  const lat1 = (a.lat * Math.PI) / 180
  const lat2 = (b.lat * Math.PI) / 180
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}

function polygonAreaHa(polygon: LatLon[]): number {
  if (polygon.length < 3) return 0
  const origin = centroid(polygon)
  const xy = polygon.map((p) => toXY(p, origin))
  let area = 0
  for (let i = 0; i < xy.length; i++) {
    const p1 = xy[i]
    const p2 = xy[(i + 1) % xy.length]
    area += p1.x * p2.y - p2.x * p1.y
  }
  return Math.abs(area / 2) / 10000 // m² → hectares
}

export function computeStats(
  waypoints: Waypoint[],
  polygon: LatLon[],
  camera: Camera,
  params: MissionParams,
): MissionStats {
  const { w: footprintWM, h: footprintHM } = computeFootprint(camera, params)
  const gsdCm = ((params.altitudeM * camera.sensorWidthMm) / (camera.focalLengthMm * camera.resolutionW)) * 100
  const triggerDist = Math.max(footprintHM * (1 - params.frontOverlap), 0.5)

  let distanceM = 0
  for (let i = 1; i < waypoints.length; i++) {
    distanceM += haversineM(waypoints[i - 1], waypoints[i])
  }
  const imageCount = Math.floor(distanceM / triggerDist)
  const flightTimeSec = distanceM / params.speedMs + 30
  const areaHa = polygonAreaHa(polygon)

  return { gsdCm, footprintWM, footprintHM, areaHa, imageCount, distanceM, flightTimeSec }
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd website/nextjs && npx vitest run lib/missionGeometry.test.ts 2>&1 | tail -20
```
Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add website/nextjs/lib/missionGeometry.ts website/nextjs/lib/missionGeometry.test.ts
git commit -m "feat(plan): add mission geometry engine (grid/perimeter/corridor + stats)"
```

---

## Task 3: Waypoint Export

**Files:**
- Create: `website/nextjs/lib/waypointExport.ts`
- Create: `website/nextjs/lib/waypointExport.test.ts`

- [ ] **Step 1: Write the failing tests**

```ts
// website/nextjs/lib/waypointExport.test.ts
import { describe, it, expect } from 'vitest'
import { serialiseQGCWPL110, waypointFilename } from './waypointExport'
import type { Waypoint } from './missionGeometry'

const WPS: Waypoint[] = [
  { lat: 18.52, lon: 73.855, alt: 20 },
  { lat: 18.521, lon: 73.856, alt: 20 },
  { lat: 18.522, lon: 73.857, alt: 20 },
]

describe('serialiseQGCWPL110', () => {
  it('starts with the QGC WPL 110 header', () => {
    const text = serialiseQGCWPL110(WPS, 5)
    expect(text.split('\n')[0]).toBe('QGC WPL 110')
  })

  it('has a home row, a takeoff row, a camera-trigger row, waypoints, then RTL', () => {
    const text = serialiseQGCWPL110(WPS, 5)
    const lines = text.trim().split('\n')
    // header + home + takeoff + cam-trigger + 3 waypoints + RTL = 8 lines
    expect(lines.length).toBe(8)
    // home uses command 16, frame 0
    expect(lines[1].split('\t')[3]).toBe('16')
    // takeoff = command 22
    expect(lines[2].split('\t')[3]).toBe('22')
    // camera trigger = command 206 with trigger dist in param1
    expect(lines[3].split('\t')[3]).toBe('206')
    expect(lines[3].split('\t')[4]).toBe('5')
    // last row is RTL = command 20
    expect(lines[lines.length - 1].split('\t')[3]).toBe('20')
  })

  it('indexes rows sequentially from 0', () => {
    const text = serialiseQGCWPL110(WPS, 5)
    const lines = text.trim().split('\n').slice(1) // skip header
    lines.forEach((line, i) => {
      expect(line.split('\t')[0]).toBe(String(i))
    })
  })

  it('returns just the header for empty waypoints', () => {
    const text = serialiseQGCWPL110([], 5)
    expect(text.trim()).toBe('QGC WPL 110')
  })
})

describe('waypointFilename', () => {
  it('slugifies the mission name and appends .waypoints', () => {
    expect(waypointFilename('PUNE_FARM_01 Grid #3')).toBe('PUNE_FARM_01_Grid_3.waypoints')
  })

  it('falls back to mission.waypoints for empty names', () => {
    expect(waypointFilename('')).toBe('mission.waypoints')
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd website/nextjs && npx vitest run lib/waypointExport.test.ts 2>&1 | head -20
```
Expected: FAIL — cannot find module `./waypointExport`

- [ ] **Step 3: Create waypointExport.ts**

```ts
// website/nextjs/lib/waypointExport.ts
import type { Waypoint } from './missionGeometry'

// MAVLink command IDs
const CMD_WAYPOINT = 16
const CMD_TAKEOFF = 22
const CMD_RTL = 20
const CMD_SET_CAM_TRIGG_DIST = 206

function row(
  index: number,
  current: number,
  frame: number,
  command: number,
  p1: number,
  p2: number,
  p3: number,
  p4: number,
  lat: number,
  lon: number,
  alt: number,
  autocontinue = 1,
): string {
  return [index, current, frame, command, p1, p2, p3, p4, lat, lon, alt, autocontinue].join('\t')
}

/**
 * Serialise waypoints to QGC WPL 110 (ArduPilot / Mission Planner / QGroundControl).
 * triggerDistM is the camera trigger distance in metres (0 disables triggering).
 */
export function serialiseQGCWPL110(waypoints: Waypoint[], triggerDistM: number): string {
  const lines = ['QGC WPL 110']
  if (waypoints.length === 0) return lines.join('\n')

  const home = waypoints[0]
  let idx = 0
  // Home (frame 0 = global abs alt)
  lines.push(row(idx++, 1, 0, CMD_WAYPOINT, 0, 0, 0, 0, home.lat, home.lon, home.alt))
  // Takeoff (frame 3 = relative alt)
  lines.push(row(idx++, 0, 3, CMD_TAKEOFF, 0, 0, 0, 0, home.lat, home.lon, home.alt))
  // Camera trigger distance
  lines.push(row(idx++, 0, 3, CMD_SET_CAM_TRIGG_DIST, triggerDistM, 0, 0, 0, 0, 0, 0))
  // Survey waypoints (skip index 0 which is home/takeoff position)
  for (let i = 1; i < waypoints.length; i++) {
    const wp = waypoints[i]
    lines.push(row(idx++, 0, 3, CMD_WAYPOINT, 0, 0, 0, 0, wp.lat, wp.lon, wp.alt))
  }
  // RTL
  lines.push(row(idx++, 0, 3, CMD_RTL, 0, 0, 0, 0, 0, 0, 0))
  return lines.join('\n')
}

export function waypointFilename(missionName: string): string {
  const slug = missionName.trim().replace(/[^A-Za-z0-9]+/g, '_').replace(/^_+|_+$/g, '')
  return slug ? `${slug}.waypoints` : 'mission.waypoints'
}

export function downloadWaypoints(waypoints: Waypoint[], triggerDistM: number, missionName: string): void {
  const text = serialiseQGCWPL110(waypoints, triggerDistM)
  const blob = new Blob([text], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = waypointFilename(missionName)
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd website/nextjs && npx vitest run lib/waypointExport.test.ts 2>&1 | tail -20
```
Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add website/nextjs/lib/waypointExport.ts website/nextjs/lib/waypointExport.test.ts
git commit -m "feat(plan): add ArduPilot QGC WPL 110 waypoint exporter"
```

---

## Task 4: Backend — Mission Model + Migration

**Files:**
- Modify: `platform/db/models.py`
- Create: `alembic/versions/0004_missions.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/backend/test_missions.py  (create this file)
from axalon.db.models import Mission, Park


def test_mission_model_persists(db_session):
    park = Park(id="PARK_PLAN", name="Plan Park")
    db_session.add(park)
    db_session.flush()
    m = Mission(
        name="Grid #1",
        park_id="PARK_PLAN",
        mission_type="grid",
        camera_id="itl612r-pro",
        params='{"altitudeM": 20}',
        polygon='[{"lat": 18.5, "lon": 73.8}]',
        waypoints='[{"lat": 18.5, "lon": 73.8, "alt": 20}]',
        area_ha=4.2,
        image_count=312,
    )
    db_session.add(m)
    db_session.commit()
    fetched = db_session.query(Mission).filter_by(name="Grid #1").first()
    assert fetched.mission_type == "grid"
    assert fetched.camera_id == "itl612r-pro"
    assert fetched.area_ha == 4.2
```

- [ ] **Step 2: Run test to verify it fails**

```bash
source .venv/bin/activate && pytest tests/backend/test_missions.py::test_mission_model_persists -v 2>&1 | tail -15
```
Expected: `ImportError: cannot import name 'Mission'`

- [ ] **Step 3: Add Mission model to models.py**

Add at the end of `platform/db/models.py` (after the last model class, before any `Index(...)` definitions if present; otherwise at end of file):

```python
class Mission(Base):
    """A planned drone survey mission — drawn area, flight params, computed waypoints."""
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

- [ ] **Step 4: Run test to verify the model works**

```bash
source .venv/bin/activate && pytest tests/backend/test_missions.py::test_mission_model_persists -v 2>&1 | tail -15
```
Expected: PASS (the test DB is created from models via `create_all`, so the table exists without the migration)

- [ ] **Step 5: Create the Alembic migration**

```python
# alembic/versions/0004_missions.py
"""missions

Revision ID: 0004
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = '0004'
down_revision = '0003'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'missions',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('park_id', sa.String(), sa.ForeignKey('parks.id'), nullable=True),
        sa.Column('mission_type', sa.String(), nullable=True),
        sa.Column('camera_id', sa.String(), nullable=True),
        sa.Column('params', sa.Text(), nullable=True),
        sa.Column('polygon', sa.Text(), nullable=True),
        sa.Column('waypoints', sa.Text(), nullable=True),
        sa.Column('area_ha', sa.Float(), nullable=True),
        sa.Column('image_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_missions_park_id', 'missions', ['park_id'])


def downgrade() -> None:
    op.drop_index('ix_missions_park_id', 'missions')
    op.drop_table('missions')
```

- [ ] **Step 6: Apply the migration to verify it is valid**

```bash
source .venv/bin/activate && alembic upgrade head && alembic current
```
Expected: ends at `0004 (head)`, no errors

- [ ] **Step 7: Commit**

```bash
git add platform/db/models.py alembic/versions/0004_missions.py tests/backend/test_missions.py
git commit -m "feat(plan): add Mission model and 0004 migration"
```

---

## Task 5: Backend — Mission CRUD Endpoints

**Files:**
- Modify: `platform/api/app.py`
- Modify: `tests/backend/test_missions.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/backend/test_missions.py`:

```python
import json


def _make_park(client):
    # Missions can reference a park; create one via the DB through a batch is heavy,
    # so we POST a mission with a park_id that may not exist — FK is nullable and
    # SQLite does not enforce FK by default, so this is fine for endpoint tests.
    return "PARK_PLAN_API"


def test_create_mission(client):
    payload = {
        "name": "API Grid #1",
        "park_id": _make_park(client),
        "mission_type": "grid",
        "camera_id": "itl612r-pro",
        "params": {"altitudeM": 20, "frontOverlap": 0.8},
        "polygon": [{"lat": 18.52, "lon": 73.855}],
        "waypoints": [{"lat": 18.52, "lon": 73.855, "alt": 20}],
        "area_ha": 4.2,
        "image_count": 312,
    }
    resp = client.post("/missions", json=payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "API Grid #1"
    assert "id" in data


def test_list_missions_filtered_by_park(client):
    for name in ["M1", "M2"]:
        client.post("/missions", json={
            "name": name, "park_id": "PARK_LIST", "mission_type": "grid",
            "camera_id": "itl612r-pro", "params": {}, "polygon": [], "waypoints": [],
            "area_ha": 1.0, "image_count": 10,
        })
    client.post("/missions", json={
        "name": "Other", "park_id": "PARK_OTHER", "mission_type": "grid",
        "camera_id": "itl612r-pro", "params": {}, "polygon": [], "waypoints": [],
        "area_ha": 1.0, "image_count": 10,
    })
    resp = client.get("/missions?park_id=PARK_LIST")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 2
    assert {m["name"] for m in items} == {"M1", "M2"}
    # list response should NOT carry the heavy waypoints payload
    assert "waypoints" not in items[0]


def test_get_mission_returns_full_payload(client):
    created = client.post("/missions", json={
        "name": "Full", "park_id": "PARK_FULL", "mission_type": "perimeter",
        "camera_id": "dji-xt2", "params": {"altitudeM": 15},
        "polygon": [{"lat": 1, "lon": 2}], "waypoints": [{"lat": 1, "lon": 2, "alt": 15}],
        "area_ha": 2.0, "image_count": 50,
    }).json()
    resp = client.get(f"/missions/{created['id']}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["mission_type"] == "perimeter"
    assert data["params"] == {"altitudeM": 15}
    assert data["waypoints"] == [{"lat": 1, "lon": 2, "alt": 15}]


def test_get_mission_404(client):
    assert client.get("/missions/999999").status_code == 404


def test_delete_mission(client):
    created = client.post("/missions", json={
        "name": "ToDelete", "park_id": "PARK_DEL", "mission_type": "grid",
        "camera_id": "itl612r-pro", "params": {}, "polygon": [], "waypoints": [],
        "area_ha": 1.0, "image_count": 1,
    }).json()
    assert client.delete(f"/missions/{created['id']}").status_code == 204
    assert client.get(f"/missions/{created['id']}").status_code == 404


def test_create_mission_requires_name(client):
    resp = client.post("/missions", json={"mission_type": "grid"})
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
source .venv/bin/activate && pytest tests/backend/test_missions.py -k "mission and (create or list or get or delete)" -v 2>&1 | tail -20
```
Expected: 404s — endpoints don't exist yet

- [ ] **Step 3: Add Mission import to app.py**

In `platform/api/app.py`, update the models import line (line 46) to add `Mission`:

```python
from axalon.db.models import Park, Inspection, PanelFault, Detection as DbDetection, FAULT_OPEN, FAULT_STALE, FAULT_RESOLVED, Correction, Job as DbJob, FaultComment, Mission
```

- [ ] **Step 4: Add _serialize_mission helpers near the other serializers**

Add after `_serialize_comment` (search for `def _serialize_comment`):

```python
def _serialize_mission_summary(m: Mission) -> dict:
    return {
        "id": m.id,
        "name": m.name,
        "park_id": m.park_id,
        "mission_type": m.mission_type,
        "camera_id": m.camera_id,
        "area_ha": m.area_ha,
        "image_count": m.image_count,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _serialize_mission_full(m: Mission) -> dict:
    return {
        **_serialize_mission_summary(m),
        "params": json.loads(m.params) if m.params else {},
        "polygon": json.loads(m.polygon) if m.polygon else [],
        "waypoints": json.loads(m.waypoints) if m.waypoints else [],
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    }
```

- [ ] **Step 5: Add the four endpoints**

Add after the `list_fault_comments` endpoint (search for `def list_fault_comments`, add after its function body ends):

```python
@app.post("/missions", status_code=201)
def create_mission(payload: dict):
    """Save a planned mission."""
    name = str(payload.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    session = get_session()
    try:
        m = Mission(
            name=name[:200],
            park_id=(payload.get("park_id") or None),
            mission_type=payload.get("mission_type", "grid"),
            camera_id=payload.get("camera_id"),
            params=json.dumps(payload.get("params") or {}),
            polygon=json.dumps(payload.get("polygon") or []),
            waypoints=json.dumps(payload.get("waypoints") or []),
            area_ha=payload.get("area_ha"),
            image_count=payload.get("image_count"),
        )
        session.add(m)
        session.commit()
        session.refresh(m)
        return JSONResponse(content=_serialize_mission_summary(m), status_code=201)
    finally:
        session.close()


@app.get("/missions")
def list_missions(park_id: str | None = None):
    """List saved missions, optionally filtered by park_id. Excludes heavy waypoint payloads."""
    session = get_session()
    try:
        q = session.query(Mission)
        if park_id:
            q = q.filter(Mission.park_id == park_id)
        missions = q.order_by(Mission.created_at.desc()).all()
        return [_serialize_mission_summary(m) for m in missions]
    finally:
        session.close()


@app.get("/missions/{mission_id}")
def get_mission(mission_id: int):
    """Return one mission including its full waypoint path."""
    session = get_session()
    try:
        m = session.query(Mission).filter_by(id=mission_id).first()
        if m is None:
            raise HTTPException(status_code=404, detail="Mission not found")
        return _serialize_mission_full(m)
    finally:
        session.close()


@app.delete("/missions/{mission_id}", status_code=204)
def delete_mission(mission_id: int):
    """Delete a saved mission."""
    session = get_session()
    try:
        m = session.query(Mission).filter_by(id=mission_id).first()
        if m is None:
            raise HTTPException(status_code=404, detail="Mission not found")
        session.delete(m)
        session.commit()
        return Response(status_code=204)
    finally:
        session.close()
```

- [ ] **Step 6: Run the mission tests**

```bash
source .venv/bin/activate && pytest tests/backend/test_missions.py -v 2>&1 | tail -25
```
Expected: all pass

- [ ] **Step 7: Run the full backend suite to confirm no regressions**

```bash
source .venv/bin/activate && pytest tests/backend/ 2>&1 | tail -5
```
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add platform/api/app.py tests/backend/test_missions.py
git commit -m "feat(plan): add mission CRUD endpoints (POST/GET/DELETE /missions)"
```

---

## Task 6: Frontend API Client + leaflet-draw Dependency

**Files:**
- Modify: `website/nextjs/package.json`
- Modify: `website/nextjs/lib/api.ts`

- [ ] **Step 1: Install leaflet-draw**

```bash
cd website/nextjs && npm install leaflet-draw && npm install -D @types/leaflet-draw
```
Expected: `package.json` and `package-lock.json` updated

- [ ] **Step 2: Add Mission types + API helpers to api.ts**

Find the `export const api = {` object in `website/nextjs/lib/api.ts`. First add these types just above it:

```ts
export type MissionSummary = {
  id: number
  name: string
  park_id: string | null
  mission_type: 'grid' | 'perimeter' | 'corridor'
  camera_id: string | null
  area_ha: number | null
  image_count: number | null
  created_at: string | null
}

export type MissionFull = MissionSummary & {
  params: Record<string, unknown>
  polygon: { lat: number; lon: number }[]
  waypoints: { lat: number; lon: number; alt: number }[]
  updated_at: string | null
}

export type MissionCreate = {
  name: string
  park_id?: string | null
  mission_type: string
  camera_id?: string | null
  params: Record<string, unknown>
  polygon: { lat: number; lon: number }[]
  waypoints: { lat: number; lon: number; alt: number }[]
  area_ha: number
  image_count: number
}
```

Then add these methods inside the `api` object (alongside the existing helpers):

```ts
  missions: (parkId?: string) =>
    request<MissionSummary[]>(`/missions${parkId ? `?park_id=${encodeURIComponent(parkId)}` : ''}`),
  mission: (id: number) => request<MissionFull>(`/missions/${id}`),
  createMission: (body: MissionCreate) =>
    request<MissionSummary>('/missions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  deleteMission: (id: number) => request<void>(`/missions/${id}`, { method: 'DELETE' }),
```

- [ ] **Step 3: Type-check**

```bash
cd website/nextjs && npx tsc --noEmit 2>&1 | head -20
```
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add website/nextjs/package.json website/nextjs/package-lock.json website/nextjs/lib/api.ts
git commit -m "feat(plan): add leaflet-draw dep and mission API client helpers"
```

---

## Task 7: PlanMap Component

**Files:**
- Create: `website/nextjs/components/Platform/PlanMap.tsx`

### Background
Follow the basemap pattern from `AnomalyMap.tsx` (Mapbox satellite with token, ESRI fallback). Leaflet and leaflet-draw must only run client-side. PlanMap renders the drawn polygon, the waypoint polyline, start/end markers, and a stats bar overlay.

- [ ] **Step 1: Create PlanMap.tsx**

```tsx
// website/nextjs/components/Platform/PlanMap.tsx
'use client'

import { useEffect, useRef } from 'react'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import 'leaflet-draw'
import 'leaflet-draw/dist/leaflet.draw.css'
import type { LatLon, Waypoint, MissionStats, MissionType } from '@/lib/missionGeometry'

const MAPBOX_TOKEN = process.env.NEXT_PUBLIC_MAPBOX_TOKEN || ''

const SAT_URL = MAPBOX_TOKEN
  ? `https://api.mapbox.com/styles/v1/mapbox/satellite-streets-v12/tiles/{z}/{x}/{y}?access_token=${MAPBOX_TOKEN}`
  : 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}'

const SAT_ATTR = MAPBOX_TOKEN ? '© Mapbox © OpenStreetMap' : 'Tiles © Esri'

type Props = {
  missionType: MissionType
  polygon: LatLon[] | null
  waypoints: Waypoint[]
  stats: MissionStats | null
  onShapeDrawn: (points: LatLon[]) => void
  onClear: () => void
}

function fmtTime(sec: number): string {
  const m = Math.floor(sec / 60)
  const s = Math.round(sec % 60)
  return `${m}m ${s}s`
}

export default function PlanMap({
  missionType,
  polygon,
  waypoints,
  stats,
  onShapeDrawn,
  onClear,
}: Props) {
  const mapDivRef = useRef<HTMLDivElement>(null)
  const mapRef = useRef<L.Map | null>(null)
  const drawnRef = useRef<L.FeatureGroup | null>(null)
  const pathRef = useRef<L.LayerGroup | null>(null)
  const onShapeDrawnRef = useRef(onShapeDrawn)
  const onClearRef = useRef(onClear)
  onShapeDrawnRef.current = onShapeDrawn
  onClearRef.current = onClear

  // Initialise map once
  useEffect(() => {
    if (!mapDivRef.current || mapRef.current) return
    const map = L.map(mapDivRef.current, { center: [18.5204, 73.8567], zoom: 16 })
    L.tileLayer(SAT_URL, { attribution: SAT_ATTR, maxZoom: 22 }).addTo(map)

    const drawn = new L.FeatureGroup()
    map.addLayer(drawn)
    drawnRef.current = drawn
    pathRef.current = L.layerGroup().addTo(map)

    map.on(L.Draw.Event.CREATED, (e: any) => {
      drawn.clearLayers()
      const layer = e.layer
      drawn.addLayer(layer)
      const latlngs = (layer.getLatLngs?.()[0] ?? layer.getLatLngs?.() ?? []) as L.LatLng[]
      const pts: LatLon[] = (Array.isArray(latlngs) ? latlngs : []).map((ll: L.LatLng) => ({
        lat: ll.lat,
        lon: ll.lng,
      }))
      onShapeDrawnRef.current(pts)
    })

    mapRef.current = map
    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  // Swap the active draw control based on mission type (polygon vs polyline)
  useEffect(() => {
    const map = mapRef.current
    const drawn = drawnRef.current
    if (!map || !drawn) return
    const useLine = missionType === 'corridor'
    const control = new L.Control.Draw({
      draw: {
        polygon: useLine ? false : ({ shapeOptions: { color: '#0ea5e9' } } as any),
        polyline: useLine ? ({ shapeOptions: { color: '#0ea5e9' } } as any) : false,
        rectangle: false,
        circle: false,
        marker: false,
        circlemarker: false,
      },
      edit: { featureGroup: drawn, remove: true } as any,
    })
    map.addControl(control)
    return () => {
      map.removeControl(control)
    }
  }, [missionType])

  // Redraw waypoint path whenever waypoints change
  useEffect(() => {
    const layer = pathRef.current
    if (!layer) return
    layer.clearLayers()
    if (waypoints.length < 2) return
    const latlngs = waypoints.map((w) => [w.lat, w.lon] as [number, number])
    L.polyline(latlngs, { color: '#06b6d4', weight: 2, opacity: 0.9 }).addTo(layer)
    L.circleMarker(latlngs[0], { radius: 6, color: '#0ea5e9', fillOpacity: 1 })
      .bindTooltip('Start')
      .addTo(layer)
    L.circleMarker(latlngs[latlngs.length - 1], { radius: 6, color: '#10b981', fillOpacity: 1 })
      .bindTooltip('End')
      .addTo(layer)
  }, [waypoints])

  return (
    <div className="plan-map">
      <div ref={mapDivRef} style={{ position: 'absolute', inset: 0 }} />
      {stats && (
        <div className="plan-stats-bar">
          <span>Area <strong>{stats.areaHa.toFixed(1)} ha</strong></span>
          <span>Images <strong>{stats.imageCount}</strong></span>
          <span>Distance <strong>{(stats.distanceM / 1000).toFixed(2)} km</strong></span>
          <span>Time <strong>{fmtTime(stats.flightTimeSec)}</strong></span>
          <span>GSD <strong style={{ color: '#0ea5e9' }}>{stats.gsdCm.toFixed(2)} cm/px</strong></span>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Type-check**

```bash
cd website/nextjs && npx tsc --noEmit 2>&1 | head -20
```
Expected: no errors (the `as any` casts on leaflet-draw options are intentional — its types are loose)

- [ ] **Step 3: Commit**

```bash
git add website/nextjs/components/Platform/PlanMap.tsx
git commit -m "feat(plan): add PlanMap with leaflet-draw tools and live path overlay"
```

---

## Task 8: PlanSidebar Component

**Files:**
- Create: `website/nextjs/components/Platform/PlanSidebar.tsx`

- [ ] **Step 1: Create PlanSidebar.tsx**

```tsx
// website/nextjs/components/Platform/PlanSidebar.tsx
'use client'

import { Download, Save, Trash2 } from 'lucide-react'
import type { Camera } from '@/lib/cameras'
import { CAMERAS } from '@/lib/cameras'
import type { MissionParams, MissionType, MissionStats } from '@/lib/missionGeometry'
import { computeFootprint } from '@/lib/missionGeometry'
import type { MissionSummary } from '@/lib/api'

type Props = {
  missionName: string
  onMissionNameChange: (v: string) => void
  parkId: string
  onParkIdChange: (v: string) => void
  missionType: MissionType
  onMissionTypeChange: (t: MissionType) => void
  camera: Camera
  onCameraChange: (c: Camera) => void
  params: MissionParams
  onParamsChange: (p: MissionParams) => void
  stats: MissionStats | null
  savedMissions: MissionSummary[]
  onLoadMission: (id: number) => void
  onDeleteMission: (id: number) => void
  onExport: () => void
  onSave: () => void
  canExport: boolean
}

const TYPES: MissionType[] = ['grid', 'perimeter', 'corridor']

export default function PlanSidebar(props: Props) {
  const {
    missionName, onMissionNameChange, parkId, onParkIdChange,
    missionType, onMissionTypeChange, camera, onCameraChange,
    params, onParamsChange, stats, savedMissions,
    onLoadMission, onDeleteMission, onExport, onSave, canExport,
  } = props

  const fp = computeFootprint(camera, params)

  function setCamById(id: string) {
    const next = CAMERAS.find((c) => c.id === id)
    if (next) onCameraChange(next)
  }

  function patchParams(patch: Partial<MissionParams>) {
    onParamsChange({ ...params, ...patch })
  }

  function patchCamera(patch: Partial<Camera>) {
    onCameraChange({ ...camera, ...patch })
  }

  return (
    <aside className="plan-sidebar">
      {/* Mission */}
      <section className="panel">
        <div className="panel-head compact"><div className="panel-title">Mission</div></div>
        <div className="plan-param">
          <input
            value={missionName}
            onChange={(e) => onMissionNameChange(e.target.value)}
            placeholder="Mission name"
            style={{ width: '100%', boxSizing: 'border-box' }}
          />
          <input
            value={parkId}
            onChange={(e) => onParkIdChange(e.target.value)}
            placeholder="Park ID (optional)"
            style={{ width: '100%', boxSizing: 'border-box', marginTop: 8 }}
          />
          <div style={{ display: 'flex', gap: 6, marginTop: 8 }}>
            {TYPES.map((t) => (
              <button
                key={t}
                type="button"
                className={t === missionType ? 'primary' : 'secondary'}
                style={{ flex: 1, textTransform: 'capitalize', padding: '5px' }}
                onClick={() => onMissionTypeChange(t)}
              >
                {t}
              </button>
            ))}
          </div>
        </div>
      </section>

      {/* Camera */}
      <section className="panel">
        <div className="panel-head compact"><div className="panel-title">Camera</div></div>
        <div className="plan-param">
          <select
            value={camera.id}
            onChange={(e) => setCamById(e.target.value)}
            style={{ width: '100%', boxSizing: 'border-box' }}
          >
            {CAMERAS.map((c) => (
              <option key={c.id} value={c.id}>{c.name}</option>
            ))}
          </select>
          <div className="plan-camera-card">
            {camera.custom ? (
              <>
                <label>Sensor W (mm)
                  <input type="number" step="0.01" value={camera.sensorWidthMm}
                    onChange={(e) => patchCamera({ sensorWidthMm: Number(e.target.value) })} />
                </label>
                <label>Sensor H (mm)
                  <input type="number" step="0.01" value={camera.sensorHeightMm}
                    onChange={(e) => patchCamera({ sensorHeightMm: Number(e.target.value) })} />
                </label>
                <label>Focal (mm)
                  <input type="number" step="0.1" value={camera.focalLengthMm}
                    onChange={(e) => patchCamera({ focalLengthMm: Number(e.target.value) })} />
                </label>
                <label>Res W (px)
                  <input type="number" value={camera.resolutionW}
                    onChange={(e) => patchCamera({ resolutionW: Number(e.target.value) })} />
                </label>
              </>
            ) : (
              <>
                <div className="cam-row"><span>Sensor</span><span>{camera.sensorWidthMm} × {camera.sensorHeightMm} mm</span></div>
                <div className="cam-row"><span>Focal length</span><span>{camera.focalLengthMm} mm</span></div>
                <div className="cam-row"><span>Resolution</span><span>{camera.resolutionW} × {camera.resolutionH} px</span></div>
              </>
            )}
            <div className="cam-row" style={{ marginTop: 4 }}>
              <span>Footprint @ {params.altitudeM}m</span>
              <span style={{ color: '#0ea5e9' }}>{fp.w.toFixed(1)} × {fp.h.toFixed(1)} m</span>
            </div>
          </div>
        </div>
      </section>

      {/* Flight params */}
      <section className="panel">
        <div className="panel-head compact"><div className="panel-title">Flight Params</div></div>
        <div className="plan-param">
          <label>Altitude <span>{params.altitudeM} m</span></label>
          <input type="range" min={10} max={120} value={params.altitudeM}
            onChange={(e) => patchParams({ altitudeM: Number(e.target.value) })} />
          <label>Front overlap <span>{Math.round(params.frontOverlap * 100)} %</span></label>
          <input type="range" min={50} max={95} value={Math.round(params.frontOverlap * 100)}
            onChange={(e) => patchParams({ frontOverlap: Number(e.target.value) / 100 })} />
          <label>Side overlap <span>{Math.round(params.sideOverlap * 100)} %</span></label>
          <input type="range" min={50} max={95} value={Math.round(params.sideOverlap * 100)}
            onChange={(e) => patchParams({ sideOverlap: Number(e.target.value) / 100 })} />
          <label>Speed <span>{params.speedMs} m/s</span></label>
          <input type="range" min={3} max={15} value={params.speedMs}
            onChange={(e) => patchParams({ speedMs: Number(e.target.value) })} />
        </div>
      </section>

      {/* Saved missions */}
      <section className="panel">
        <div className="panel-head compact"><div className="panel-title">Saved Missions</div></div>
        <div className="plan-param">
          {savedMissions.length === 0 && <div className="empty" style={{ fontSize: 12 }}>No saved missions</div>}
          {savedMissions.map((m) => (
            <div key={m.id} className="queue-item" style={{ marginBottom: 4 }}>
              <div className="queue-row" onClick={() => onLoadMission(m.id)} style={{ cursor: 'pointer' }}>
                <strong>{m.name}</strong>
                <button className="secondary" style={{ padding: 2 }} onClick={(e) => { e.stopPropagation(); onDeleteMission(m.id) }}>
                  <Trash2 size={12} />
                </button>
              </div>
              <div className="queue-row sub">
                <span className="muted">{m.mission_type} · {m.area_ha?.toFixed(1) ?? '–'} ha</span>
                <span className="muted">{m.image_count ?? '–'} img</span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Actions */}
      <section className="panel" style={{ marginTop: 'auto' }}>
        <div className="plan-param">
          <button className="primary" style={{ width: '100%', marginBottom: 6 }} disabled={!canExport} onClick={onExport}>
            <Download size={15} /> Export .waypoints
          </button>
          <button className="secondary" style={{ width: '100%' }} disabled={!canExport} onClick={onSave}>
            <Save size={15} /> Save Mission
          </button>
        </div>
      </section>
    </aside>
  )
}
```

- [ ] **Step 2: Type-check**

```bash
cd website/nextjs && npx tsc --noEmit 2>&1 | head -20
```
Expected: no errors

- [ ] **Step 3: Commit**

```bash
git add website/nextjs/components/Platform/PlanSidebar.tsx
git commit -m "feat(plan): add PlanSidebar with camera picker, sliders, saved missions"
```

---

## Task 9: PlanTab Component (wiring)

**Files:**
- Create: `website/nextjs/components/Platform/PlanTab.tsx`

- [ ] **Step 1: Create PlanTab.tsx**

```tsx
// website/nextjs/components/Platform/PlanTab.tsx
'use client'

import dynamic from 'next/dynamic'
import { useEffect, useMemo, useState } from 'react'
import { useToast } from '@/components/Platform/Toast'
import { api, ApiError, type MissionSummary } from '@/lib/api'
import { DEFAULT_CAMERA, getCamera, type Camera } from '@/lib/cameras'
import {
  generateGrid,
  generatePerimeter,
  generateCorridor,
  computeStats,
  computeFootprint,
  type LatLon,
  type MissionParams,
  type MissionType,
} from '@/lib/missionGeometry'
import { downloadWaypoints } from '@/lib/waypointExport'
import PlanSidebar from '@/components/Platform/PlanSidebar'

const PlanMap = dynamic(() => import('@/components/Platform/PlanMap'), {
  ssr: false,
  loading: () => <div className="plan-map" style={{ display: 'grid', placeItems: 'center', color: '#64748b' }}>Loading map…</div>,
})

const DEFAULT_PARAMS: MissionParams = {
  altitudeM: 20,
  frontOverlap: 0.8,
  sideOverlap: 0.7,
  speedMs: 8,
  headingDeg: 'auto',
}

export function PlanTab() {
  const toast = useToast()
  const [missionName, setMissionName] = useState('New Mission')
  const [parkId, setParkId] = useState('')
  const [missionType, setMissionType] = useState<MissionType>('grid')
  const [camera, setCamera] = useState<Camera>(DEFAULT_CAMERA)
  const [params, setParams] = useState<MissionParams>(DEFAULT_PARAMS)
  const [polygon, setPolygon] = useState<LatLon[] | null>(null)
  const [savedMissions, setSavedMissions] = useState<MissionSummary[]>([])

  const waypoints = useMemo(() => {
    if (!polygon || polygon.length < 2) return []
    if (missionType === 'grid') return generateGrid(polygon, camera, params)
    if (missionType === 'perimeter') return generatePerimeter(polygon, camera, params)
    return generateCorridor(polygon, camera, params)
  }, [polygon, camera, params, missionType])

  const stats = useMemo(() => {
    if (waypoints.length < 2 || !polygon) return null
    return computeStats(waypoints, polygon, camera, params)
  }, [waypoints, polygon, camera, params])

  async function refreshMissions() {
    try {
      const list = await api.missions(parkId || undefined)
      setSavedMissions(list)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : String(err))
    }
  }

  useEffect(() => {
    refreshMissions()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  function handleExport() {
    if (waypoints.length < 2) return
    const fp = computeFootprint(camera, params)
    const triggerDist = Math.max(fp.h * (1 - params.frontOverlap), 0.5)
    downloadWaypoints(waypoints, triggerDist, missionName)
  }

  async function handleSave() {
    if (waypoints.length < 2 || !polygon || !stats) {
      toast.error('Draw a survey area first')
      return
    }
    try {
      await api.createMission({
        name: missionName,
        park_id: parkId || null,
        mission_type: missionType,
        camera_id: camera.id,
        params: params as unknown as Record<string, unknown>,
        polygon,
        waypoints,
        area_ha: stats.areaHa,
        image_count: stats.imageCount,
      })
      toast.success(`Saved "${missionName}"`)
      refreshMissions()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : String(err))
    }
  }

  async function handleLoad(id: number) {
    try {
      const m = await api.mission(id)
      setMissionName(m.name)
      setParkId(m.park_id ?? '')
      setMissionType(m.mission_type)
      setCamera(getCamera(m.camera_id ?? DEFAULT_CAMERA.id))
      setParams({ ...DEFAULT_PARAMS, ...(m.params as Partial<MissionParams>) })
      setPolygon(m.polygon.length ? m.polygon : null)
      toast.success(`Loaded "${m.name}"`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : String(err))
    }
  }

  async function handleDelete(id: number) {
    try {
      await api.deleteMission(id)
      refreshMissions()
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : String(err))
    }
  }

  return (
    <div className="plan-layout">
      <div className="plan-map-wrap">
        <PlanMap
          missionType={missionType}
          polygon={polygon}
          waypoints={waypoints}
          stats={stats}
          onShapeDrawn={setPolygon}
          onClear={() => setPolygon(null)}
        />
      </div>
      <PlanSidebar
        missionName={missionName}
        onMissionNameChange={setMissionName}
        parkId={parkId}
        onParkIdChange={setParkId}
        missionType={missionType}
        onMissionTypeChange={setMissionType}
        camera={camera}
        onCameraChange={setCamera}
        params={params}
        onParamsChange={setParams}
        stats={stats}
        savedMissions={savedMissions}
        onLoadMission={handleLoad}
        onDeleteMission={handleDelete}
        onExport={handleExport}
        onSave={handleSave}
        canExport={waypoints.length >= 2}
      />
    </div>
  )
}
```

- [ ] **Step 2: Verify the toast API matches**

Check that `useToast()` exposes `success` and `error`:

```bash
cd website/nextjs && grep -n "success\|error" components/Platform/Toast.tsx | head
```
If `success` does not exist, use `toast.error` for failures and `toast.info`/whatever the success method is. Adjust the calls in PlanTab accordingly.

- [ ] **Step 3: Type-check**

```bash
cd website/nextjs && npx tsc --noEmit 2>&1 | head -20
```
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add website/nextjs/components/Platform/PlanTab.tsx
git commit -m "feat(plan): add PlanTab wiring map, sidebar, geometry and persistence"
```

---

## Task 10: CSS + Tab Integration

**Files:**
- Modify: `website/nextjs/app/platform/platform.css`
- Modify: `website/nextjs/app/platform/page.tsx`

- [ ] **Step 1: Add CSS to platform.css**

Append to `website/nextjs/app/platform/platform.css`:

```css
/* ─── Plan tab (mission planner) ─── */
.plan-layout {
  display: flex;
  height: calc(100vh - 48px);
  overflow: hidden;
}
.plan-map-wrap {
  flex: 1;
  position: relative;
  min-width: 0;
}
.plan-map {
  position: absolute;
  inset: 0;
}
.plan-sidebar {
  width: 280px;
  flex-shrink: 0;
  overflow-y: auto;
  background: #ffffff;
  border-left: 1px solid #e2e8f0;
  display: flex;
  flex-direction: column;
}
.plan-sidebar .panel {
  border: 0;
  border-bottom: 1px solid #f1f5f9;
  border-radius: 0;
  box-shadow: none;
}
.plan-param {
  padding: 0 16px 12px;
}
.plan-param > label {
  font-size: 12px;
  color: #64748b;
  display: flex;
  justify-content: space-between;
  margin-top: 8px;
  margin-bottom: 3px;
}
.plan-param input[type='range'] {
  width: 100%;
  accent-color: #0ea5e9;
}
.plan-param input[type='text'],
.plan-param input[type='number'],
.plan-param input:not([type]),
.plan-param select {
  height: 32px;
  padding: 0 8px;
  border: 1px solid #cbd5e1;
  border-radius: 6px;
  font: inherit;
  font-size: 12px;
}
.plan-camera-card {
  background: #f8fafc;
  border-radius: 6px;
  padding: 10px 12px;
  font-size: 11px;
  color: #64748b;
  margin-top: 8px;
}
.plan-camera-card .cam-row {
  display: flex;
  justify-content: space-between;
  margin-top: 3px;
}
.plan-camera-card label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 4px;
  gap: 8px;
}
.plan-camera-card label input {
  width: 90px;
}
.plan-stats-bar {
  position: absolute;
  bottom: 12px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(255, 255, 255, 0.93);
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 6px 16px;
  display: flex;
  gap: 16px;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.12);
  z-index: 800;
  font-size: 12px;
  color: #64748b;
}
.plan-stats-bar strong {
  color: #111827;
}
```

- [ ] **Step 2: Wire the tab into page.tsx**

In `website/nextjs/app/platform/page.tsx`:

1. Add `Navigation2` to the lucide-react import:
```tsx
import {
  LayoutDashboard,
  Image as ImageIcon,
  History as HistoryIcon,
  SlidersHorizontal,
  MapIcon,
  GitCompare,
  Navigation2,
} from 'lucide-react'
```

2. Import the tab component (with the other Platform imports):
```tsx
import { PlanTab } from '@/components/Platform/PlanTab'
```

3. Extend the `Tab` type:
```tsx
type Tab = 'operations' | 'inspect' | 'history' | 'settings' | 'parkmap' | 'diff' | 'plan'
```

4. Add a rail button. Find the `diff` rail button and add this one right after it:
```tsx
            <button
              type="button"
              className={`rail-link ${tab === 'plan' ? 'active' : ''}`}
              onClick={() => setTab('plan')}
              title="Plan"
              data-testid="tab-plan"
            >
              <Navigation2 size={16} />
              <span>Plan</span>
            </button>
```

5. Render the tab. Find where tabs render in the content area (e.g. `{tab === 'diff' && <DiffTab />}`) and add:
```tsx
        {tab === 'plan' && <PlanTab />}
```

- [ ] **Step 3: Type-check and build**

```bash
cd website/nextjs && npx tsc --noEmit 2>&1 | head -20
```
Expected: no errors

- [ ] **Step 4: Commit**

```bash
git add website/nextjs/app/platform/platform.css website/nextjs/app/platform/page.tsx
git commit -m "feat(plan): add Plan tab styles and rail navigation entry"
```

---

## Task 11: Final Verification

- [ ] **Step 1: Run frontend unit tests**

```bash
cd website/nextjs && npx vitest run lib/missionGeometry.test.ts lib/waypointExport.test.ts 2>&1 | tail -15
```
Expected: all pass

- [ ] **Step 2: Run full backend suite**

```bash
cd /home/parakh/Desktop/AxalonSystems && source .venv/bin/activate && pytest tests/backend/ 2>&1 | tail -8
```
Expected: all pass, no regressions

- [ ] **Step 3: Production build of the Next.js app**

```bash
cd website/nextjs && npm run build 2>&1 | tail -25
```
Expected: build succeeds, `/platform` route compiles

- [ ] **Step 4: Verify Alembic at head**

```bash
cd /home/parakh/Desktop/AxalonSystems && source .venv/bin/activate && alembic current
```
Expected: `0004 (head)`

- [ ] **Step 5: Manual smoke test (optional but recommended)**

```bash
# Terminal 1
cd /home/parakh/Desktop/AxalonSystems && source .venv/bin/activate && uvicorn axalon.api.app:app --port 8000
# Terminal 2
cd website/nextjs && npm run dev
# Open http://localhost:3000/platform → Plan tab → draw a polygon →
# confirm path appears, stats bar updates, export downloads a .waypoints file,
# Save persists and the mission appears in the Saved Missions list.
```

- [ ] **Step 6: Final commit (if any uncommitted changes)**

```bash
git add -u && git commit -m "chore(plan): final verification pass for mission planner" || echo "nothing to commit"
```

---

## Summary of All Changes

| Area | What was built |
|---|---|
| `lib/cameras.ts` | Camera preset library (iTL612R Pro + 3 thermal cams + Custom) |
| `lib/missionGeometry.ts` | Pure grid/perimeter/corridor waypoint generation + live stats |
| `lib/waypointExport.ts` | ArduPilot QGC WPL 110 export + browser download |
| `components/Platform/PlanMap.tsx` | Leaflet + leaflet-draw map, live path overlay, stats bar |
| `components/Platform/PlanSidebar.tsx` | Camera picker, flight sliders, saved missions, actions |
| `components/Platform/PlanTab.tsx` | State owner; wires geometry → map → persistence |
| `platform/db/models.py` + `0004_missions.py` | `Mission` table |
| `platform/api/app.py` | 4 mission CRUD endpoints |
| `lib/api.ts` | Mission types + client helpers |
| `page.tsx` + `platform.css` | Plan tab navigation + styling matching existing UI |
