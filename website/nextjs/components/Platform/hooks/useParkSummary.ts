'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'

export type InspectionRef = { id: string; flight_date?: string | null; created_at?: string | null }

const NO_INSPECTIONS: InspectionRef[] = []

/** The `inspections` array of a park summary, or [] when absent/malformed. */
export function inspectionsOf(summary: unknown): InspectionRef[] {
  const list = (summary as { inspections?: unknown } | null | undefined)?.inspections
  return Array.isArray(list) ? (list as InspectionRef[]) : NO_INSPECTIONS
}

/**
 * GET /park/{id}. History, Diff and Park Map all read it, so they share one
 * cache entry per park. Disabled until a park is chosen.
 */
export function useParkSummary(parkId: string) {
  return useQuery({
    queryKey: queryKeys.parks.summary(parkId),
    queryFn: () => api.park(parkId),
    enabled: Boolean(parkId),
  })
}
