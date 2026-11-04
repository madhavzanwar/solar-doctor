'use client'

import {
  ArrowDownToLine,
  CheckCircle2,
  Clock3,
  FileJson,
  FileSpreadsheet,
  FileText,
  MapIcon,
  Play,
  RefreshCw,
  Search,
  UploadCloud,
  Wifi,
  XCircle,
} from 'lucide-react'
import dynamic from 'next/dynamic'
import { ChangeEvent, DragEvent, useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useToast } from '@/components/Platform/Toast'
import { CanWrite } from '@/components/Platform/AuthGate'
import { queryKeys } from '@/lib/queryKeys'
import { batchUploadSchema, firstError } from '@/lib/schemas/operations'
import { api, ApiError, API_BASE } from '@/lib/api'
import {
  useMapData,
  type Anomaly as MapAnomaly,
  type BasemapId,
  type OrthoMeta,
  type ViewMode,
} from '@/components/Platform/AnomalyMap'
import { useJob } from '@/components/Platform/hooks/useJob'

const AnomalyMap = dynamic(() => import('@/components/Platform/AnomalyMap'), {
  ssr: false,
  loading: () => (
    <div
      style={{
        height: 360,
        borderRadius: 8,
        border: '1px solid #e2e8f0',
        background: '#f1f5f9',
        display: 'grid',
        placeItems: 'center',
        color: '#64748b',
        fontSize: 12,
        fontWeight: 700,
      }}
    >
      Loading map…
    </div>
  ),
})

const EMPTY_ORTHOS: OrthoMeta[] = []

type JobStatus = 'queued' | 'processing' | 'completed' | 'failed'
type Severity = 'critical' | 'high' | 'medium' | 'low'
type ReportFormat = 'pdf' | 'excel' | 'json' | 'geojson'

type Finding = {
  id: string
  module: string
  className: string
  severity: Severity
  confidence: number
  action: string
}

type Health = {
  status: string
  model: string
  version: string
  db: string
  parks_in_db: number
}

const SEVERITY_ACTION: Record<Severity, string> = {
  critical: 'Dispatch crew and isolate string before next peak load window.',
  high: 'Schedule electrical test and lock report to maintenance queue.',
  medium: 'Review RGB companion frame for cracking or shade source.',
  low: 'Group into next cleaning route.',
}

function findingFromAnomaly(a: MapAnomaly): Finding {
  const sev = a.severity.toLowerCase() as Severity
  return {
    id: a.id,
    module: a.panel_id || 'N/A',
    className: a.class || 'unknown',
    severity: sev,
    confidence: a.confidence,
    action: SEVERITY_ACTION[sev] ?? '',
  }
}

// ── Internal helper components ──

function Chip({
  label,
  value,
  tone,
}: {
  label: string
  value: string
  tone: 'info' | 'ok' | 'crit' | 'muted'
}) {
  return (
    <div className={`chip chip-${tone}`}>
      <span className="chip-label">{label}</span>
      <span className="chip-value">{value}</span>
    </div>
  )
}

function StatusPill({ status }: { status: JobStatus }) {
  const Icon =
    status === 'completed'
      ? CheckCircle2
      : status === 'failed'
        ? XCircle
        : status === 'processing'
          ? RefreshCw
          : Clock3
  return (
    <span className={`pill ${status}`}>
      <Icon size={13} />
      {status}
    </span>
  )
}

function Mini({ label, value }: { label: string; value: string }) {
  return (
    <div className="mini">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function ReportLink({
  href,
  label,
  icon,
  disabled,
}: {
  href: string
  label: string
  icon: ReportFormat
  disabled: boolean
}) {
  const Icon =
    icon === 'pdf'
      ? FileText
      : icon === 'excel'
        ? FileSpreadsheet
        : icon === 'json'
          ? FileJson
          : MapIcon
  if (disabled) {
    return (
      <span className="report disabled">
        <Icon size={15} />
        {label}
      </span>
    )
  }
  return (
    <a className="report" href={href}>
      <ArrowDownToLine size={15} />
      {label}
    </a>
  )
}

// ── OperationsTab ──

export function OperationsTab() {
  const toast = useToast()
  const queryClient = useQueryClient()
  const fileInput = useRef<HTMLInputElement>(null)
  const orthoInput = useRef<HTMLInputElement>(null)

  const { jobs, activeJob, activeJobId, setActiveJobId, addJob } = useJob()

  const [parkId, setParkId] = useState('MH_SOLAR_07')
  const [parkMode, setParkMode] = useState<'auto' | 'numbered' | 'unnumbered'>('auto')
  const [altitude, setAltitude] = useState(42)
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [isUploading, setIsUploading] = useState(false)
  const [message, setMessage] = useState('Ready')
  const [query, setQuery] = useState('')
  const [severityFilter, setSeverityFilter] = useState<Severity | 'all'>('all')
  const [selectedAnomalyId, setSelectedAnomalyId] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<ViewMode>('markers')
  const [basemap, setBasemap] = useState<BasemapId>(
    (process.env.NEXT_PUBLIC_MAPBOX_TOKEN ? 'mapbox' : 'esri') as BasemapId,
  )
  const [activeOrtho, setActiveOrtho] = useState<OrthoMeta | null>(null)
  const [orthoUploading, setOrthoUploading] = useState(false)

  const { data: mapData, loading: mapLoading } = useMapData(
    API_BASE,
    activeJob.id,
    activeJob.status,
  )

  const liveFindings: Finding[] = useMemo(
    () => (mapData ? mapData.anomalies.map(findingFromAnomaly) : []),
    [mapData],
  )

  const totals = useMemo(() => {
    return jobs.reduce(
      (acc, job) => {
        acc.running += job.status === 'processing' ? 1 : 0
        acc.completed += job.status === 'completed' ? 1 : 0
        acc.critical += job.detections.critical
        acc.images += job.total || job.processed
        return acc
      },
      { running: 0, completed: 0, critical: 0, images: 0 },
    )
  }, [jobs])

  const SEVERITY_RANK: Record<Severity, number> = { critical: 0, high: 1, medium: 2, low: 3 }
  const visibleFindings = useMemo(() => {
    const q = query.toLowerCase()
    return liveFindings
      .filter((finding) => {
        const matchesSeverity = severityFilter === 'all' || severityFilter === finding.severity
        const haystack = `${finding.id} ${finding.module} ${finding.className}`.toLowerCase()
        return matchesSeverity && haystack.includes(q)
      })
      .sort((a, b) => {
        const rank = SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity]
        return rank !== 0 ? rank : b.confidence - a.confidence
      })
      .slice(0, 50)
  }, [query, severityFilter, liveFindings]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Health ──
  const healthQuery = useQuery({
    queryKey: queryKeys.ops.health,
    queryFn: () => api.health() as Promise<Health>,
  })
  const health = healthQuery.data ?? null

  // Surface online/offline in the status line. react-query dedupes the fetch,
  // so the old offlineToastedRef guard against repeat toasts is unnecessary.
  useEffect(() => {
    if (healthQuery.isPending) return
    if (healthQuery.error) {
      const err = healthQuery.error
      setMessage(`API offline at ${API_BASE}`)
      toast.error(err instanceof ApiError ? err.message : `API offline at ${API_BASE}`)
      return
    }
    if (health) setMessage(`API online: ${health.model}`)
  }, [healthQuery.isPending, healthQuery.error, health]) // eslint-disable-line react-hooks/exhaustive-deps

  // ── Orthos ──
  // Keyed on parkId, so switching jobs swaps cached lists instead of refetching
  // and racing. The API has returned both a bare array and {orthos: [...]}.
  const orthosQuery = useQuery({
    queryKey: queryKeys.ops.orthos(activeJob.parkId),
    queryFn: async (): Promise<OrthoMeta[]> => {
      const raw = (await api.orthos(activeJob.parkId)) as unknown as
        | { orthos?: OrthoMeta[] }
        | OrthoMeta[]
      return Array.isArray(raw) ? raw : (raw.orthos ?? [])
    },
  })
  const orthos = orthosQuery.data ?? EMPTY_ORTHOS

  useEffect(() => {
    setActiveOrtho(null)
  }, [activeJob.parkId])

  useEffect(() => {
    const err = orthosQuery.error
    if (err) toast.error(err instanceof ApiError ? err.message : String(err))
  }, [orthosQuery.error]) // eslint-disable-line react-hooks/exhaustive-deps

  async function uploadOrtho(file: File | undefined) {
    if (!file) return
    if (!/\.(tif|tiff)$/i.test(file.name)) {
      setMessage('Orthomosaic must be a .tif or .tiff GeoTIFF')
      return
    }
    setOrthoUploading(true)
    setMessage(`Uploading ortho ${file.name}…`)
    const form = new FormData()
    form.append('file', file)
    try {
      const data = await api.uploadOrtho(activeJob.parkId, form)
      const ortho = data as unknown as OrthoMeta
      // Write the uploaded ortho straight into the cache (replacing any entry
      // with the same name), then let the query refetch to reconcile.
      queryClient.setQueryData<OrthoMeta[]>(
        queryKeys.ops.orthos(activeJob.parkId),
        (current = []) => [...current.filter((o) => o.name !== ortho.name), ortho],
      )
      void queryClient.invalidateQueries({ queryKey: queryKeys.ops.orthos(activeJob.parkId) })
      setActiveOrtho(ortho)
      setMessage(`Ortho ${ortho.name} ready · ${(ortho as Record<string, unknown>).crs}`)
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : 'Ortho upload failed'
      setMessage(msg)
      toast.error(msg)
    } finally {
      setOrthoUploading(false)
    }
  }

  function selectFile(file: File | undefined) {
    if (!file) return
    setSelectedFile(file)
    setMessage(
      file.name.endsWith('.zip') ? 'Mission package selected' : 'Batch upload expects a .zip archive',
    )
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    selectFile(event.dataTransfer.files[0])
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) {
    selectFile(event.target.files?.[0])
  }

  async function uploadBatch() {
    if (!selectedFile) {
      setMessage('Choose a mission ZIP first')
      return
    }

    // Validate against the same contract the API enforces, so a bad park ID
    // fails here instead of after the whole ZIP has uploaded.
    const parsed = batchUploadSchema.safeParse({
      park_id: parkId,
      altitude_m: altitude,
      file_name: selectedFile.name,
    })
    const problem = firstError(parsed)
    if (problem) {
      setMessage(problem)
      toast.error(problem)
      return
    }

    setIsUploading(true)
    setMessage('Uploading batch...')

    const form = new FormData()
    form.append('images', selectedFile)
    form.append('park_id', parkId)
    form.append('park_mode', parkMode)
    form.append('altitude_m', String(altitude))

    try {
      const data = await api.batch(form)

      const job = {
        id: data.job_id,
        parkId,
        fileName: selectedFile.name,
        status: 'queued' as const,
        progress: 0,
        processed: 0,
        total: 0,
        altitude,
        createdAt: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
        detections: { critical: 0, high: 0, medium: 0, low: 0 },
      }

      addJob(job)
      setSelectedFile(null)
      setMessage(`Queued ${data.job_id}`)
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : 'Could not submit batch'
      setMessage(msg)
      toast.error(msg)
    } finally {
      setIsUploading(false)
    }
  }

  function reportHref(format: ReportFormat) {
    return api.reportUrl(activeJob.id, format as 'json' | 'excel' | 'geojson' | 'pdf')
  }

  return (
    <>
      {/* Compact command bar — title + inline metric chips */}
      <header className="cmdbar">
        <div className="cmdbar-titles">
          <div className="eyebrow">
            <Wifi size={13} />
            {health ? `${health.status} · DB ${health.db} · ${health.parks_in_db} parks` : message}
          </div>
          <h1>Operations</h1>
        </div>
        <div className="chips">
          <Chip label="Running" value={String(totals.running)} tone="info" />
          <Chip label="Completed" value={String(totals.completed)} tone="ok" />
          <Chip label="Critical" value={String(totals.critical)} tone="crit" />
          <Chip label="Images" value={totals.images.toLocaleString()} tone="muted" />
        </div>
      </header>

      <div className="ops-grid operations-split">
        {/* ───── LEFT (primary): map + findings ───── */}
        <div className="ops-main">
          <section className="panel map-panel-hero">
            <div className="panel-head compact">
              <div>
                <div className="panel-title">
                  <MapIcon size={16} />
                  <span>Anomaly map · {activeJob.parkId}</span>
                </div>
                <p>GPS-tagged anomaly markers on every image position.</p>
              </div>
              <CanWrite>
              <div className="map-actions">
                <input
                  ref={orthoInput}
                  type="file"
                  accept=".tif,.tiff,image/tiff"
                  hidden
                  onChange={(event) => uploadOrtho(event.target.files?.[0])}
                />
                <button
                  className="secondary"
                  type="button"
                  disabled={orthoUploading}
                  onClick={() => orthoInput.current?.click()}
                >
                  <UploadCloud size={14} />
                  {orthoUploading ? 'Uploading…' : 'Upload ortho'}
                </button>
              </div>
              </CanWrite>
            </div>
            {mapData && (
              <AnomalyMap
                apiBase={API_BASE}
                data={mapData}
                loading={mapLoading}
                selectedAnomalyId={selectedAnomalyId}
                onAnomalySelect={setSelectedAnomalyId}
                viewMode={viewMode}
                onViewModeChange={setViewMode}
                basemap={basemap}
                onBasemapChange={setBasemap}
                ortho={activeOrtho}
                orthos={orthos}
                onOrthoChange={setActiveOrtho}
              />
            )}
          </section>

          <section className="panel">
            <div className="panel-head compact">
              <div>
                <div className="panel-title">Fault triage</div>
                <p>
                  {visibleFindings.length} of {liveFindings.length} anomalies · click to locate on
                  map.
                </p>
              </div>
              <div className="tools inline">
                <label className="search">
                  <Search size={14} />
                  <input
                    value={query}
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="Search module or class"
                  />
                </label>
                <select
                  value={severityFilter}
                  onChange={(event) => setSeverityFilter(event.target.value as Severity | 'all')}
                >
                  <option value="all">All severities</option>
                  <option value="critical">Critical</option>
                  <option value="high">High</option>
                  <option value="medium">Medium</option>
                  <option value="low">Low</option>
                </select>
              </div>
            </div>

            {!mapLoading && visibleFindings.length === 0 && (
              <div className="empty">
                No anomalies match the current filters{query ? ' or query' : ''}.
              </div>
            )}
            <div className="findings-grid">
              {visibleFindings.map((finding) => {
                const selected = selectedAnomalyId === finding.id
                return (
                  <article
                    className={`finding ${selected ? 'selected' : ''}`}
                    key={finding.id}
                    onClick={() => setSelectedAnomalyId(selected ? null : finding.id)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter' || event.key === ' ') {
                        event.preventDefault()
                        setSelectedAnomalyId(selected ? null : finding.id)
                      }
                    }}
                  >
                    <div className="finding-id">
                      <span className="muted">{finding.id}</span>
                      <strong>{finding.module}</strong>
                    </div>
                    <div className="finding-body">
                      <span className={`severity ${finding.severity}`}>{finding.severity}</span>
                      <p>
                        <strong>{finding.className}</strong> · {Math.round(finding.confidence * 100)}
                        %
                        <br />
                        <span className="muted">{finding.action}</span>
                      </p>
                    </div>
                  </article>
                )
              })}
            </div>
          </section>
        </div>

        {/* ───── RIGHT (rail): active job + new mission + queue ───── */}
        <aside className="ops-rail">
          <section className={`panel job-card ${activeJob.status}`}>
            <div className="job-head">
              <div>
                <div className="muted micro">Active mission</div>
                <strong>{activeJob.parkId}</strong>
                <span className="muted micro">{activeJob.id}</span>
              </div>
              <StatusPill status={activeJob.status} />
            </div>
            <div className="job-progress">
              <div className="job-progress-row">
                <span>{Math.round(activeJob.progress * 100)}%</span>
                <span className="muted">
                  {activeJob.processed}/{activeJob.total || '—'}
                </span>
              </div>
              <div className="bar">
                <span style={{ width: `${activeJob.progress * 100}%` }} />
              </div>
            </div>
            <div className="mini-row">
              <Mini label="Altitude" value={`${activeJob.altitude} m`} />
              <Mini label="Critical" value={String(activeJob.detections.critical)} />
              <Mini label="Started" value={activeJob.createdAt} />
            </div>
            <div className="reports">
              <ReportLink
                href={reportHref('pdf')}
                label="PDF"
                icon="pdf"
                disabled={activeJob.status !== 'completed'}
              />
              <ReportLink
                href={reportHref('excel')}
                label="Excel"
                icon="excel"
                disabled={activeJob.status !== 'completed'}
              />
              <ReportLink
                href={reportHref('json')}
                label="JSON"
                icon="json"
                disabled={activeJob.status !== 'completed'}
              />
              <ReportLink
                href={reportHref('geojson')}
                label="GeoJSON"
                icon="geojson"
                disabled={activeJob.status !== 'completed'}
              />
            </div>
          </section>

          <CanWrite>
          <section className="panel">
            <div className="panel-head compact">
              <div>
                <div className="panel-title">New mission</div>
                <p>Upload ZIP with thermal/ folder.</p>
              </div>
              <UploadCloud size={18} />
            </div>
            <div
              className="drop compact"
              onDragOver={(event) => event.preventDefault()}
              onDrop={onDrop}
              onClick={() => fileInput.current?.click()}
            >
              <input ref={fileInput} type="file" accept=".zip" hidden onChange={onFileChange} />
              <div>
                <UploadCloud size={22} />
                <strong>{selectedFile ? selectedFile.name : 'Drop ZIP or click'}</strong>
                <span className="muted">2 GB / 10k files</span>
              </div>
            </div>
            <div className="form-row">
              <label>
                Park ID
                <input value={parkId} onChange={(event) => setParkId(event.target.value)} />
              </label>
              <label>
                Park Mode
                <select
                  value={parkMode}
                  onChange={(event) =>
                    setParkMode(event.target.value as 'auto' | 'numbered' | 'unnumbered')
                  }
                  title="Auto: detect from images. Numbered: OCR panel IDs from RGB. Unnumbered: synthetic R-C grid."
                >
                  <option value="auto">Auto-detect</option>
                  <option value="numbered">Numbered (OCR)</option>
                  <option value="unnumbered">Unnumbered (Grid)</option>
                </select>
              </label>
              <label>
                Altitude m
                <input
                  type="number"
                  min={1}
                  max={500}
                  value={altitude}
                  onChange={(event) => setAltitude(Number(event.target.value))}
                />
              </label>
            </div>
            <button className="primary" disabled={isUploading} onClick={uploadBatch}>
              {isUploading ? <RefreshCw size={15} /> : <Play size={15} />}
              Submit batch
            </button>
          </section>
          </CanWrite>

          <section className="panel">
            <div className="panel-head compact">
              <div>
                <div className="panel-title">Queue</div>
                <p>
                  {jobs.length} batch{jobs.length === 1 ? '' : 'es'}
                </p>
              </div>
              <button className="secondary" onClick={() => window.location.reload()}>
                <RefreshCw size={13} />
              </button>
            </div>
            <div className="queue-list">
              {jobs.map((job) => (
                <button
                  key={job.id}
                  className={`queue-item ${activeJob.id === job.id ? 'active' : ''}`}
                  onClick={() => setActiveJobId(job.id)}
                >
                  <div className="queue-row">
                    <strong>{job.parkId}</strong>
                    <StatusPill status={job.status} />
                  </div>
                  <div className="queue-row sub">
                    <span className="muted">{Math.round(job.progress * 100)}%</span>
                    <span className="muted">{job.detections.critical} crit</span>
                  </div>
                  <div className="bar slim">
                    <span style={{ width: `${job.progress * 100}%` }} />
                  </div>
                </button>
              ))}
            </div>
          </section>
        </aside>
      </div>
    </>
  )
}
