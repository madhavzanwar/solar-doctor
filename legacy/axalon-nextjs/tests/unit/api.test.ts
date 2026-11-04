import { afterEach, describe, expect, test, vi } from 'vitest'
import { api, ApiError } from '@/lib/api'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('api client', () => {
  test('health returns parsed JSON on 200', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ status: 'ok' }), { status: 200 })
    )
    const h = await api.health()
    expect(h.status).toBe('ok')
  })

  test('throws ApiError with status + body on 500', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response('boom', { status: 500 })
    )
    await expect(api.health()).rejects.toMatchObject({
      name: 'ApiError',
      status: 500,
    })
  })

  test('throws ApiError with truncated body in message', async () => {
    const long = 'x'.repeat(500)
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(long, { status: 400 })
    )
    let caught: unknown
    try {
      await api.health()
    } catch (e) {
      caught = e
    }
    expect(caught).toBeInstanceOf(ApiError)
    expect((caught as ApiError).message).toMatch(/HTTP 400/)
    // body slice in message should not exceed 200 chars (per ApiError impl)
    expect((caught as ApiError).message.length).toBeLessThan(260)
  })

  test('network error becomes ApiError with status 0', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new TypeError('fetch failed'))
    await expect(api.health()).rejects.toMatchObject({
      name: 'ApiError',
      status: 0,
    })
  })

  test('parkGrid encodes query string when inspectionId provided', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(
        JSON.stringify({ park_id: 'P1', inspection_id: 'b1', rows: 1, cols: 1, panels: [] }),
        { status: 200 }
      )
    )
    await api.parkGrid('PARK A', 'batch-zz')
    const calledUrl = (fetchSpy.mock.calls[0][0] as string)
    expect(calledUrl).toContain('/park/PARK%20A/grid')
    expect(calledUrl).toContain('inspection_id=batch-zz')
  })

  test('testAlert POSTs /alerts/test and returns per-channel results', async () => {
    const body = {
      configured: true,
      min_severity: 'CRITICAL',
      channels: {
        webhook: { status: 'sent', detail: 'HTTP 200' },
        email: { status: 'not_configured', detail: '' },
      },
    }
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(body), { status: 200 })
    )
    const res = await api.testAlert()
    expect(fetchSpy.mock.calls[0][0] as string).toContain('/alerts/test')
    expect((fetchSpy.mock.calls[0][1] as RequestInit).method).toBe('POST')
    expect(res.channels.webhook.status).toBe('sent')
    expect(res.configured).toBe(true)
  })
})
