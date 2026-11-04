import type { OdmJob } from '@/lib/odm'
import type { CalibrationStatus, CalibrationSummary } from '@/lib/calibration'
import type { ParkLayoutStatus } from '@/lib/parkLayout'

export const API_BASE =
  process.env.NEXT_PUBLIC_AXALON_API_URL || 'http://localhost:8000'

export class ApiError extends Error {
  status: number
  body: string
  constructor(status: number, body: string, message?: string) {
    super(message ?? `HTTP ${status}: ${body.slice(0, 200)}`)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

const REQUEST_TIMEOUT_MS = 20_000
/** Image ZIPs for orthomosaic generation run to gigabytes; 20 s would abort them. */
const ODM_UPLOAD_TIMEOUT_MS = 30 * 60_000

/** sessionStorage slot for the credential: the shared API key, or — when the
 * API runs AXALON_AUTH_MODE=users — the session token. Same slot, same header. */
export const CREDENTIAL_STORAGE_KEY = 'axalon_api_key'

export function storedCredential(): string {
  const envKey = process.env.NEXT_PUBLIC_AXALON_API_KEY ?? ''
  if (typeof sessionStorage === 'undefined') return envKey
  return sessionStorage.getItem(CREDENTIAL_STORAGE_KEY) ?? envKey
}

/** Read-only share token from the page URL (`/platform?share=…`), if any. */
export function shareToken(): string {
  if (typeof window === 'undefined') return ''
  return new URLSearchParams(window.location.search).get('share') ?? ''
}

function withShare(path: string): string {
  const share = shareToken()
  if (!share) return path
  return `${path}${path.includes('?') ? '&' : '?'}share=${encodeURIComponent(share)}`
}

/** Query-string auth for URLs the browser fetches itself (<img>, downloads). */
function authQuery(prefix: '?' | '&'): string {
  const params = new URLSearchParams()
  const key = storedCredential()
  if (key) params.set('api_key', key)
  const share = shareToken()
  if (share) params.set('share', share)
  const qs = params.toString()
  return qs ? `${prefix}${qs}` : ''
}

function isHtmlBody(text: string): boolean {
  const t = text.trimStart()
  return t.startsWith('<!DOCTYPE') || t.startsWith('<html')
}

async function request<T>(
  path: string,
  init?: RequestInit,
  timeoutMs: number = REQUEST_TIMEOUT_MS,
): Promise<T> {
  let res: Response
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  try {
    const storedKey = storedCredential()
    const headers: HeadersInit = storedKey
      ? {
          ...((init?.headers as Record<string, string> | undefined) ?? {}),
          Authorization: `Bearer ${storedKey}`,
        }
      : ((init?.headers as Record<string, string> | undefined) ?? {})
    res = await fetch(`${API_BASE}${withShare(path)}`, { ...init, headers, signal: controller.signal })
  } catch (err) {
    const isTimeout = err instanceof Error && err.name === 'AbortError'
    const msg = isTimeout
      ? `Request timed out after ${timeoutMs / 1000}s — the backend may be starting up`
      : `Network error contacting ${API_BASE}${path}`
    throw new ApiError(0, String(err), msg)
  } finally {
    clearTimeout(timer)
  }
  const text = await res.text()
  if (!res.ok) {
    if (res.status === 401 && typeof window !== 'undefined') {
      window.dispatchEvent(new Event('axalon:unauthorized'))
    }
    const body = isHtmlBody(text) ? '' : text
    const msg = isHtmlBody(text)
      ? `Server error (HTTP ${res.status}) — the backend returned an unexpected response`
      : undefined
    throw new ApiError(res.status, body, msg)
  }
  if (!text) return undefined as T
  try {
    return JSON.parse(text) as T
  } catch {
    return text as unknown as T
  }
}

// Shapes — keep loose; the API is the source of truth.
export type Health = { status: string; [k: string]: unknown }

export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'

// Radiometric fields (°C) from the iTL612R Pro _temp.raw companion. All nullable:
// images without a companion carry no temperatures.
export type DetectionTemps = {
  min_temp?: number | null
  max_temp?: number | null
  avg_temp?: number | null
  reference_temp?: number | null
  /** max_temp − reference_temp (frame median ≈ healthy module) */
  delta_t_measured?: number | null
  /** ΔT scaled to 1000 W/m² (IEC 62446-3); null without irradiance */
  delta_t_normalized?: number | null
}

// Estimated daily revenue loss from CRITICAL/HIGH panels — an estimate, not a meter reading.
export type RevenueLoss = {
  revenue_loss_usd?: number | null
  revenue_currency?: string
}

export type GridPanelDetection = DetectionTemps & {
  class: string | null
  confidence: number | null
  severity: Severity | null
  thermal_filename: string | null
  bbox: number[] | null
}

export type GridPanel = {
  panel_id: string
  row: number
  col: number
  worst_severity: Severity | null
  detection_count: number
  detections: GridPanelDetection[]
  gps: { lat: number; lon: number } | null
}

export type ParkGrid = {
  park_id: string
  inspection_id: string | null
  rows: number
  cols: number
  panels: GridPanel[]
}

export type TrendPoint = {
  inspection_id: string
  date: string | null
  CRITICAL: number
  HIGH: number
  MEDIUM: number
  LOW: number
}

export type RecurringPanel = {
  panel_id: string
  inspection_count: number
  worst_severity: Severity
  classes: string[]
  first_seen: string | null
  last_seen: string | null
}

export type JobStatus = {
  job_id: string
  state: 'queued' | 'running' | 'succeeded' | 'failed' | string
  progress?: number
  total?: number
  processed?: number
  message?: string
  [k: string]: unknown
}
export type AlertChannelStatus = 'sent' | 'failed' | 'skipped' | 'not_configured'
export type AlertChannelResult = { status: AlertChannelStatus; detail: string }
export type AlertTestResult = {
  configured: boolean
  min_severity: Severity
  channels: Record<'webhook' | 'email', AlertChannelResult>
}
export type ParkRef = { id: string; name?: string }
/** One park in /analytics/overview; revenue loss is for its latest inspection. */
export type OverviewBundle = RevenueLoss & { park: ParkRef; trend: TrendPoint[] }
export type ParkSummary = Record<string, unknown>
export type MapData = Record<string, unknown>
export type SettingsBlob = Record<string, unknown>
export type InspectResult = {
  job_id: string
  status: string
  total_detections: number
  summary: {
    by_severity?: { CRITICAL: number; HIGH: number; MEDIUM: number; LOW: number }
    CRITICAL?: number
    HIGH?: number
    MEDIUM?: number
    LOW?: number
    [k: string]: unknown
  }
  detections: Array<
    DetectionTemps & {
      class: string
      class_id: number
      confidence: number
      bbox: [number, number, number, number]
      bbox_norm?: [number, number, number, number]
      severity: string
      [k: string]: unknown
    }
  >
  rgb_filename?: string
  [k: string]: unknown
}
export type OrthoMeta = {
  park_id: string
  name: string
  crs: string
  width: number
  height: number
  band_count: number
  bounds: { west: number; south: number; east: number; north: number }
  center: { lat: number; lon: number }
  size_bytes: number
}

export type DiffPanel = {
  panel_id: string
  status: 'new' | 'resolved' | 'changed' | 'unchanged'
  severity_a: Severity | null
  severity_b: Severity | null
  detections_a: { class: string; severity: Severity | null; confidence: number | null }[]
  detections_b: { class: string; severity: Severity | null; confidence: number | null }[]
}

export type ParkDiff = {
  park_id: string
  inspection_a: string
  inspection_b: string
  summary: { new: number; resolved: number; changed: number }
  panels: DiffPanel[]
}

export type Correction = {
  id: number
  job_id: string
  image_id: string | null
  panel_id: string | null
  class: string
  class_id: number | null
  severity: string | null
  bbox_norm: [number, number, number, number]
  notes: string | null
  created_at: string | null
  updated_at?: string | null
}

export type CorrectionCreate = {
  class_: string
  class_id: number
  severity: string
  bbox_norm: [number, number, number, number]
  image_id?: string
  panel_id?: string
  notes?: string
}

export type MissionSummary = {
  id: number
  name: string
  park_id: string | null
  mission_type: 'grid' | 'perimeter' | 'corridor'
  camera_id: string | null
  area_ha: number | null
  image_count: number | null
  created_at: string | null
}

export type MissionFull = MissionSummary & {
  params: Record<string, unknown>
  polygon: { lat: number; lon: number }[]
  waypoints: { lat: number; lon: number; alt: number }[]
  updated_at: string | null
}

export type MissionCreate = {
  name: string
  park_id?: string | null
  mission_type: string
  camera_id?: string | null
  params: Record<string, unknown>
  polygon: { lat: number; lon: number }[]
  waypoints: { lat: number; lon: number; alt: number }[]
  area_ha: number
  image_count: number
}

// ── Inventory & prototype tracking ───────────────────────────────────────────

export type ComponentCategory =
  | 'flight-controller'
  | 'motor'
  | 'esc'
  | 'battery'
  | 'propeller'
  | 'frame'
  | 'camera'
  | 'sensor'
  | 'companion-computer'
  | 'radio'
  | 'gps'
  | 'wiring'
  | 'other'

export type PrototypeStatus = 'planning' | 'building' | 'active' | 'retired'
export type OrderStatus = 'planned' | 'ordered' | 'received' | 'cancelled'

export type InventoryComponent = {
  id: number
  name: string
  category: ComponentCategory
  part_number: string | null
  vendor: string | null
  link: string | null
  unit_cost: number | null
  currency: string
  qty_total: number
  qty_assigned: number
  qty_available: number
  specs: string | null
  notes: string | null
  created_at: string | null
  updated_at: string | null
}

export type ComponentAssignment = {
  id: number
  component_id: number
  prototype_id: number
  component_name: string | null
  component_category: string | null
  qty: number
  notes: string | null
  created_at: string | null
}

export type Prototype = {
  id: number
  name: string
  status: PrototypeStatus
  description: string | null
  notes: string | null
  assignments: ComponentAssignment[]
  created_at: string | null
  updated_at: string | null
}

export type ComponentOrder = {
  id: number
  component_id: number | null
  name: string
  qty: number
  est_unit_cost: number | null
  vendor: string | null
  link: string | null
  status: OrderStatus
  needed_by: string | null
  notes: string | null
  created_at: string | null
  updated_at: string | null
}

export type InventorySummary = {
  component_count: number
  prototype_count: number
  open_order_count: number
  stock_value: number
  low_stock: InventoryComponent[]
}

export type ComponentCreate = Partial<
  Omit<InventoryComponent, 'id' | 'qty_assigned' | 'qty_available' | 'created_at' | 'updated_at'>
> & { name: string }

export type PrototypeCreate = Partial<Pick<Prototype, 'status' | 'description' | 'notes'>> & {
  name: string
}

export type OrderCreate = Partial<
  Omit<ComponentOrder, 'id' | 'created_at' | 'updated_at'>
>

// ── Area C: Projects → Sites → Missions/Inspections ──────────────────────────

export type ProjectStatus = 'active' | 'archived'

export type Project = {
  id: number
  name: string
  client: string | null
  description: string | null
  status: ProjectStatus
  site_count?: number
  created_at: string | null
  updated_at: string | null
}

export type ProjectSite = {
  id: string
  name: string
  total_panels: number
  inspection_count: number
  mission_count: number
  last_inspection_date: string | null
}

export type ProjectDetail = Project & { sites: ProjectSite[] }

// ── /track workspace ──────────────────────────────────────────────────────────

export type NoteKind = 'research' | 'log' | 'doc' | 'link' | 'idea' | 'other'

export type TrackNote = {
  id: number
  title: string
  kind: NoteKind
  body: string | null
  url: string | null
  tags: string | null
  created_at: string | null
  updated_at: string | null
}

export type TrackFileMeta = {
  id: number
  original_name: string
  stored_name: string
  label: string | null
  content_type: string | null
  size_bytes: number
  created_at: string | null
}

export type NoteCreate = Partial<Omit<TrackNote, 'id' | 'created_at' | 'updated_at'>> & {
  title: string
}

// ── Fault repair workflow ─────────────────────────────────────────────────────

export type FaultStatus = 'open' | 'stale' | 'assigned' | 'in_progress' | 'resolved'
export type FaultPriority = 'urgent' | 'high' | 'medium' | 'low'

export type PanelFault = {
  id: number
  park_id: string
  panel_id: string
  class: string
  class_id: number | null
  severity: Severity | null
  status: FaultStatus
  occurrences: number
  max_confidence: number
  first_seen_inspection_id: string | null
  last_seen_inspection_id: string | null
  first_seen_date: string | null
  last_seen_date: string | null
  last_bbox: number[] | null
  last_gps: { lat: number; lon: number } | null
  notes: string | null
  comment_count: number
  assignee: string | null
  due_date: string | null
  /** Effective priority: the override, else derived from the class severity. */
  priority: FaultPriority | null
  priority_override: FaultPriority | null
  resolved_at: string | null
  resolution_note: string | null
  photo_count: number
  updated_at: string | null
}

export type FaultsList = {
  park_id: string
  total: number
  counts_by_status: Record<FaultStatus, number>
  faults: PanelFault[]
}

/** PATCH /faults/{id}. `null` clears assignee, due_date or the priority override. */
export type FaultUpdate = {
  status?: FaultStatus
  notes?: string
  assignee?: string | null
  due_date?: string | null
  priority?: FaultPriority | null
  resolution_note?: string | null
}

export type FaultPhoto = {
  id: number
  fault_id: number
  original_name: string
  content_type: string
  size_bytes: number
  created_at: string | null
}

export type WorkOrderFormat = 'csv' | 'xlsx'

export type WorkOrderFilters = {
  status?: FaultStatus[]
  assignee?: string
}

/** Query string for the work-order export (format + optional filters). */
export function workOrdersQuery(format: WorkOrderFormat, filters: WorkOrderFilters = {}): string {
  const params = new URLSearchParams({ format })
  if (filters.status?.length) params.set('status', filters.status.join(','))
  if (filters.assignee?.trim()) params.set('assignee', filters.assignee.trim())
  return params.toString()
}

// ── Accounts & sharing (AXALON_AUTH_MODE=users) ─────────────────────────────

export type AuthMode = 'off' | 'apikey' | 'users'
export type UserRole = 'admin' | 'operator' | 'viewer'

export type AuthUser = {
  id: number
  email: string
  role: UserRole
  disabled: boolean
  project_ids: number[]
  created_at: string | null
}

export type AuthMe = {
  mode: AuthMode
  kind: 'system' | 'user' | 'share'
  role: UserRole
  project_ids: number[] | null
  user: AuthUser | null
}

export type LoginResponse = { token: string; expires_at: string; user: AuthUser }

export type UserCreate = { email: string; password: string; role: UserRole; project_ids: number[] }
export type UserUpdate = Partial<{ role: UserRole; disabled: boolean; password: string; project_ids: number[] }>

export type ShareLink = {
  id: number
  project_id: number
  label: string | null
  created_by: number | null
  created_at: string | null
  expires_at: string | null
  revoked_at: string | null
  revoked: boolean
  expired: boolean
}

function jsonInit(method: string, body: unknown): RequestInit {
  return {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  }
}

export const api = {
  health: () => request<Health>('/health'),
  batch: (form: FormData) =>
    request<{ job_id: string }>('/batch', { method: 'POST', body: form }),
  inspect: (form: FormData) =>
    request<InspectResult>('/inspect', { method: 'POST', body: form }),
  status: (jobId: string) => request<JobStatus>(`/status/${encodeURIComponent(jobId)}`),
  reportUrl: (jobId: string, format: 'json' | 'excel' | 'geojson' | 'pdf') =>
    `${API_BASE}/report/${encodeURIComponent(jobId)}?format=${format}${authQuery('&')}`,
  mapData: (jobId: string) => request<MapData>(`/map/${encodeURIComponent(jobId)}`),
  parks: () => request<ParkRef[]>('/parks'),
  missions: (parkId?: string) =>
    request<MissionSummary[]>(`/missions${parkId ? `?park_id=${encodeURIComponent(parkId)}` : ''}`),
  mission: (id: number) => request<MissionFull>(`/missions/${id}`),
  createMission: (body: MissionCreate) =>
    request<MissionSummary>('/missions', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  deleteMission: (id: number) => request<void>(`/missions/${id}`, { method: 'DELETE' }),
  park: (parkId: string) =>
    request<ParkSummary>(`/park/${encodeURIComponent(parkId)}`),
  parkGrid: (parkId: string, inspectionId?: string) => {
    const q = inspectionId ? `?inspection_id=${encodeURIComponent(inspectionId)}` : ''
    return request<ParkGrid>(`/park/${encodeURIComponent(parkId)}/grid${q}`)
  },
  parkGridPng: (parkId: string, inspectionId?: string) => {
    const q = inspectionId ? `?inspection_id=${encodeURIComponent(inspectionId)}` : ''
    const storedKey = storedCredential()
    return fetch(`${API_BASE}${withShare(`/park/${encodeURIComponent(parkId)}/grid/png${q}`)}`, {
      headers: storedKey ? { Authorization: `Bearer ${storedKey}` } : {},
    }).then((res) => {
      if (!res.ok) throw new Error(`PNG export failed: ${res.status}`)
      return res.blob()
    })
  },
  parkTrend: (parkId: string) =>
    request<TrendPoint[]>(`/park/${encodeURIComponent(parkId)}/trend`),
  parkRecurring: (parkId: string, minInspections = 2) =>
    request<RecurringPanel[]>(
      `/park/${encodeURIComponent(parkId)}/recurring?min_inspections=${minInspections}`,
    ),
  orthos: (parkId: string) =>
    request<OrthoMeta[] | { orthos: OrthoMeta[] }>(
      `/park/${encodeURIComponent(parkId)}/orthos`,
    ).then((resp) => (Array.isArray(resp) ? resp : resp.orthos ?? [])),
  uploadOrtho: (parkId: string, form: FormData) =>
    request<OrthoMeta>(`/park/${encodeURIComponent(parkId)}/ortho`, {
      method: 'POST',
      body: form,
    }),
  orthoGenerationJobs: (parkId: string) =>
    request<{ jobs?: OdmJob[] }>(`/parks/${encodeURIComponent(parkId)}/orthos/generate`).then(
      (resp) => resp.jobs ?? [],
    ),
  generateOrtho: (parkId: string, form: FormData) =>
    request<OdmJob>(
      `/parks/${encodeURIComponent(parkId)}/orthos/generate`,
      { method: 'POST', body: form },
      ODM_UPLOAD_TIMEOUT_MS,
    ),
  orthoGenerationStatus: (parkId: string, jobId: string) =>
    request<OdmJob>(
      `/parks/${encodeURIComponent(parkId)}/orthos/generate/${encodeURIComponent(jobId)}`,
    ),
  cancelOrthoGeneration: (parkId: string, jobId: string) =>
    request<OdmJob>(
      `/parks/${encodeURIComponent(parkId)}/orthos/generate/${encodeURIComponent(jobId)}`,
      { method: 'DELETE' },
    ),
  parkLayout: (parkId: string) =>
    request<ParkLayoutStatus>(`/park/${encodeURIComponent(parkId)}/layout`),
  uploadParkLayout: (parkId: string, form: FormData) =>
    request<ParkLayoutStatus>(`/park/${encodeURIComponent(parkId)}/layout`, {
      method: 'POST',
      body: form,
    }),
  deleteParkLayout: (parkId: string) =>
    request<ParkLayoutStatus>(`/park/${encodeURIComponent(parkId)}/layout`, {
      method: 'DELETE',
    }),
  fusionCalibration: () => request<CalibrationStatus>('/settings/fusion-calibration'),
  uploadFusionCalibration: (form: FormData) =>
    request<{ ok: boolean; calibration: CalibrationSummary; active: CalibrationStatus }>(
      '/settings/fusion-calibration',
      { method: 'POST', body: form },
    ),
  getSettings: () => request<SettingsBlob>('/settings'),
  putSettings: (blob: SettingsBlob) =>
    request<SettingsBlob>('/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ settings: blob }),
    }),
  testAlert: () => request<AlertTestResult>('/alerts/test', { method: 'POST' }),
  parkDiff: (parkId: string, inspectionA: string, inspectionB: string) =>
    request<ParkDiff>(
      `/park/${encodeURIComponent(parkId)}/diff?inspection_a=${encodeURIComponent(inspectionA)}&inspection_b=${encodeURIComponent(inspectionB)}`,
    ),
  corrections: (jobId: string) =>
    request<Correction[]>(`/corrections/${encodeURIComponent(jobId)}`),
  addCorrection: (jobId: string, body: CorrectionCreate) =>
    request<Correction>(`/corrections/${encodeURIComponent(jobId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  deleteCorrection: (jobId: string, id: number) =>
    request<void>(`/corrections/${encodeURIComponent(jobId)}/${id}`, { method: 'DELETE' }),

  projects: () => request<Project[]>('/projects'),
  project: (id: number) => request<ProjectDetail>(`/projects/${id}`),
  createProject: (body: { name: string; client?: string | null; description?: string | null }) =>
    request<Project>('/projects', jsonInit('POST', body)),
  updateProject: (id: number, body: Partial<Pick<Project, 'name' | 'client' | 'description' | 'status'>>) =>
    request<Project>(`/projects/${id}`, jsonInit('PATCH', body)),
  deleteProject: (id: number) => request<void>(`/projects/${id}`, { method: 'DELETE' }),
  updatePark: (parkId: string, body: { project_id?: number | null; name?: string }) =>
    request<{ id: string; name: string; project_id: number | null }>(
      `/park/${encodeURIComponent(parkId)}`,
      jsonInit('PATCH', body),
    ),

  analyticsOverview: () =>
    request<OverviewBundle[]>('/analytics/overview'),

  // Inventory & prototype tracking
  inventorySummary: () => request<InventorySummary>('/inventory/summary'),
  inventoryComponents: () => request<InventoryComponent[]>('/inventory/components'),
  createComponent: (body: ComponentCreate) =>
    request<InventoryComponent>('/inventory/components', jsonInit('POST', body)),
  updateComponent: (id: number, body: Partial<ComponentCreate>) =>
    request<InventoryComponent>(`/inventory/components/${id}`, jsonInit('PATCH', body)),
  deleteComponent: (id: number) =>
    request<void>(`/inventory/components/${id}`, { method: 'DELETE' }),
  prototypes: () => request<Prototype[]>('/inventory/prototypes'),
  createPrototype: (body: PrototypeCreate) =>
    request<Prototype>('/inventory/prototypes', jsonInit('POST', body)),
  updatePrototype: (id: number, body: Partial<PrototypeCreate>) =>
    request<Prototype>(`/inventory/prototypes/${id}`, jsonInit('PATCH', body)),
  deletePrototype: (id: number) =>
    request<void>(`/inventory/prototypes/${id}`, { method: 'DELETE' }),
  createAssignment: (body: { component_id: number; prototype_id: number; qty: number; notes?: string }) =>
    request<ComponentAssignment>('/inventory/assignments', jsonInit('POST', body)),
  updateAssignment: (id: number, body: { qty?: number; notes?: string }) =>
    request<ComponentAssignment>(`/inventory/assignments/${id}`, jsonInit('PATCH', body)),
  deleteAssignment: (id: number) =>
    request<void>(`/inventory/assignments/${id}`, { method: 'DELETE' }),
  orders: () => request<ComponentOrder[]>('/inventory/orders'),
  createOrder: (body: OrderCreate) =>
    request<ComponentOrder>('/inventory/orders', jsonInit('POST', body)),
  updateOrder: (id: number, body: Partial<OrderCreate>) =>
    request<ComponentOrder>(`/inventory/orders/${id}`, jsonInit('PATCH', body)),
  deleteOrder: (id: number) =>
    request<void>(`/inventory/orders/${id}`, { method: 'DELETE' }),

  // /track workspace
  trackLogin: (password: string) =>
    request<{ ok: boolean }>('/track/login', jsonInit('POST', { password })),
  setTrackPassword: (newPassword: string, currentPassword?: string) =>
    request<{ ok: boolean }>(
      '/track/password',
      jsonInit('POST', { new_password: newPassword, current_password: currentPassword ?? '' }),
    ),
  trackNotes: (kind?: string) =>
    request<TrackNote[]>(`/track/notes${kind ? `?kind=${encodeURIComponent(kind)}` : ''}`),
  createNote: (body: NoteCreate) => request<TrackNote>('/track/notes', jsonInit('POST', body)),
  updateNote: (id: number, body: Partial<NoteCreate>) =>
    request<TrackNote>(`/track/notes/${id}`, jsonInit('PATCH', body)),
  deleteNote: (id: number) => request<void>(`/track/notes/${id}`, { method: 'DELETE' }),
  trackFiles: () => request<TrackFileMeta[]>('/track/files'),
  uploadTrackFile: (form: FormData) =>
    request<TrackFileMeta>('/track/files', { method: 'POST', body: form }),
  deleteTrackFile: (id: number) => request<void>(`/track/files/${id}`, { method: 'DELETE' }),
  trackFileUrl: (id: number) => `${API_BASE}/track/files/${id}${authQuery('?')}`,

  /** Auth query string for browser-loaded URLs (images, tiles, downloads). */
  authQuery,

  // Accounts (AXALON_AUTH_MODE=users)
  authMode: () => request<{ mode: AuthMode }>('/auth/mode'),
  login: (email: string, password: string) =>
    request<LoginResponse>('/auth/login', jsonInit('POST', { email, password })),
  logout: () => request<void>('/auth/logout', { method: 'POST' }),
  me: () => request<AuthMe>('/auth/me'),
  users: () => request<AuthUser[]>('/users'),
  createUser: (body: UserCreate) => request<AuthUser>('/users', jsonInit('POST', body)),
  updateUser: (id: number, body: UserUpdate) => request<AuthUser>(`/users/${id}`, jsonInit('PATCH', body)),
  deleteUser: (id: number) => request<void>(`/users/${id}`, { method: 'DELETE' }),
  shareLinks: () => request<ShareLink[]>('/share-links'),
  createShareLink: (body: { project_id: number; label?: string; expires_in_days: number }) =>
    request<ShareLink & { token: string }>('/share-links', jsonInit('POST', body)),
  revokeShareLink: (id: number) => request<void>(`/share-links/${id}`, { method: 'DELETE' }),

  // Fault repair workflow
  parkFaults: (parkId: string, status?: FaultStatus) =>
    request<FaultsList>(
      `/parks/${encodeURIComponent(parkId)}/faults${status ? `?status=${encodeURIComponent(status)}` : ''}`,
    ),
  updateFault: (id: number, body: FaultUpdate) =>
    request<PanelFault>(`/faults/${id}`, jsonInit('PATCH', body)),
  faultPhotos: (faultId: number) => request<FaultPhoto[]>(`/faults/${faultId}/photos`),
  uploadFaultPhoto: (faultId: number, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<FaultPhoto>(`/faults/${faultId}/photos`, { method: 'POST', body: form })
  },
  deleteFaultPhoto: (faultId: number, photoId: number) =>
    request<void>(`/faults/${faultId}/photos/${photoId}`, { method: 'DELETE' }),
  /** <img src> for a proof photo — images can't send headers, so the key rides the query. */
  faultPhotoUrl: (faultId: number, photoId: number) =>
    `${API_BASE}/faults/${faultId}/photos/${photoId}${authQuery('?')}`,
  workOrders: async (
    parkId: string,
    format: WorkOrderFormat,
    filters: WorkOrderFilters = {},
  ): Promise<Blob> => {
    const key = storedCredential()
    const res = await fetch(
      `${API_BASE}/parks/${encodeURIComponent(parkId)}/work-orders?${workOrdersQuery(format, filters)}`,
      { headers: key ? { Authorization: `Bearer ${key}` } : {} },
    )
    if (!res.ok) {
      const body = await res.text()
      throw new ApiError(res.status, body)
    }
    return res.blob()
  },
}
