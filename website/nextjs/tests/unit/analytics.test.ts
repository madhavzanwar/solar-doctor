import { describe, it, expect } from 'vitest'
import { aggregatePortfolio } from '@/lib/analytics'
import type { TrendPoint } from '@/lib/api'

const tp = (c: number, h: number, m: number, l: number): TrendPoint => ({
  inspection_id: 'x', date: null, CRITICAL: c, HIGH: h, MEDIUM: m, LOW: l,
})

describe('aggregatePortfolio', () => {
  it('sums each park\'s latest severity and ranks by critical', () => {
    const r = aggregatePortfolio([
      { park: { id: 'a', name: 'Alpha' }, trend: [tp(1, 0, 0, 0), tp(3, 2, 1, 0)] },
      { park: { id: 'b', name: 'Beta' }, trend: [tp(5, 0, 0, 0)] },
      { park: { id: 'c' }, trend: [] },
    ])
    expect(r.parkCount).toBe(3)
    expect(r.inspectionCount).toBe(3) // 2 + 1 + 0
    expect(r.bySeverity.CRITICAL).toBe(8) // latest a=3, b=5, c=0
    expect(r.bySeverity.MEDIUM).toBe(1)
    expect(r.totalFaults).toBe(6 + 5) // a(3+2+1)=6, b=5
    expect(r.ranked[0].id).toBe('b') // 5 > 3 critical
    expect(r.worstParkId).toBe('b')
  })

  it('handles empty input', () => {
    const r = aggregatePortfolio([])
    expect(r.parkCount).toBe(0)
    expect(r.totalFaults).toBe(0)
    expect(r.worstParkId).toBeNull()
  })
})
