// website/nextjs/lib/analytics.ts
// Portfolio aggregation across parks for the Analytics Overview dashboard. Pure + tested.
import type { ParkRef, TrendPoint } from './api'

export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
export type ParkTrendBundle = { park: ParkRef; trend: TrendPoint[] }

export type RankedPark = { id: string; name: string; critical: number; total: number }
export type PortfolioSummary = {
  parkCount: number
  inspectionCount: number
  bySeverity: Record<Severity, number>
  totalFaults: number
  ranked: RankedPark[]
  worstParkId: string | null
}

export const SEVERITIES: Severity[] = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']

// Each park's "current" fault counts = its latest trend point. Sum across parks
// for portfolio totals; rank parks by CRITICAL (then total).
export function aggregatePortfolio(bundles: ParkTrendBundle[]): PortfolioSummary {
  const bySeverity: Record<Severity, number> = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0 }
  let inspectionCount = 0
  const ranked: RankedPark[] = []

  for (const { park, trend } of bundles) {
    inspectionCount += trend.length
    const latest = trend.length ? trend[trend.length - 1] : null
    const counts: Record<Severity, number> = {
      CRITICAL: latest?.CRITICAL ?? 0,
      HIGH: latest?.HIGH ?? 0,
      MEDIUM: latest?.MEDIUM ?? 0,
      LOW: latest?.LOW ?? 0,
    }
    for (const s of SEVERITIES) bySeverity[s] += counts[s]
    const total = SEVERITIES.reduce((n, s) => n + counts[s], 0)
    ranked.push({ id: park.id, name: park.name ?? park.id, critical: counts.CRITICAL, total })
  }

  ranked.sort((a, b) => b.critical - a.critical || b.total - a.total)
  const totalFaults = SEVERITIES.reduce((n, s) => n + bySeverity[s], 0)

  return {
    parkCount: bundles.length,
    inspectionCount,
    bySeverity,
    totalFaults,
    ranked,
    worstParkId: ranked[0]?.id ?? null,
  }
}
