/**
 * STILL PENDING (hand-written): the backend declares the weather endpoints as an untyped object
 * (`/api/v1/weather/{plant_id}/current|forecast` -> `{[key: string]: unknown}`), so their shape is mirrored from
 * SolarPulseAI and tests/fixtures. Delete this file once the backend gives them a response model. Everything else
 * that used to live here now comes from the schema (see api.types.ts).
 */

export interface WeatherPoint {
  timestamp: string;
  temperature_c: number;
  humidity_pct: number;
  wind_speed_kph: number;
  cloud_cover_pct: number;
  uv_index: number;
  irradiance_w_m2: number;
  condition: string;
  is_day: boolean;
}

export interface WeatherData {
  latitude: number;
  longitude: number;
  location_name: string;
  timezone_id: string;
  fetched_at: string;
  source: string;
  current: WeatherPoint;
  hourly_forecast?: WeatherPoint[];
}

/**
 * Physics deficit endpoints (`/api/v1/performance/*`, `/api/v1/strings/{id}/peers`) and the park map endpoints
 * (`/api/v1/park/{id}/grid`, `/api/v1/parks/{id}/faults`). Hand-written from backend/solardoctor/physics/schemas/
 * performance.py and docs/solardoctor/interfaces/physics-deficit.md because the committed openapi.json predates them.
 * Swap to `components["schemas"]` after the next `npm run gen:api` with a fresh openapi.json.
 */
export type PerformanceBaseline = "clearsky" | "pvwatts" | "hybrid";
export type DeficitSeverity = "CRITICAL" | "WARNING" | "INFO";

export interface HourlyPoint {
  ts: string;
  expected_kw: number | null;
  actual_kw: number | null;
  pi: number | null;
  clear: boolean;
  usable: boolean;
  source: string;
}

export interface DeficitEvent {
  scope: "plant" | "inverter" | "string";
  scope_id: number | null;
  name: string;
  severity: DeficitSeverity;
  start: string;
  end: string;
  pi_median: number;
  expected_kw_mean: number;
  actual_kw_mean: number;
  deviation_percent: number;
  clear_hours: number;
  peer_z: number | null;
  evidence: Record<string, unknown>;
}

export interface SoilingAnalytics {
  status: "ok" | "insufficient_data" | "unavailable";
  method: "rdtools_srr" | "pvlib_kimber" | "none" | "unavailable";
  label: "measured" | "modelled" | "none";
  days_with_data?: number;
  reason?: string;
  note?: string;
  day?: string;
  soiling_ratio_p50?: number;
  soiling_ratio_latest?: number;
  soiling_ratio_ci?: [number, number];
  soiling_loss_rate_per_day?: number;
  soiling_loss_rate_pct_per_day?: number;
  /** ISO dates: cleaning intervals for rdtools_srr, rain resets for pvlib_kimber. */
  cleaning_events?: string[];
  days?: number;
}

export interface PerformanceAlert {
  id: number;
  plant_id: number;
  severity: string;
  message: string;
  scope?: string;
  inverter_id?: number | null;
  string_id?: number | null;
  is_resolved: boolean;
}

export interface PerformanceResponse {
  plant_id: number;
  baseline: string;
  start: string;
  end: string;
  status: "ok" | "no_telemetry";
  data_source: string | null;
  series: HourlyPoint[];
  events: DeficitEvent[];
  open_alerts: PerformanceAlert[];
  soiling: SoilingAnalytics | null;
  degradation: Record<string, unknown> | null;
  qc: Record<string, unknown>;
  provenance: Record<string, number>;
}

export type QcStatus = "ok" | "time_offset_suspected" | "irradiance_unverified";

export interface ScanResponse {
  status: "ok" | "no_telemetry" | "baseline_unsupported_for_trackers";
  qc_status: QcStatus | null;
  clock_offset_min: number | null;
  baseline: string | null;
  data_source: string | null;
  events: DeficitEvent[];
  alert_ids: number[];
  qc: Record<string, unknown>;
  provenance: Record<string, number>;
}

export interface PeerValue {
  string_id: number;
  name: string;
  normalised_yield: number;
  peer_z: number | null;
  clear_hours: number;
}

export interface PeersResponse {
  string_id: number;
  plant_id: number;
  start: string;
  end: string;
  status: "ok" | "no_telemetry" | "no_clear_hours_for_string";
  normalised_yield: number | null;
  plant_median: number | null;
  peer_z: number | null;
  peers: PeerValue[];
}

export interface GridPanelDetection {
  class: string | null;
  confidence: number | null;
  severity: string | null;
  thermal_filename: string | null;
}

export interface GridPanel {
  panel_id: string;
  row: number;
  col: number;
  worst_severity: string | null;
  detection_count: number;
  detections: GridPanelDetection[];
  gps: { lat: number; lon: number } | null;
}

export interface ParkGrid {
  park_id: string;
  inspection_id: string | null;
  rows: number;
  cols: number;
  panels: GridPanel[];
}

export interface ParkFault {
  id: number;
  park_id: string | null;
  panel_id: string | null;
  severity: string | null;
  status: string | null;
  occurrences: number | null;
  assignee: string | null;
  due_date: string | null;
  priority: string | null;
}

export interface ParkFaultsResponse {
  park_id: string;
  total: number;
  faults: ParkFault[];
}
