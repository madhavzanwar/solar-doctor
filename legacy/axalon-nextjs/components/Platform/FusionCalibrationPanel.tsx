'use client'

import { Crosshair, UploadCloud } from 'lucide-react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useToast } from '@/components/Platform/Toast'
import { api, ApiError } from '@/lib/api'
import { queryKeys } from '@/lib/queryKeys'
import { calibrationSourceLabel, rmsTone } from '@/lib/calibration'
import type { CalibrationStatus } from '@/lib/calibration'

function errorText(err: unknown): string {
  return err instanceof Error ? err.message : String(err)
}

function formatSize(size?: [number, number]): string {
  return size ? `${size[0]}×${size[1]}` : '—'
}

/** Thermal↔RGB rig calibration: current summary + upload of scripts/calibrate_fusion.py output. */
export function FusionCalibrationPanel() {
  const toast = useToast()
  const queryClient = useQueryClient()

  const statusQuery = useQuery({
    queryKey: queryKeys.settings.fusionCalibration,
    queryFn: () => api.fusionCalibration(),
  })
  const status: CalibrationStatus | null = statusQuery.data ?? null
  const loadError = statusQuery.error && !status ? errorText(statusQuery.error) : ''

  const uploadMutation = useMutation({
    mutationFn: (form: FormData) => api.uploadFusionCalibration(form),
    onSuccess: (res) => {
      // The response carries the now-active status; show it, then reconcile.
      queryClient.setQueryData(queryKeys.settings.fusionCalibration, res.active)
      void queryClient.invalidateQueries({ queryKey: queryKeys.settings.fusionCalibration })
      toast.success(`Calibration for rig "${res.calibration.rig_id}" stored`)
      if (res.active.source && res.active.source !== 'database') {
        toast.error(`Stored, but ${calibrationSourceLabel(res.active.source)} takes precedence`)
      }
    },
    onError: (err) => toast.error(err instanceof ApiError ? err.message : 'Upload failed'),
  })
  const uploading = uploadMutation.isPending

  function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    e.target.value = ''
    if (!file) return
    const form = new FormData()
    form.append('file', file)
    uploadMutation.mutate(form)
  }

  const cal = status?.calibration ?? null
  const tone = rmsTone(cal?.rms_error_px)

  return (
    <section className="panel" data-testid="fusion-calibration-panel">
      <div className="panel-head">
        <div>
          <div className="panel-title">
            <Crosshair size={13} /> Thermal ↔ RGB calibration
          </div>
          <p>{status ? calibrationSourceLabel(status.source) : loadError || 'Loading…'}</p>
        </div>
        <label className="primary" style={{ cursor: uploading ? 'progress' : 'pointer' }}>
          <UploadCloud size={15} />
          {uploading ? 'Uploading…' : 'Upload calibration'}
          <input
            type="file"
            hidden
            accept=".json,application/json"
            onChange={handleUpload}
            disabled={uploading}
            data-testid="fusion-calibration-upload"
          />
        </label>
      </div>

      {status?.error && (
        <div className="empty" role="alert">
          Configured calibration is invalid: {status.error}
        </div>
      )}

      {cal ? (
        <div className="chips">
          <div className="chip chip-info">
            <span className="chip-label">Rig</span>
            <span className="chip-value">{cal.rig_id}</span>
          </div>
          <div className={`chip chip-${tone}`}>
            <span className="chip-label">RMS error</span>
            <span className="chip-value">{cal.rms_error_px.toFixed(2)} px</span>
          </div>
          <div className="chip chip-muted">
            <span className="chip-label">Thermal</span>
            <span className="chip-value">{formatSize(cal.thermal_size)}</span>
          </div>
          <div className="chip chip-muted">
            <span className="chip-label">RGB</span>
            <span className="chip-value">{formatSize(cal.rgb_size)}</span>
          </div>
          {cal.created_at && (
            <div className="chip chip-muted">
              <span className="chip-label">Created</span>
              <span className="chip-value">{cal.created_at.slice(0, 10)}</span>
            </div>
          )}
        </div>
      ) : (
        status &&
        !status.error && (
          <div className="empty">
            No calibration — fusion falls back to GPS scaling or feature matching.
          </div>
        )
      )}
    </section>
  )
}
