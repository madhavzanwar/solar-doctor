import { describe, it, expect } from 'vitest'
import { faultsFromMapData, planReinspection, type FaultPoint } from '@/lib/reinspect'

describe('faultsFromMapData', () => {
  it('extracts from an { anomalies } payload', () => {
    const f = faultsFromMapData({ anomalies: [{ lat: 1, lon: 2, severity: 'CRITICAL' }, { lat: 3, lon: 4, severity: 'high' }] })
    expect(f).toHaveLength(2)
    expect(f[0]).toEqual({ lat: 1, lon: 2, severity: 'CRITICAL' })
    expect(f[1].severity).toBe('HIGH')
  })

  it('extracts from GeoJSON features (lon,lat order)', () => {
    const f = faultsFromMapData({ features: [{ geometry: { coordinates: [73.8, 18.5] }, properties: { severity: 'MEDIUM' } }] })
    expect(f[0]).toEqual({ lat: 18.5, lon: 73.8, severity: 'MEDIUM' })
  })

  it('drops entries without finite coords', () => {
    expect(faultsFromMapData({ anomalies: [{ lat: 'x', lon: 2 }] })).toHaveLength(0)
  })
})

describe('planReinspection', () => {
  const faults: FaultPoint[] = [
    { lat: 18.5, lon: 73.8, severity: 'CRITICAL' },
    { lat: 18.52, lon: 73.8, severity: 'CRITICAL' }, // far
    { lat: 18.5001, lon: 73.8, severity: 'MEDIUM' }, // near the first
  ]

  it('filters by minimum severity', () => {
    const wps = planReinspection(faults, { altitudeM: 30, minSeverity: 'HIGH' })
    expect(wps).toHaveLength(2) // only the two CRITICALs
    for (const w of wps) expect(w.alt).toBe(30)
  })

  it('orders by nearest-neighbour and assigns headings', () => {
    const wps = planReinspection(faults, { altitudeM: 30, minSeverity: 'LOW' })
    expect(wps).toHaveLength(3)
    // from the first point, the nearest is the MEDIUM at 18.5001, then the far one
    expect(wps[1].lat).toBeCloseTo(18.5001, 4)
    expect(wps[2].lat).toBeCloseTo(18.52, 4)
    expect(typeof wps[0].heading).toBe('number')
  })

  it('returns empty when nothing meets the threshold', () => {
    expect(planReinspection([{ lat: 1, lon: 1, severity: 'LOW' }], { altitudeM: 30, minSeverity: 'CRITICAL' })).toHaveLength(0)
  })
})
