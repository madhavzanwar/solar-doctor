import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { useSettings } from '@/components/Platform/hooks/useSettings'
import { api, ApiError } from '@/lib/api'
import { withQueryClient } from './queryWrapper'

afterEach(() => {
  vi.restoreAllMocks()
})

const BLOB = { detector: { confidence: 0.25, device: 'cpu' } }

describe('useSettings', () => {
  test('loads settings from either response shape', async () => {
    vi.spyOn(api, 'getSettings').mockResolvedValue({ settings: BLOB })
    const { result } = renderHook(() => useSettings(), { wrapper: withQueryClient() })

    await waitFor(() => expect(result.current.settings).toEqual(BLOB))
    expect(result.current.dirty).toBe(false)
    expect(result.current.loading).toBe(false)
  })

  test('edits are local until saved, then saved and refetched', async () => {
    const get = vi
      .spyOn(api, 'getSettings')
      .mockResolvedValueOnce(BLOB)
      .mockResolvedValue({ detector: { confidence: 0.4, device: 'cpu' } })
    const put = vi.spyOn(api, 'putSettings').mockResolvedValue({})
    const { result } = renderHook(() => useSettings(), { wrapper: withQueryClient() })
    await waitFor(() => expect(result.current.settings).toEqual(BLOB))

    act(() => result.current.update('detector', 'confidence', 0.4))
    expect(result.current.dirty).toBe(true)
    expect(result.current.settings?.detector.confidence).toBe(0.4)
    expect(put).not.toHaveBeenCalled()

    await act(async () => {
      await result.current.save()
    })
    expect(put).toHaveBeenCalledWith({ detector: { confidence: 0.4, device: 'cpu' } })
    expect(result.current.dirty).toBe(false)
    expect(result.current.message).toMatch(/^Saved/)
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2))
    expect(result.current.settings?.detector.confidence).toBe(0.4)
  })

  test('a failed save keeps the edits and reports the error', async () => {
    vi.spyOn(api, 'getSettings').mockResolvedValue(BLOB)
    vi.spyOn(api, 'putSettings').mockRejectedValue(new ApiError(403, '', 'Admin only'))
    const { result } = renderHook(() => useSettings(), { wrapper: withQueryClient() })
    await waitFor(() => expect(result.current.settings).toEqual(BLOB))

    act(() => result.current.update('detector', 'device', 'cuda'))
    await act(async () => {
      await result.current.save()
    })
    expect(result.current.dirty).toBe(true)
    expect(result.current.message).toBe('Admin only')
    expect(result.current.settings?.detector.device).toBe('cuda')
  })

  test('surfaces a load failure as the status message', async () => {
    vi.spyOn(api, 'getSettings').mockRejectedValue(new ApiError(500, '', 'Server exploded'))
    const { result } = renderHook(() => useSettings(), { wrapper: withQueryClient() })

    await waitFor(() => expect(result.current.message).toBe('Server exploded'))
    expect(result.current.settings).toBeNull()
  })

  test('reload discards unsaved edits', async () => {
    const get = vi.spyOn(api, 'getSettings').mockResolvedValue(BLOB)
    const { result } = renderHook(() => useSettings(), { wrapper: withQueryClient() })
    await waitFor(() => expect(result.current.settings).toEqual(BLOB))

    act(() => result.current.update('detector', 'device', 'cuda'))
    act(() => result.current.load())
    await waitFor(() => expect(result.current.dirty).toBe(false))
    expect(result.current.settings).toEqual(BLOB)
    await waitFor(() => expect(get).toHaveBeenCalledTimes(2))
  })
})
