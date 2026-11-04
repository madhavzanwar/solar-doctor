/**
 * In-platform orthomosaic generation (NodeODM) — shared types and pure helpers.
 *
 * Mirrors platform/api/support/odm_jobs.py::serialize_odm_job and the
 * `capabilities.odm` flag on GET /health.
 */
import type { Health } from '@/lib/api'

export type OdmJobState = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled'

export type OdmJob = {
  job_id: string
  park_id: string | null
  state: OdmJobState
  /** 0–1 */
  progress: number
  stage: string | null
  error: string | null
  message: string | null
  ortho_name: string | null
  created_at?: string | null
  updated_at?: string | null
}

export type OdmSensor = 'auto' | 'rgb' | 'thermal'

export type OdmCapability = { configured: boolean; message: string | null }

/** Matches the backend's _MAX_ZIP_BYTES — fail before a multi-GB upload, not after. */
export const MAX_ODM_ZIP_BYTES = 2 * 1024 * 1024 * 1024

const OLD_BACKEND_MESSAGE =
  'This backend does not support orthomosaic generation yet — update the API.'

export function odmCapability(health: Health | null | undefined): OdmCapability {
  const caps = (health as { capabilities?: { odm?: Partial<OdmCapability> } } | null)?.capabilities
  const odm = caps?.odm
  if (!odm || typeof odm.configured !== 'boolean') {
    return { configured: false, message: OLD_BACKEND_MESSAGE }
  }
  return { configured: odm.configured, message: odm.message ?? null }
}

export function isOdmJobActive(job: Pick<OdmJob, 'state'>): boolean {
  return job.state === 'queued' || job.state === 'running'
}

export function odmProgressLabel(job: OdmJob): string {
  switch (job.state) {
    case 'succeeded':
      return 'Completed'
    case 'failed':
      return `Failed: ${job.error ?? 'unknown error'}`
    case 'cancelled':
      return 'Cancelled'
    default: {
      const pct = Math.round(Math.min(Math.max(job.progress, 0), 1) * 100)
      return `${job.stage ?? 'Queued'} — ${pct}%`
    }
  }
}

/** Returns an error message, or null when the file can be submitted. */
export function validateOdmZip(file: { name: string; size: number } | null | undefined): string | null {
  if (!file) return 'Choose a .zip of geotagged drone images'
  if (!file.name.toLowerCase().endsWith('.zip')) return 'Only .zip archives can be submitted'
  if (file.size > MAX_ODM_ZIP_BYTES) return 'ZIP archive exceeds the 2 GB upload limit'
  return null
}
