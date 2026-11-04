'use client'

import { Layers, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'
import { isTerminalHttpError } from '@/lib/queryPolicy'
import {
  isOdmJobActive,
  odmCapability,
  odmProgressLabel,
  validateOdmZip,
  type OdmCapability,
  type OdmJob,
  type OdmSensor,
} from '@/lib/odm'

export type OrthoGeneratorProps = {
  parkId: string
  /** Called once a generation finishes and the new ortho is registered. */
  onOrthoReady: (orthoName: string) => void
  pollMs?: number
}

const DEFAULT_POLL_MS = 5_000
const MUTED = '#64748b'
const ACCENT = '#0ea5e9'
const DANGER = '#dc2626'

function errorText(err: unknown, fallback: string): string {
  return err instanceof ApiError || err instanceof Error ? err.message : fallback
}

/** refetchInterval for a generation job: poll while active, stop when done or gone. */
export function odmPollInterval(job: OdmJob | undefined, error: unknown, pollMs: number): number | false {
  if (isTerminalHttpError(error)) return false
  return job && isOdmJobActive(job) ? pollMs : false
}

export function OrthoGenerator({ parkId, onOrthoReady, pollMs = DEFAULT_POLL_MS }: OrthoGeneratorProps) {
  const queryClient = useQueryClient()
  const [formOpen, setFormOpen] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [sensor, setSensor] = useState<OdmSensor>('auto')
  const [resolutionCm, setResolutionCm] = useState(2)
  const [formError, setFormError] = useState<string | null>(null)
  // Job started from this form; otherwise the park's most recent job is shown.
  const [startedJob, setStartedJob] = useState<{ parkId: string; jobId: string } | null>(null)
  const onReadyRef = useRef(onOrthoReady)
  onReadyRef.current = onOrthoReady

  // Shared with Operations' health line: one /health request for both.
  const healthQuery = useQuery({ queryKey: queryKeys.ops.health, queryFn: () => api.health() })
  const capability: OdmCapability | null = healthQuery.data
    ? odmCapability(healthQuery.data)
    : healthQuery.isError
      ? { configured: false, message: 'Backend unreachable' }
      : null

  useEffect(() => {
    setFormOpen(false)
    setFormError(null)
  }, [parkId])

  // No history is not an error worth surfacing — the button still works.
  const jobsQuery = useQuery({
    queryKey: queryKeys.odm.jobs(parkId),
    queryFn: () => api.orthoGenerationJobs(parkId),
  })
  const latestJob = jobsQuery.data?.[0] ?? null
  const jobId = startedJob?.parkId === parkId ? startedJob.jobId : latestJob?.job_id ?? null

  // The tracked job lives in its own cache entry: seeded from the history list
  // or the generate/cancel response, refreshed by polling while it is active.
  const jobQuery = useQuery({
    queryKey: queryKeys.odm.job(parkId, jobId ?? ''),
    queryFn: () => api.orthoGenerationStatus(parkId, jobId as string),
    enabled: Boolean(jobId),
    initialData: () => (latestJob && latestJob.job_id === jobId ? latestJob : undefined),
    // Seeded data is fresh: the first status request waits one poll interval,
    // exactly like the old setInterval loop.
    staleTime: Infinity,
    refetchInterval: (query) => odmPollInterval(query.state.data, query.state.error, pollMs),
    refetchIntervalInBackground: true,
    retry: false,
  })
  const job = jobId ? (jobQuery.data ?? null) : null
  const activeJobId = job && isOdmJobActive(job) ? job.job_id : null

  // Report completion only for a transition seen here (active → succeeded), so
  // a job that had already finished before mount is not re-announced.
  const lastSeenRef = useRef<{ jobId: string; active: boolean } | null>(null)
  useEffect(() => {
    if (!job) return
    const last = lastSeenRef.current
    const wasActive = last?.jobId === job.job_id && last.active
    lastSeenRef.current = { jobId: job.job_id, active: isOdmJobActive(job) }
    if (wasActive && job.state === 'succeeded' && job.ortho_name) onReadyRef.current(job.ortho_name)
  }, [job])

  function track(next: OdmJob) {
    queryClient.setQueryData(queryKeys.odm.job(parkId, next.job_id), next)
    setStartedJob({ parkId, jobId: next.job_id })
    void queryClient.invalidateQueries({ queryKey: queryKeys.odm.jobs(parkId) })
  }

  const generateMutation = useMutation({
    mutationFn: (form: FormData) => api.generateOrtho(parkId, form),
    onSuccess: (next) => {
      track(next)
      setFormOpen(false)
      setFile(null)
    },
    onError: (err) => setFormError(errorText(err, 'Upload failed')),
  })

  const cancelMutation = useMutation({
    mutationFn: (id: string) => api.cancelOrthoGeneration(parkId, id),
    onSuccess: track,
    onError: (err) => setFormError(errorText(err, 'Cancel failed')),
  })

  const submitting = generateMutation.isPending

  function start() {
    const invalid = validateOdmZip(file)
    if (invalid || !file) {
      setFormError(invalid)
      return
    }
    setFormError(null)
    const form = new FormData()
    form.append('images', file)
    form.append('sensor', sensor)
    form.append('orthophoto_resolution_cm', String(resolutionCm))
    generateMutation.mutate(form)
  }

  function cancel() {
    if (job) cancelMutation.mutate(job.job_id)
  }

  const configured = capability?.configured === true
  const busy = Boolean(activeJobId) || submitting
  const pct = job ? Math.round(Math.min(Math.max(job.progress, 0), 1) * 100) : 0

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, width: '100%' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
        <button
          type="button"
          onClick={() => setFormOpen((v) => !v)}
          disabled={!configured || busy}
          title={capability && !configured ? (capability.message ?? undefined) : undefined}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            padding: '5px 14px',
            borderRadius: 6,
            fontSize: 12,
            fontWeight: 600,
            background: 'transparent',
            color: configured && !busy ? ACCENT : MUTED,
            border: '1px solid #cbd5e1',
            cursor: configured && !busy ? 'pointer' : 'not-allowed',
            opacity: configured && !busy ? 1 : 0.6,
          }}
        >
          <Layers size={14} />
          Generate orthomosaic
        </button>
        {capability && !configured && (
          <span style={{ fontSize: 12, color: MUTED }}>{capability.message}</span>
        )}
      </div>

      {formOpen && configured && (
        <div
          style={{
            display: 'flex',
            gap: 12,
            alignItems: 'flex-end',
            flexWrap: 'wrap',
            padding: 12,
            border: '1px solid #e2e8f0',
            borderRadius: 8,
          }}
        >
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: MUTED }}>
            Images ZIP
            <input
              type="file"
              accept=".zip"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              disabled={submitting}
            />
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: MUTED }}>
            Camera
            <select
              value={sensor}
              onChange={(e) => setSensor(e.target.value as OdmSensor)}
              style={{ padding: '4px 8px', border: '1px solid #cbd5e1', borderRadius: 6 }}
            >
              <option value="auto">Auto (RGB if present)</option>
              <option value="rgb">RGB</option>
              <option value="thermal">Thermal</option>
            </select>
          </label>
          <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: MUTED }}>
            Resolution (cm/px)
            <input
              type="number"
              min={0.5}
              max={50}
              step={0.5}
              value={resolutionCm}
              onChange={(e) => setResolutionCm(Number(e.target.value))}
              style={{ width: 80, padding: '4px 8px', border: '1px solid #cbd5e1', borderRadius: 6 }}
            />
          </label>
          <button
            type="button"
            onClick={start}
            disabled={submitting}
            style={{
              padding: '6px 14px',
              borderRadius: 6,
              fontSize: 12,
              fontWeight: 600,
              background: ACCENT,
              color: '#fff',
              border: 'none',
              cursor: submitting ? 'progress' : 'pointer',
            }}
          >
            {submitting ? 'Uploading…' : 'Start generation'}
          </button>
          <span style={{ fontSize: 11, color: MUTED, flexBasis: '100%' }}>
            Geotagged images from one camera, max 2 GB. Stitching runs on the NodeODM server and can
            take from minutes to hours.
          </span>
        </div>
      )}

      {formError && (
        <div role="alert" style={{ fontSize: 12, color: DANGER }}>
          {formError}
        </div>
      )}

      {job && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap', fontSize: 12 }}>
          {isOdmJobActive(job) && (
            <div
              role="progressbar"
              aria-label="Orthomosaic generation progress"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={pct}
              style={{ width: 160, height: 6, background: '#e2e8f0', borderRadius: 3, overflow: 'hidden' }}
            >
              <div style={{ width: `${pct}%`, height: '100%', background: ACCENT, transition: 'width 300ms' }} />
            </div>
          )}
          {job.state === 'failed' ? (
            <span role="alert" style={{ color: DANGER }}>
              {odmProgressLabel(job)}
            </span>
          ) : (
            <span style={{ color: job.state === 'succeeded' ? '#16a34a' : MUTED }}>{odmProgressLabel(job)}</span>
          )}
          {isOdmJobActive(job) && (
            <button
              type="button"
              onClick={cancel}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: 4,
                padding: '3px 10px',
                borderRadius: 6,
                fontSize: 12,
                background: 'transparent',
                color: DANGER,
                border: `1px solid ${DANGER}`,
                cursor: 'pointer',
              }}
            >
              <X size={12} />
              Cancel
            </button>
          )}
        </div>
      )}
    </div>
  )
}
