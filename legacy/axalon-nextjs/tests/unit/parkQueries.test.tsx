import '@testing-library/jest-dom/vitest'
import { fireEvent, render, renderHook, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { ParkLayoutControl } from '@/components/Platform/ParkLayoutControl'
import { normalizeParks, useParks } from '@/components/Platform/hooks/useParks'
import { inspectionsOf } from '@/components/Platform/hooks/useParkSummary'
import { api } from '@/lib/api'
import type { ParkLayoutStatus } from '@/lib/parkLayout'
import { makeQueryClient, withQueryClient } from './queryWrapper'

afterEach(() => {
  vi.restoreAllMocks()
})

const AUTO: ParkLayoutStatus = { park_id: 'P1', mode: 'auto', summary: null, error: null }
const MANUAL: ParkLayoutStatus = {
  park_id: 'P1',
  mode: 'manual',
  summary: {
    park_id: 'P1',
    name: null,
    tables: 3,
    total_panels: 120,
    match_tolerance_m: 1,
    source_format: 'layout',
  },
  error: null,
}

describe('park list', () => {
  test('normalizes both response shapes', () => {
    expect(normalizeParks([{ id: 'A' }])).toEqual([{ id: 'A' }])
    expect(normalizeParks({ parks: [{ id: 'B' }] })).toEqual([{ id: 'B' }])
    expect(normalizeParks(null)).toEqual([])
  })

  test('tabs mounting useParks together share one request', async () => {
    const parks = vi.spyOn(api, 'parks').mockResolvedValue([{ id: 'A' }])
    const wrapper = withQueryClient(makeQueryClient())
    const first = renderHook(() => useParks(), { wrapper })
    const second = renderHook(() => useParks(), { wrapper })

    await waitFor(() => expect(first.result.current.parks).toEqual([{ id: 'A' }]))
    await waitFor(() => expect(second.result.current.loading).toBe(false))
    expect(parks).toHaveBeenCalledTimes(1)
  })

  test('inspectionsOf tolerates summaries without an inspection list', () => {
    expect(inspectionsOf({ inspections: [{ id: 'i1' }] })).toEqual([{ id: 'i1' }])
    expect(inspectionsOf({})).toEqual([])
    expect(inspectionsOf(undefined)).toEqual([])
  })
})

describe('ParkLayoutControl', () => {
  test('an upload shows the new layout at once and refetches the status', async () => {
    const statusSpy = vi.spyOn(api, 'parkLayout').mockResolvedValueOnce(AUTO).mockResolvedValue(MANUAL)
    vi.spyOn(api, 'uploadParkLayout').mockResolvedValue(MANUAL)
    render(<ParkLayoutControl parkId="P1" />, { wrapper: withQueryClient() })

    expect(await screen.findByText('Auto-grid')).toBeInTheDocument()
    const input = screen.getByTestId('parkmap-layout-control').querySelector('input[type=file]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [new File(['{}'], 'layout.json')] } })

    expect(await screen.findByText(/Manual · 120 panels/)).toBeInTheDocument()
    await waitFor(() => expect(statusSpy).toHaveBeenCalledTimes(2))
  })

  test('reverting to auto-grid clears the manual badge', async () => {
    vi.spyOn(api, 'parkLayout').mockResolvedValueOnce(MANUAL).mockResolvedValue(AUTO)
    const revert = vi.spyOn(api, 'deleteParkLayout').mockResolvedValue(AUTO)
    vi.spyOn(window, 'confirm').mockReturnValue(true)
    render(<ParkLayoutControl parkId="P1" />, { wrapper: withQueryClient() })

    fireEvent.click(await screen.findByRole('button', { name: /use auto-grid/i }))
    expect(await screen.findByText('Auto-grid')).toBeInTheDocument()
    expect(revert).toHaveBeenCalledWith('P1')
  })

  test('rejects a non-layout file without calling the API', async () => {
    vi.spyOn(api, 'parkLayout').mockResolvedValue(AUTO)
    const upload = vi.spyOn(api, 'uploadParkLayout')
    render(<ParkLayoutControl parkId="P1" />, { wrapper: withQueryClient() })

    await screen.findByText('Auto-grid')
    const input = screen.getByTestId('parkmap-layout-control').querySelector('input[type=file]') as HTMLInputElement
    fireEvent.change(input, { target: { files: [new File(['x'], 'layout.csv')] } })
    expect(await screen.findByText(/must be a .json layout/)).toBeInTheDocument()
    expect(upload).not.toHaveBeenCalled()
  })
})
