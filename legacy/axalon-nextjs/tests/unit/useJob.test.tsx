import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, test, vi } from 'vitest'

import { applyJobStatus, jobPollInterval, useJob, type BatchJob } from '@/components/Platform/hooks/useJob'
import { api, ApiError, type JobStatus } from '@/lib/api'
import { withQueryClient } from './queryWrapper'

afterEach(() => {
  vi.restoreAllMocks()
})

const job = (overrides: Partial<BatchJob> = {}): BatchJob => ({
  id: 'job-1',
  parkId: 'P1',
  fileName: 'flight.zip',
  status: 'queued',
  progress: 0,
  processed: 0,
  total: 0,
  altitude: 40,
  createdAt: '10:00',
  detections: { critical: 0, high: 0, medium: 0, low: 0 },
  ...overrides,
})

const status = (overrides: Partial<JobStatus> = {}): JobStatus =>
  ({ job_id: 'job-1', state: 'running', ...overrides }) as JobStatus

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

describe('applyJobStatus', () => {
  test('maps API states onto queue states', () => {
    expect(applyJobStatus(job(), status({ state: 'queued' })).status).toBe('queued')
    expect(applyJobStatus(job(), status({ state: 'running' })).status).toBe('processing')
    expect(applyJobStatus(job(), status({ state: 'succeeded' })).status).toBe('completed')
    expect(applyJobStatus(job(), status({ state: 'failed' })).status).toBe('failed')
  })

  test('keeps known values when the response omits them', () => {
    const base = job({ status: 'processing', progress: 0.4, processed: 4, total: 10, error: 'old' })
    expect(applyJobStatus(base, status({ state: 'weird' }))).toMatchObject({
      status: 'processing',
      progress: 0.4,
      processed: 4,
      total: 10,
      error: 'old',
    })
    expect(applyJobStatus(base, status({ progress: 0.9, processed: 9, total: 10, message: 'nearly' }))).toMatchObject({
      progress: 0.9,
      processed: 9,
      error: 'nearly',
    })
  })
})

describe('jobPollInterval', () => {
  test('polls until the job reaches a final state', () => {
    expect(jobPollInterval(undefined, null, 1800)).toBe(1800)
    expect(jobPollInterval(status({ state: 'running' }), null, 1800)).toBe(1800)
    expect(jobPollInterval(status({ state: 'succeeded' }), null, 1800)).toBe(false)
    expect(jobPollInterval(status({ state: 'failed' }), null, 1800)).toBe(false)
  })

  test('keeps polling through transient errors but stops on auth/not-found', () => {
    expect(jobPollInterval(undefined, new ApiError(0, ''), 1800)).toBe(1800)
    expect(jobPollInterval(undefined, new ApiError(503, ''), 1800)).toBe(1800)
    expect(jobPollInterval(undefined, new ApiError(401, ''), 1800)).toBe(false)
    expect(jobPollInterval(undefined, new ApiError(404, ''), 1800)).toBe(false)
  })
})

describe('useJob', () => {
  test('never polls the seeded demo job', async () => {
    const spy = vi.spyOn(api, 'status')
    const { result } = renderHook(() => useJob(10), { wrapper: withQueryClient() })
    await sleep(50)
    expect(result.current.jobs).toHaveLength(1)
    expect(spy).not.toHaveBeenCalled()
  })

  test('polls an added job, reflects progress, and stops once it completes', async () => {
    const spy = vi
      .spyOn(api, 'status')
      .mockResolvedValueOnce(status({ state: 'running', progress: 0.5, processed: 5, total: 10 }))
      .mockResolvedValue(status({ state: 'succeeded', progress: 1, processed: 10, total: 10 }))
    const { result } = renderHook(() => useJob(10), { wrapper: withQueryClient() })

    act(() => result.current.addJob(job()))
    expect(result.current.activeJobId).toBe('job-1')

    await waitFor(() => expect(result.current.activeJob.status).toBe('completed'))
    expect(result.current.activeJob.progress).toBe(1)
    const calls = spy.mock.calls.length
    await sleep(80)
    expect(spy.mock.calls.length).toBe(calls)
  })

  test('stops polling when the session is no longer authorised', async () => {
    const spy = vi.spyOn(api, 'status').mockRejectedValue(new ApiError(401, ''))
    const { result } = renderHook(() => useJob(10), { wrapper: withQueryClient() })

    act(() => result.current.addJob(job()))
    await waitFor(() => expect(spy).toHaveBeenCalled())
    await sleep(80)
    expect(spy).toHaveBeenCalledTimes(1)
    expect(result.current.activeJob.status).toBe('queued')
  })
})
