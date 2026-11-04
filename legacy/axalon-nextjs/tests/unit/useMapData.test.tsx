import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { useMapData } from '@/components/Platform/AnomalyMap'
import { withQueryClient } from './queryWrapper'

afterEach(() => {
  vi.restoreAllMocks()
})

const REAL = {
  job_id: 'job-1',
  park_id: 'P1',
  flight_date: '2026-09-01',
  total_images: 2,
  total_anomalies: 1,
  summary: { CRITICAL: 1, HIGH: 0, MEDIUM: 0, LOW: 0 },
  bounds: null,
  synthetic: false,
  images: [],
  anomalies: [],
}

function mockFetch(response: Response | Error) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async () => {
    if (response instanceof Error) throw response
    return response.clone()
  })
}

describe('useMapData', () => {
  test('shows demo data without calling the API while the job is still running', async () => {
    const fetchSpy = mockFetch(new Response(JSON.stringify(REAL)))
    const { result } = renderHook(() => useMapData('http://api', 'job-1', 'processing'), {
      wrapper: withQueryClient(),
    })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data?.synthetic).toBe(true)
    expect(result.current.data?.job_id).toBe('job-1')
    expect(fetchSpy).not.toHaveBeenCalled()
  })

  test('loads the real map once the job completes', async () => {
    const fetchSpy = mockFetch(new Response(JSON.stringify(REAL)))
    const { result } = renderHook(() => useMapData('http://api', 'job-1', 'completed'), {
      wrapper: withQueryClient(),
    })

    await waitFor(() => expect(result.current.data?.synthetic).toBe(false))
    expect(result.current.loading).toBe(false)
    expect(result.current.error).toBeNull()
    expect(String(fetchSpy.mock.calls[0][0])).toContain('http://api/map/job-1')
  })

  test('falls back to demo data for an empty inspection', async () => {
    mockFetch(new Response(JSON.stringify({ ...REAL, total_images: 0, total_anomalies: 0 })))
    const { result } = renderHook(() => useMapData('http://api', 'job-1', 'completed'), {
      wrapper: withQueryClient(),
    })

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data?.synthetic).toBe(true)
  })

  test('falls back to demo data and reports the error when the API fails', async () => {
    const fetchSpy = mockFetch(new Response('nope', { status: 500 }))
    const { result } = renderHook(() => useMapData('http://api', 'job-1', 'completed'), {
      wrapper: withQueryClient(),
    })

    await waitFor(() => expect(result.current.error).toBe('API returned 500'))
    expect(result.current.data?.synthetic).toBe(true)
    expect(result.current.loading).toBe(false)
    expect(fetchSpy).toHaveBeenCalledTimes(1)
  })
})
