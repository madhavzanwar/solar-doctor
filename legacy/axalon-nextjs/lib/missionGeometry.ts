// website/nextjs/lib/missionGeometry.ts
import type { Camera } from './cameras'

export type LatLon = { lat: number; lon: number }
export type Waypoint = {
  lat: number
  lon: number
  alt: number
  heading?: number // deg, 0=N clockwise — drone/camera facing (arrows, α alignment, export)
  gimbalPitch?: number // deg, negative = down (orbit aims by atan2(alt, radius))
  leg?: number // 0-based battery leg index
}
export type MissionType = 'grid' | 'perimeter' | 'corridor' | 'orbit' | 'solar'

export type MissionParams = {
  altitudeM: number
  frontOverlap: number // 0–0.95
  sideOverlap: number // 0–0.95
  speedMs: number
  headingDeg: number | 'auto' // α: panel-row azimuth for grid
  rowAngleDeg?: number // α: solar row angle, CCW from east/horizontal
  droneHeadingDeg?: number | 'auto' // solar drone/camera orientation
  batteryMinutes?: number // usable flight time per battery (default 18)
  batteryReservePct?: number // reserve margin %, default 20
  orbitRadiusM?: number // orbit pattern (default 30)
  orbitPhotoCount?: number // orbit pattern (default 16)
  gimbalPitchDeg?: number // camera pitch for grid/perimeter/corridor/solar (default -90 nadir)
}

export type MissionStats = {
  gsdCm: number
  footprintWM: number
  footprintHM: number
  areaHa: number
  imageCount: number
  distanceM: number
  flightTimeSec: number
  legCount: number
  batteryCount: number
}

const M_PER_DEG_LAT = 111320
const DEFAULT_BATTERY_MIN = 18
const DEFAULT_RESERVE_PCT = 20
const DEFAULT_ORBIT_RADIUS = 30
const DEFAULT_ORBIT_PHOTOS = 16

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

// Initial bearing a→b in degrees, 0=N clockwise.
export function bearingDeg(a: LatLon, b: LatLon): number {
  const phi1 = (a.lat * Math.PI) / 180
  const phi2 = (b.lat * Math.PI) / 180
  const dLon = ((b.lon - a.lon) * Math.PI) / 180
  const y = Math.sin(dLon) * Math.cos(phi2)
  const x = Math.cos(phi1) * Math.sin(phi2) - Math.sin(phi1) * Math.cos(phi2) * Math.cos(dLon)
  return (((Math.atan2(y, x) * 180) / Math.PI) + 360) % 360
}

// Set each waypoint's heading to its travel bearing (toward the next point;
// last point keeps the previous bearing). Already-set headings (orbit) are kept.
function withTravelHeadings(wps: Waypoint[]): Waypoint[] {
  if (wps.length < 2) return wps.map((w) => ({ ...w }))
  return wps.map((w, i) => {
    if (w.heading !== undefined) return { ...w }
    const heading = i < wps.length - 1 ? bearingDeg(w, wps[i + 1]) : bearingDeg(wps[i - 1], w)
    return { ...w, heading }
  })
}

export function computeFootprint(camera: Camera, params: MissionParams): { w: number; h: number } {
  // footprint (m) = altitude(m) * sensorDim(mm) / focal(mm)
  const w = (params.altitudeM * camera.sensorWidthMm) / camera.focalLengthMm
  const h = (params.altitudeM * camera.sensorHeightMm) / camera.focalLengthMm
  return { w, h }
}

// Heading (radians, CCW from east) of the polygon's long axis, via the two farthest vertices
function autoHeading(xy: XY[]): number {
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
  // headingDeg is α (panel-row azimuth, 0=N clockwise) → convert to math angle (CCW from east).
  const heading =
    params.headingDeg === 'auto'
      ? autoHeading(xyRaw)
      : ((90 - params.headingDeg) * Math.PI) / 180
  // Rotate polygon so flight lines are horizontal (align long axis / α to x)
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
  return withTravelHeadings(assembleMission(polygon[0], survey, params.altitudeM, params.gimbalPitchDeg))
}

export function generatePerimeter(polygon: LatLon[], camera: Camera, params: MissionParams): Waypoint[] {
  if (polygon.length < 3) return []
  // Trace the polygon boundary, closing the loop.
  const loop = [...polygon, polygon[0]]
  return withTravelHeadings(assembleMission(polygon[0], loop, params.altitudeM, params.gimbalPitchDeg))
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
  return withTravelHeadings(assembleMission(line[0], path, params.altitudeM, params.gimbalPitchDeg))
}

// Orbit / point-of-interest: a ring of photos around `center`, camera aimed inward.
export function generateOrbit(center: LatLon, camera: Camera, params: MissionParams): Waypoint[] {
  const radius = Math.max(params.orbitRadiusM ?? DEFAULT_ORBIT_RADIUS, 1)
  const count = Math.max(Math.round(params.orbitPhotoCount ?? DEFAULT_ORBIT_PHOTOS), 3)
  const alt = params.altitudeM
  const gimbalPitch = -((Math.atan2(alt, radius) * 180) / Math.PI) // look down toward the target
  const wps: Waypoint[] = []
  for (let k = 0; k < count; k++) {
    const ang = (2 * Math.PI * k) / count
    const p = toLatLon({ x: radius * Math.cos(ang), y: radius * Math.sin(ang) }, center)
    wps.push({ lat: p.lat, lon: p.lon, alt, heading: bearingDeg(p, center), gimbalPitch })
  }
  return wps
}

// Resolved compass bearing (deg, 0=N clockwise) of the grid sweep lines — for display.
export function resolvedHeadingDeg(polygon: LatLon[], params: MissionParams): number {
  if (params.headingDeg !== 'auto') return ((params.headingDeg % 360) + 360) % 360
  if (polygon.length < 3) return 0
  const xy = polygon.map((p) => toXY(p, centroid(polygon)))
  const deg = (autoHeading(xy) * 180) / Math.PI // CCW from east
  return (((90 - deg) % 360) + 360) % 360 // → compass
}

// Solar manual-row mode: draw the array area, set row angle α, then click one
// center point on each row. Every clicked row becomes a line at α clipped to area.
export function generateSolar(area: LatLon[], rowCenters: LatLon[], params: MissionParams): Waypoint[] {
  if (area.length < 3 || rowCenters.length < 1) return []
  const origin = centroid(area)
  const aRad = ((params.rowAngleDeg ?? 0) * Math.PI) / 180
  const rotArea = area.map((p) => rotate(toXY(p, origin), -aRad))

  const rows = rowCenters
    .map((c) => rotate(toXY(c, origin), -aRad))
    .map((rc) => {
      const xs = scanLineIntersections(rotArea, rc.y)
      if (xs.length < 2) return null
      return {
        y: rc.y,
        e1: { x: xs[0], y: rc.y },
        e2: { x: xs[xs.length - 1], y: rc.y },
      }
    })
    .filter((row): row is { y: number; e1: XY; e2: XY } => row !== null)
    .sort((m, n) => m.y - n.y)

  const surveyXY: XY[] = []
  let dir = 1
  for (const row of rows) {
    surveyXY.push(...(dir > 0 ? [row.e1, row.e2] : [row.e2, row.e1]))
    dir *= -1
  }

  const g = params.gimbalPitchDeg ?? -90
  const survey = surveyXY.map((p) => toLatLon(rotate(p, aRad), origin))
  const wps: Waypoint[] = survey.map((p) => ({
    lat: p.lat,
    lon: p.lon,
    alt: params.altitudeM,
    gimbalPitch: g,
    heading: typeof params.droneHeadingDeg === 'number' ? params.droneHeadingDeg : undefined,
  }))
  return typeof params.droneHeadingDeg === 'number' ? wps : withTravelHeadings(wps)
}

// Prepend takeoff at home, set altitude on every survey point. RTL is appended by the exporter;
// here we just build the visible flight path starting from home.
function assembleMission(home: LatLon, survey: LatLon[], altM: number, gimbalPitch?: number): Waypoint[] {
  const g = gimbalPitch ?? -90
  const wps: Waypoint[] = [{ lat: home.lat, lon: home.lon, alt: altM, gimbalPitch: g }]
  for (const p of survey) wps.push({ lat: p.lat, lon: p.lon, alt: altM, gimbalPitch: g })
  return wps
}

// Tag waypoints with a 0-based battery leg index. A new leg starts when the next
// segment would push the current leg's flight time past the usable budget.
export function splitByBattery(
  waypoints: Waypoint[],
  params: MissionParams,
): { waypoints: Waypoint[]; legCount: number } {
  if (waypoints.length === 0) return { waypoints: [], legCount: 0 }
  const budgetSec =
    (params.batteryMinutes ?? DEFAULT_BATTERY_MIN) * 60 *
    (1 - (params.batteryReservePct ?? DEFAULT_RESERVE_PCT) / 100)
  const speed = Math.max(params.speedMs, 0.1)
  let leg = 0
  let legTime = 0
  const out: Waypoint[] = [{ ...waypoints[0], leg }]
  for (let i = 1; i < waypoints.length; i++) {
    const segTime = haversineM(waypoints[i - 1], waypoints[i]) / speed
    if (budgetSec > 0 && legTime + segTime > budgetSec && legTime > 0) {
      leg++
      legTime = segTime
    } else {
      legTime += segTime
    }
    out.push({ ...waypoints[i], leg })
  }
  return { waypoints: out, legCount: leg + 1 }
}

// Walk the assembled flight path and place a point at every `triggerDistM`
// travelled, matching what CMD_SET_CAM_TRIGG_DIST makes the flight controller
// do onboard (continuous distance-based triggering from the moment the
// command is issued, independent of leg/RTL boundaries). This is the list of
// expected image-capture coordinates, which the mission export previously
// only encoded as a trigger *interval* rather than concrete points.
export function computeCapturePoints(waypoints: Waypoint[], triggerDistM: number): Waypoint[] {
  if (waypoints.length < 2 || triggerDistM <= 0) return []
  const points: Waypoint[] = []
  let carry = 0 // distance remaining until the next trigger, carried across segments
  for (let i = 1; i < waypoints.length; i++) {
    const a = waypoints[i - 1]
    const b = waypoints[i]
    const segLen = haversineM(a, b)
    if (segLen <= 0) continue
    const heading = b.heading ?? bearingDeg(a, b)
    let travelled = triggerDistM - carry
    while (travelled <= segLen) {
      const t = travelled / segLen
      points.push({
        lat: a.lat + (b.lat - a.lat) * t,
        lon: a.lon + (b.lon - a.lon) * t,
        alt: a.alt + (b.alt - a.alt) * t,
        heading,
        leg: b.leg,
      })
      travelled += triggerDistM
    }
    carry = segLen - (travelled - triggerDistM)
  }
  return points
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
  const areaHa = polygon.length >= 3 ? polygonAreaHa(polygon) : 0
  const legCount = splitByBattery(waypoints, params).legCount

  return {
    gsdCm,
    footprintWM,
    footprintHM,
    areaHa,
    imageCount,
    distanceM,
    flightTimeSec,
    legCount,
    batteryCount: legCount,
  }
}
