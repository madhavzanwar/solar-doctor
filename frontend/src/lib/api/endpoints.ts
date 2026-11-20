/**
 * Endpoint wrappers in SolarPulseAI's shapes. Response types come from ../api.types.ts until the backend
 * OpenAPI schema (src/lib/api/schema.d.ts) includes these routes; then swap the imports to `components["schemas"]`.
 */
import type {
  Alert,
  DiagnosisRequest,
  DiagnosisResponse,
  ForecastRecord,
  ForecastSummary,
  OnlineAdapterStatus,
  ParkFaultsResponse,
  ParkGrid,
  PeersResponse,
  PerformanceBaseline,
  PerformanceResponse,
  ScanResponse,
  Plant,
  PlantConfig,
  PlantCreate,
  ProbabilisticForecastResponse,
  RootCauseTaxonomyItem,
  WeatherData,
  InspectionRecord,
  WorkOrderRecord,
  WorkOrderCreateInput,
  WorkOrderUpdateInput,
  WorkOrderVerifyResult,
  RoiResponse,
  PlantRoiSettings,
  UserRecord,
  UserCreateInput,
  UserUpdateInput,
  AnomalyThresholdInput,
} from "../api.types";
import { ApiError } from "./errors";
import { apiFetch } from "./http";

// ── Plant endpoints ────────────────────────────────────────────────────────────

export const plantsApi = {
  list: () => apiFetch<Plant[]>("/api/v1/plants"),
  get: (id: number) => apiFetch<Plant>(`/api/v1/plants/${id}`),
  create: (data: PlantCreate) => 
    apiFetch<Plant>("/api/v1/plants", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: number, data: Partial<Plant>) =>
    apiFetch<Plant>(`/api/v1/plants/${id}`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  getConfig: (id: number) => apiFetch<PlantConfig>(`/api/v1/plants/${id}/config`),
  updateConfig: (id: number, data: Partial<PlantConfig>) =>
    apiFetch<PlantConfig>(`/api/v1/plants/${id}/config`, {
      method: "PUT",
      body: JSON.stringify(data),
    }),
  setAnomalyThreshold: (data: AnomalyThresholdInput) =>
    apiFetch<{ message: string }>("/api/v1/anomaly/threshold", {
      method: "POST",
      body: JSON.stringify(data),
    }),
};

// ── Forecast endpoints ─────────────────────────────────────────────────────────

export const forecastApi = {
  list: (plantId: number, limit = 48) =>
    apiFetch<ForecastRecord[]>(
      `/api/v1/forecast/${plantId}?limit=${limit}`
    ),
  /** Resolves to null when the plant has no forecasts yet (the API answers 404). */
  summary: (plantId: number) =>
    apiFetch<ForecastSummary>(`/api/v1/forecast/${plantId}/summary`).catch((err: unknown) => {
      if (err instanceof ApiError && err.status === 404) return null;
      throw err;
    }),
  generate: (plantId: number, horizonMinutes = 60) =>
    apiFetch<ForecastRecord>(
      `/api/v1/forecast/${plantId}/generate?horizon_minutes=${horizonMinutes}`,
      { method: "POST" }
    ),
  getProbabilistic: (plantId: number, horizonMinutes = 240, intervalMinutes = 15) =>
    apiFetch<ProbabilisticForecastResponse>(
      `/api/v1/forecast/${plantId}/probabilistic?horizon_minutes=${horizonMinutes}&interval_minutes=${intervalMinutes}`
    ),
  getOnlineStatus: (plantId: number | string) =>
    apiFetch<OnlineAdapterStatus>(`/api/v1/forecast/${plantId}/online-status`),
};

export const OPEN_ALERT_LIMIT = 500;

// ── Alert endpoints ────────────────────────────────────────────────────────────

export const alertsApi = {
  list: (plantId?: number, limit = 50) => {
    const qs = new URLSearchParams({ limit: String(limit) });
    if (plantId) qs.set("plant_id", String(plantId));
    return apiFetch<Alert[]>(`/api/v1/alerts?${qs}`);
  },
  /** Open (unresolved) alerts for one plant; the API caps a page at 500 and has no offset. */
  listOpen: (plantId: number, limit = OPEN_ALERT_LIMIT) =>
    apiFetch<Alert[]>(`/api/v1/alerts?plant_id=${plantId}&is_resolved=false&limit=${limit}`),
  resolve: (alertId: number) =>
    apiFetch<Alert>(`/api/v1/alerts/${alertId}/resolve`, {
      method: "PATCH",
    }),
};

// ── Diagnosis endpoints ────────────────────────────────────────────────────────

export const diagnosisApi = {
  getTaxonomy: () => apiFetch<RootCauseTaxonomyItem[]>("/api/v1/diagnosis/taxonomy"),
  diagnose: (data: DiagnosisRequest) =>
    apiFetch<DiagnosisResponse>("/api/v1/diagnosis/diagnose", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  diagnoseAlert: (alertId: number) =>
    apiFetch<DiagnosisResponse>(`/api/v1/diagnosis/alert/${alertId}`),
  listByPlant: (plantId: number, limit = 50) =>
    apiFetch<DiagnosisResponse[]>(`/api/v1/diagnosis/plant/${plantId}?limit=${limit}`),
};

// ── Weather endpoints ──────────────────────────────────────────────────────────

export const weatherApi = {
  current: (plantId: number) =>
    apiFetch<WeatherData>(`/api/v1/weather/${plantId}/current`),
  forecast: (plantId: number, days = 3) =>
    apiFetch<WeatherData>(`/api/v1/weather/${plantId}/forecast?days=${days}`),
};

// ── Physics deficit / performance endpoints ────────────────────────────────────

export interface PerformanceWindow {
  /** ISO timestamps (UTC). Omitted = backend default (last 7 days). Max window 92 days. */
  start?: string;
  end?: string;
  baseline?: PerformanceBaseline;
}

function windowQuery({ start, end, baseline }: PerformanceWindow): string {
  const qs = new URLSearchParams();
  if (start) qs.set("start", start);
  if (end) qs.set("end", end);
  if (baseline) qs.set("baseline", baseline);
  const s = qs.toString();
  return s ? `?${s}` : "";
}

export const performanceApi = {
  get: (plantId: number, w: PerformanceWindow = {}) =>
    apiFetch<PerformanceResponse>(`/api/v1/performance/${plantId}${windowQuery(w)}`),
  /** Persists alerts (operator+). Carries `qc_status`, which the GET response does not. */
  scan: (plantId: number, w: PerformanceWindow = {}) =>
    apiFetch<ScanResponse>(`/api/v1/performance/${plantId}/scan${windowQuery(w)}`, { method: "POST" }),
  peers: (stringId: number, w: Pick<PerformanceWindow, "start" | "end"> = {}) =>
    apiFetch<PeersResponse>(`/api/v1/strings/${stringId}/peers${windowQuery(w)}`),
};

// ── Park map endpoints (Axalon) ────────────────────────────────────────────────

export const parksApi = {
  grid: (parkId: string) => apiFetch<ParkGrid>(`/api/v1/park/${encodeURIComponent(parkId)}/grid`),
  faults: (parkId: string) => apiFetch<ParkFaultsResponse>(`/api/v1/parks/${encodeURIComponent(parkId)}/faults`),
};

// ── Inspections endpoints ──────────────────────────────────────────────────────

export const inspectionsApi = {
  list: (plantId?: number, limit = 50) => {
    const qs = new URLSearchParams({ limit: String(limit) });
    if (plantId) qs.set("plant_id", String(plantId));
    return apiFetch<InspectionRecord[]>(`/api/v1/inspections?${qs}`);
  },
  get: (id: string) => apiFetch<InspectionRecord>(`/api/v1/inspections/${id}`),
  create: async (formData: FormData): Promise<InspectionRecord> => {
    const res = await fetch("/api/v1/inspections", {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      const errJson = await res.json().catch(() => ({ detail: "Inspection upload failed" }));
      throw new Error(errJson.detail || "Inspection upload failed");
    }
    return res.json();
  },
};

// ── Work Orders endpoints ──────────────────────────────────────────────────────

export const workOrdersApi = {
  list: (params: { plant_id?: number; status?: string; assignee?: string; limit?: number } = {}) => {
    const qs = new URLSearchParams();
    if (params.plant_id) qs.set("plant_id", String(params.plant_id));
    if (params.status) qs.set("status", params.status);
    if (params.assignee) qs.set("assignee", params.assignee);
    if (params.limit) qs.set("limit", String(params.limit));
    const s = qs.toString();
    return apiFetch<WorkOrderRecord[]>(`/api/v1/work-orders${s ? `?${s}` : ""}`);
  },
  get: (id: number) => apiFetch<WorkOrderRecord>(`/api/v1/work-orders/${id}`),
  create: (data: WorkOrderCreateInput) =>
    apiFetch<WorkOrderRecord>("/api/v1/work-orders", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: number, data: WorkOrderUpdateInput) =>
    apiFetch<WorkOrderRecord>(`/api/v1/work-orders/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  verify: (id: number) =>
    apiFetch<WorkOrderVerifyResult>(`/api/v1/work-orders/${id}/verify`, {
      method: "POST",
    }),
};

// ── ROI & Cleaning Decision endpoints ──────────────────────────────────────────

export const roiApi = {
  get: (plantId: number) => apiFetch<RoiResponse>(`/api/v1/roi/${plantId}`),
  updateSettings: (plantId: number, settings: Partial<PlantRoiSettings>) =>
    apiFetch<PlantRoiSettings>(`/api/v1/roi/${plantId}/settings`, {
      method: "PUT",
      body: JSON.stringify(settings),
    }),
};

// ── Users endpoints ─────────────────────────────────────────────────────────────

export const usersApi = {
  list: () => apiFetch<UserRecord[]>("/api/v1/users"),
  create: (data: UserCreateInput) => 
    apiFetch<UserRecord>("/api/v1/users", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  update: (id: number, data: UserUpdateInput) => 
    apiFetch<UserRecord>(`/api/v1/users/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  delete: (id: number) => 
    apiFetch<void>(`/api/v1/users/${id}`, {
      method: "DELETE",
    }),
};