import { describe, it, expect } from 'vitest'
import { toLitchiCsv, toKml, toQgcPlan, serialiseMission, fileSlug } from '@/lib/waypointExport'
import type { Waypoint, MissionParams } from '@/lib/missionGeometry'

const WPS: Waypoint[] = [
  { lat: 18.52, lon: 73.85, alt: 20 },
  { lat: 18.521, lon: 73.851, alt: 20 },
  { lat: 18.522, lon: 73.852, alt: 20 },
]
const PARAMS: MissionParams = { altitudeM: 20, frontOverlap: 0.8, sideOverlap: 0.7, speedMs: 8, headingDeg: 'auto' }

describe('toLitchiCsv', () => {
  it('emits a header and one row per waypoint', () => {
    const rows = toLitchiCsv(WPS, PARAMS, 2).split('\n')
    expect(rows[0]).toContain('latitude,longitude')
    expect(rows[0]).toContain('photo_distinterval')
    expect(rows.length).toBe(WPS.length + 1)
    expect(rows[1].startsWith('18.52,73.85,20')).toBe(true)
  })

  it('writes the trigger distance into every row', () => {
    const rows = toLitchiCsv(WPS, PARAMS, 3.5).split('\n').slice(1)
    for (const r of rows) expect(r.endsWith(',3.5')).toBe(true)
  })
})

describe('toKml', () => {
  it('produces a LineString plus one placemark per waypoint', () => {
    const kml = toKml(WPS, 'Test Park')
    expect(kml).toContain('<kml')
    expect(kml).toContain('<LineString>')
    expect(kml).toContain('73.85,18.52,20')
    expect((kml.match(/<Placemark>/g) || []).length).toBe(WPS.length + 1) // path + per-wp
  })
})

describe('toQgcPlan', () => {
  it('is valid JSON with takeoff, trigger, waypoints and RTL', () => {
    const plan = JSON.parse(toQgcPlan(WPS, 2))
    expect(plan.fileType).toBe('Plan')
    const cmds = plan.mission.items.map((i: { command: number }) => i.command)
    expect(cmds).toContain(22) // takeoff
    expect(cmds).toContain(206) // cam trigger distance
    expect(cmds).toContain(20) // RTL
    expect(cmds.filter((c: number) => c === 16).length).toBe(WPS.length - 1)
    expect(plan.mission.plannedHomePosition).toEqual([18.52, 73.85, 20])
  })

  it('returns an empty mission for no waypoints', () => {
    const plan = JSON.parse(toQgcPlan([], 2))
    expect(plan.mission.items).toEqual([])
  })
})

describe('serialiseMission', () => {
  it('maps each format to the right extension and mime type', () => {
    expect(serialiseMission(WPS, PARAMS, 'm', 2, 'litchi').ext).toBe('csv')
    expect(serialiseMission(WPS, PARAMS, 'm', 2, 'kml').mime).toContain('kml')
    expect(serialiseMission(WPS, PARAMS, 'm', 2, 'plan').ext).toBe('plan')
    expect(serialiseMission(WPS, PARAMS, 'm', 2, 'waypoints').ext).toBe('waypoints')
  })

  it('emits a QGC WPL 110 header for the .waypoints format', () => {
    const out = serialiseMission(WPS, PARAMS, 'm', 5, 'waypoints')
    expect(out.text.split('\n')[0]).toBe('QGC WPL 110')
    // home + takeoff + cam-trigger + (n-1) survey waypoints + RTL
    expect(out.text.trim().split('\n').length).toBe(1 + 3 + (WPS.length - 1) + 1)
  })
})

describe('fileSlug', () => {
  it('sanitises names and falls back to "mission"', () => {
    expect(fileSlug('PUNE_FARM_01 Grid #3')).toBe('PUNE_FARM_01_Grid_3')
    expect(fileSlug('   ')).toBe('mission')
  })
})
