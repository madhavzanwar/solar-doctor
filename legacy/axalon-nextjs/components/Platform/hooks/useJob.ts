'use client'

import { useCallback, useMemo, useState } from 'react'
import { useQueries } from '@tanstack/react-query'
import { api, type JobStatus as ApiJobStatus } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'
import { isTerminalHttpError } from '@/lib/queryPolicy'

export type JobStatus = 'queued' | 'processing' | 'completed' | 'failed'
export type Severity = 'critical' | 'high' | 'medium' | 'low'

export type BatchJob = {
  id: string
  parkId: string
  fileName: string
  status: JobStatus
  progress: number
  processed: number
  total: number
  altitude: number
  createdAt: string
  detections: Record<Severity, number>
  error?: string
}

const DEMO_JOB_ID = 'batch-8f24c91a'
const JOB_POLL_MS = 1800

const INITIAL_JOBS: BatchJob[] = [
  {
    id: DEMO_JOB_ID,
    parkId: 'MH_SOLAR_07',
    fileName: 'mh_solar_07_morning_pass.zip',
    status: 'processing',
    progress: 0.64,
    processed: 896,
    total: 1400,
    altitude: 42,
    createdAt: '09:42',
    detections: { critical: 7, high: 18, medium: 42, low: 31 },
  },
]

/** Fold a /status response into a queue entry, keeping known values the response omits. */
export function applyJobStatus(job: BatchJob, res: ApiJobStatus): BatchJob {
  let status: JobStatus = job.status
  if (res.state === 'queued') status = 'queued'
  else if (res.state === 'running') status = 'processing'
  else if (res.state === 'succeeded') status = 'completed'
  else if (res.state === 'failed') status = 'failed'

  return {
    ...job,
    status,
    progress: res.progress != null ? res.progress : job.progress,
    processed: res.processed != null ? res.processed : job.processed,
    total: res.total != null ? res.total : job.total,
    error: res.message ?? job.error,
  }
}

/**
 * refetchInterval for a job's status query: keep polling while the job is in
 * flight (transient failures included), stop once it succeeded/failed or the
 * server says the session or job is gone.
 */
export function jobPollInterval(
  data: ApiJobStatus | undefined,
  error: unknown,
  pollMs: number,
): number | false {
  if (isTerminalHttpError(error)) return false
  if (data && (data.state === 'succeeded' || data.state === 'failed')) return false
  return pollMs
}

export function useJob(pollMs: number = JOB_POLL_MS): {
  jobs: BatchJob[]
  activeJob: BatchJob
  activeJobId: string
  setActiveJobId: (id: string) => void
  addJob: (job: BatchJob) => void
} {
  const [baseJobs, setBaseJobs] = useState<BatchJob[]>(INITIAL_JOBS)
  const [activeJobId, setActiveJobId] = useState<string>(DEMO_JOB_ID)

  const addJob = useCallback((job: BatchJob) => {
    setBaseJobs((prev) => [job, ...prev])
    setActiveJobId(job.id)
  }, [])

  // One status query per real job. The demo job is seeded locally and never
  // hits the API. Background tabs keep polling, as the old setInterval did.
  const realJobs = baseJobs.filter((j) => j.id !== DEMO_JOB_ID)
  const statuses = useQueries({
    queries: realJobs.map((job) => ({
      queryKey: queryKeys.jobs.status(job.id),
      queryFn: () => api.status(job.id),
      refetchInterval: (query: { state: { data: ApiJobStatus | undefined; error: unknown } }) =>
        jobPollInterval(query.state.data, query.state.error, pollMs),
      refetchIntervalInBackground: true,
      retry: false,
    })),
  })

  const statusData = statuses.map((s) => s.data)
  const jobs = useMemo(() => {
    const byId = new Map<string, ApiJobStatus>()
    realJobs.forEach((job, i) => {
      const data = statusData[i]
      if (data) byId.set(job.id, data)
    })
    return baseJobs.map((job) => {
      const data = byId.get(job.id)
      return data ? applyJobStatus(job, data) : job
    })
  }, [baseJobs, ...statusData]) // eslint-disable-line react-hooks/exhaustive-deps

  const activeJob = jobs.find((j) => j.id === activeJobId) ?? jobs[0]

  return {
    jobs,
    activeJob,
    activeJobId,
    setActiveJobId,
    addJob,
  }
}
