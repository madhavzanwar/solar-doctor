import { afterEach, describe, expect, test, vi } from 'vitest'
import { api } from '@/lib/api'
import {
  MAX_ODM_ZIP_BYTES,
  isOdmJobActive,
  odmCapability,
  odmProgressLabel,
  validateOdmZip,
  type OdmJob,
} from '@/lib/odm'

afterEach(() => {
  vi.restoreAllMocks()
})

const job = (overrides: Partial<OdmJob> = {}): OdmJob => ({
  job_id: 'odm-abc',
  park_id: 'P1',
  state: 'running',
  progress: 0.42,
  stage: 'Processing on NodeODM (40%)',
  error: null,
  message: 'Processing on NodeODM (40%)',
  ortho_name: null,
  ...overrides,
})

describe('odmCapability', () => {
  test('reads the capability flag from /health', () => {
    expect(
      odmCapability({ status: 'ok', capabilities: { odm: { configured: true, message: null } } }),
    ).toEqual({ configured: true, message: null })
  })

  test('treats an older backend without the flag as not configured', () => {
    const cap = odmCapability({ status: 'ok' })
    expect(cap.configured).toBe(false)
    expect(cap.message).toMatch(/not support/i)
  })

  test('passes the backend explanation through when disabled', () => {
    const cap = odmCapability({
      status: 'ok',
      capabilities: { odm: { configured: false, message: 'set AXALON_NODEODM_URL' } },
    })
    expect(cap).toEqual({ configured: false, message: 'set AXALON_NODEODM_URL' })
  })
})

describe('job helpers', () => {
  test('queued and running jobs are active; terminal ones are not', () => {
    expect(isOdmJobActive(job({ state: 'queued' }))).toBe(true)
    expect(isOdmJobActive(job({ state: 'running' }))).toBe(true)
    for (const state of ['succeeded', 'failed', 'cancelled'] as const) {
      expect(isOdmJobActive(job({ state }))).toBe(false)
    }
  })

  test('progress label combines stage and percent', () => {
    expect(odmProgressLabel(job())).toBe('Processing on NodeODM (40%) — 42%')
    expect(odmProgressLabel(job({ state: 'succeeded', progress: 1 }))).toBe('Completed')
    expect(odmProgressLabel(job({ state: 'failed', error: 'boom' }))).toBe('Failed: boom')
    expect(odmProgressLabel(job({ state: 'cancelled' }))).toBe('Cancelled')
  })
})

describe('validateOdmZip', () => {
  test('requires a file', () => {
    expect(validateOdmZip(null)).toMatch(/choose/i)
  })
  test('rejects non-zip files', () => {
    expect(validateOdmZip({ name: 'flight.tar', size: 10 })).toMatch(/\.zip/)
  })
  test('rejects archives over the backend limit', () => {
    expect(validateOdmZip({ name: 'f.zip', size: MAX_ODM_ZIP_BYTES + 1 })).toMatch(/2 GB/)
  })
  test('accepts a reasonable zip', () => {
    expect(validateOdmZip({ name: 'Flight.ZIP', size: 1024 })).toBeNull()
  })
})

describe('api ortho generation endpoints', () => {
  test('generateOrtho posts multipart form to the park endpoint', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify(job({ state: 'queued' })), { status: 202 }))
    const form = new FormData()
    const result = await api.generateOrtho('PARK A', form)
    const [url, init] = fetchSpy.mock.calls[0]
    expect(url).toMatch(/\/parks\/PARK%20A\/orthos\/generate$/)
    expect((init as RequestInit).method).toBe('POST')
    expect((init as RequestInit).body).toBe(form)
    expect(result.state).toBe('queued')
  })

  test('cancelOrthoGeneration sends DELETE for the job', async () => {
    const fetchSpy = vi
      .spyOn(globalThis, 'fetch')
      .mockResolvedValueOnce(new Response(JSON.stringify(job({ state: 'cancelled' })), { status: 200 }))
    await api.cancelOrthoGeneration('P1', 'odm-abc')
    const [url, init] = fetchSpy.mock.calls[0]
    expect(url).toMatch(/\/parks\/P1\/orthos\/generate\/odm-abc$/)
    expect((init as RequestInit).method).toBe('DELETE')
  })

  test('orthoGenerationJobs unwraps the jobs list', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ park_id: 'P1', jobs: [job()] }), { status: 200 }),
    )
    const jobs = await api.orthoGenerationJobs('P1')
    expect(jobs.map((j) => j.job_id)).toEqual(['odm-abc'])
  })
})
