'use client'

import { useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'
import { useErrorToast } from '@/components/Platform/hooks/useErrorToast'

export type ParkRef = { id: string; name?: string }

const NO_PARKS: ParkRef[] = []

/** Normalize: the API has returned both ParkRef[] and { parks: ParkRef[] }. */
export function normalizeParks(raw: unknown): ParkRef[] {
  if (Array.isArray(raw)) return raw as ParkRef[]
  if (raw && typeof raw === 'object' && 'parks' in raw) {
    return (raw as { parks: ParkRef[] }).parks ?? []
  }
  return []
}

/** Park list shared by every tab — one request, however many tabs mount it. */
export function useParks(): { parks: ParkRef[]; loading: boolean } {
  const query = useQuery({
    queryKey: queryKeys.parks.list,
    queryFn: async () => normalizeParks(await api.parks()),
  })
  useErrorToast(query.error)
  return { parks: query.data ?? NO_PARKS, loading: query.isPending }
}
