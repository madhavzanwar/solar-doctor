/**
 * Endpoint wrappers in SolarPulseAI's shapes. Response types come from ../api.types.pending.ts until the backend
 * OpenAPI schema (src/lib/api/schema.d.ts) includes these routes; then swap the imports to `components["schemas"]`.
 */
import type {
  Alert,
  DiagnosisRequest,
  DiagnosisResponse,
  ForecastRecord,
  ForecastSummary,
  OnlineAdapterStatus,
  Plant,
  PlantConfig,
  PlantCreate,
  ProbabilisticForecastResponse,
  RootCauseTaxonomyItem,
  WeatherData,
} from "../api.types.pending";
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
  getConfig: (id: number) => apiFetch<PlantConfig>(`/api/v1/plants/${id}/config`),
};

// ── Forecast endpoints ─────────────────────────────────────────────────────────

export const forecastApi = {
  list: (plantId: number, limit = 48) =>
    apiFetch<ForecastRecord[]>(
      `/api/v1/forecast/${plantId}?limit=${limit}`
    ),
  summary: (plantId: number) =>
    apiFetch<ForecastSummary>(`/api/v1/forecast/${plantId}/summary`),
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

// ── Alert endpoints ────────────────────────────────────────────────────────────

export const alertsApi = {
  list: (plantId?: number, limit = 50) => {
    const qs = new URLSearchParams({ limit: String(limit) });
    if (plantId) qs.set("plant_id", String(plantId));
    return apiFetch<Alert[]>(`/api/v1/alerts?${qs}`);
  },
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
