/**
 * PENDING HAND-WRITTEN TYPES. Remove this file once the backend OpenAPI schema (frontend/openapi.json ->
 * src/lib/api/schema.d.ts via `npm run gen:api`) contains /api/v1/plants, /forecast/*, /alerts, /diagnosis/* and
 * /weather/* (Phase E, sd-physics). These mirror SolarPulseAI's response shapes (MIT) and the fixtures in
 * tests/fixtures/. `source` is added so simulated data can be badged (DESIGN.md, Phase F).
 */

export interface Plant {
  id: number;
  name: string;
  location: string | null;
  latitude: number;
  longitude: number;
  timezone: string;
  capacity_kw: number;
  inverter_capacity_kw: number;
  module_count: number | null;
  is_active: boolean;
  /** Data provenance, e.g. "SIMULATED", "PVDAQ", "LIVE". Not in SolarPulseAI; added for SolarDoctor. */
  source?: string | null;
  created_at: string;
  updated_at: string;
}

export interface PlantCreate {
  name: string;
  location?: string;
  latitude: number;
  longitude: number;
  timezone?: string;
  capacity_kw: number;
  inverter_capacity_kw: number;
  module_count?: number;
}

export interface PlantConfig {
  id: number;
  plant_id: number;
  tilt: number;
  azimuth: number;
  efficiency: number;
  soiling_threshold: number;
  clipping_threshold: number;
  forecast_horizon_minutes: number;
  created_at: string;
  updated_at: string;
}

export interface ForecastRecord {
  id: number;
  plant_id: number;
  forecast_time: string;
  generated_at: string;
  predicted_power_kw: number;
  actual_power_kw: number | null;
  confidence_lower: number | null;
  confidence_upper: number | null;
  model_name: string;
  model_version: string;
  physics_power_kw: number | null;
  ml_power_kw: number | null;
  source?: string | null;
}

export interface ForecastSummary {
  plant_id: number;
  period_start: string;
  period_end: string;
  total_predicted_kwh: number;
  total_actual_kwh: number | null;
  mean_absolute_error_kw: number | null;
  record_count: number;
  model_name: string;
}

export interface ProbabilisticForecastPoint {
  forecast_time: string;
  p10_kw: number;
  p50_kw: number;
  p90_kw: number;
  uncertainty_band_kw: number;
  relative_uncertainty_pct: number;
  ramp_rate_kw_per_min: number;
  ramp_rate_pct_per_min: number;
  ramp_direction: "up" | "down" | "stable";
  ramp_risk_level: "low" | "medium" | "high" | "critical";
  cloud_impact_factor: number;
  bess_reserve_recommendation_kw: number;
  reserve_action: string;
}

export interface RampRiskSummary {
  max_ramp_rate_kw_per_min: number;
  max_ramp_down_kw_per_min: number;
  max_ramp_up_kw_per_min: number;
  ramp_risk_score: number;
  highest_risk_level: "low" | "medium" | "high" | "critical";
  high_risk_event_count: number;
  critical_risk_event_count: number;
  avg_uncertainty_band_kw: number;
  recommended_bess_capacity_kw: number;
  primary_action_advisory: string;
}

export interface ProbabilisticForecastResponse {
  plant_id: number;
  plant_name: string;
  capacity_kw: number;
  generated_at: string;
  horizon_minutes: number;
  interval_minutes: number;
  model_name: string;
  points: ProbabilisticForecastPoint[];
  summary: RampRiskSummary;
}

export interface OnlineAdapterStatus {
  plant_id: string;
  scaling_factor: number;
  bias_kw: number;
  samples_observed_today: number;
  recent_rmse_kw: number;
  status: "BASELINE_OPTIMAL" | "ADAPTING_SOILING_HAZE" | "ADAPTING_ABOVE_NWP" | string;
  last_updated: string | null;
  alpha: number;
  decay_factor: number;
}

export interface Alert {
  id: number;
  plant_id: number;
  timestamp: string;
  alert_type: string;
  severity: string;
  message: string;
  expected_power_kw: number | null;
  actual_power_kw: number | null;
  deviation_percent: number | null;
  is_resolved: boolean;
  source?: string | null;
  resolved_at: string | null;
  created_at: string;
}

export interface TechnicianStep {
  step_number: number;
  action: string;
  required_tools: string[];
  safety_note?: string | null;
}

export interface DiagnosisResponse {
  id?: number | null;
  plant_id: number;
  plant_name?: string | null;
  alert_id?: number | null;
  timestamp: string;
  root_cause_category: string;
  root_cause_title: string;
  confidence_score: number;
  inverter_error_code?: string | null;
  estimated_loss_kw: number;
  financial_impact_per_day: number;
  urgency_level: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | string;
  summary: string;
  root_cause_details: string;
  technician_steps: TechnicianStep[];
  safety_warning?: string | null;
  preventative_advice?: string | null;
  telemetry_evidence?: Record<string, unknown> | null;
  created_at: string;
}

export interface DiagnosisRequest {
  plant_id: number;
  alert_id?: number;
  inverter_error_code?: string;
  expected_power_kw?: number;
  actual_power_kw?: number;
  irradiance_w_m2?: number;
  temperature_c?: number;
  module_temp_c?: number;
  days_since_cleaning?: number;
  notes?: string;
}

export interface RootCauseTaxonomyItem {
  category: string;
  title: string;
  common_error_codes: string[];
  description: string;
  typical_urgency: string;
}

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
