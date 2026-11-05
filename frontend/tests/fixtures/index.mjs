/**
 * API fixtures in SolarPulseAI's response shapes (see src/lib/api.types.pending.ts). They reproduce the mocked
 * data behind docs/solardoctor/design/reference/*.webp so the visual harness compares like with like. All values
 * are fake demo data. Like the original mock, the forecast series is the same for every plant (scaled for the
 * 120 kW rooftop), which is why the 50 MW plant's chart looks flat in the references.
 */

export const NOW = "2026-11-04T11:30:00Z";

const base = {
  created_at: "2026-10-01T09:00:00Z",
  updated_at: "2026-10-01T09:00:00Z",
};

export const plants = [
  {
    id: 1,
    name: "Bhadla Block C",
    location: "Jodhpur, Rajasthan",
    latitude: 27.539,
    longitude: 71.915,
    timezone: "Asia/Kolkata",
    capacity_kw: 50000,
    inverter_capacity_kw: 45000,
    module_count: 92000,
    is_active: true,
    ...base,
  },
  {
    id: 2,
    name: "PCCoE Rooftop",
    location: "Pune, Maharashtra",
    latitude: 18.652,
    longitude: 73.761,
    timezone: "Asia/Kolkata",
    capacity_kw: 120,
    inverter_capacity_kw: 100,
    module_count: 220,
    is_active: true,
    ...base,
  },
  {
    id: 3,
    name: "Pavagada Unit 4",
    location: "Tumakuru, Karnataka",
    latitude: 14.099,
    longitude: 77.283,
    timezone: "Asia/Kolkata",
    capacity_kw: 25000,
    inverter_capacity_kw: 22000,
    module_count: 46000,
    is_active: false,
    ...base,
  },
];

export const plantConfig = {
  id: 1,
  plant_id: 2,
  tilt: 18,
  azimuth: 180,
  efficiency: 0.205,
  soiling_threshold: 0.05,
  clipping_threshold: 0.98,
  forecast_horizon_minutes: 720,
  ...base,
};

const START = Date.parse("2026-11-04T11:30:00Z");
const STEP = 30 * 60 * 1000;
const iso = (i) => new Date(START + i * STEP).toISOString();
const r1 = (v) => Math.round(v * 10) / 10;
const sine = (i, peak) => peak * Math.sin((Math.PI * i) / 23);

/** 24 half-hour records, 11:30 to 23:00; actuals exist for the first 18. */
export const forecastRecords = Array.from({ length: 24 }, (_, i) => {
  const adapted = r1(sine(i, 108));
  return {
    id: 100 + i,
    plant_id: 2,
    forecast_time: iso(i),
    generated_at: NOW,
    predicted_power_kw: adapted,
    actual_power_kw: i < 18 ? r1(adapted * 0.9) : null,
    confidence_lower: r1(adapted * 0.9),
    confidence_upper: r1(adapted * 1.1),
    model_name: "hybrid-lgbm",
    model_version: "1.0",
    physics_power_kw: r1(sine(i, 112)),
    ml_power_kw: r1(adapted - 1.2),
  };
});

export const forecastSummary = {
  plant_id: 2,
  period_start: iso(0),
  period_end: iso(23),
  total_predicted_kwh: 642.1,
  total_actual_kwh: null,
  mean_absolute_error_kw: null,
  record_count: 24,
  model_name: "hybrid-lgbm",
};

const RISK = ["low", "medium", "high"];

export const probabilistic = {
  plant_id: 1,
  plant_name: "Bhadla Block C",
  capacity_kw: 50000,
  generated_at: NOW,
  horizon_minutes: 240,
  interval_minutes: 15,
  model_name: "quantile-lgbm",
  points: Array.from({ length: 24 }, (_, i) => {
    const p50 = sine(i, 102);
    const p10 = p50 * 0.8;
    const p90 = p50 * 1.15;
    return {
      forecast_time: iso(i),
      p10_kw: r1(p10),
      p50_kw: r1(p50),
      p90_kw: r1(p90),
      uncertainty_band_kw: r1((p90 - p10) / 2),
      relative_uncertainty_pct: 17.5,
      ramp_rate_kw_per_min: 0.4,
      ramp_rate_pct_per_min: 0.4,
      ramp_direction: "up",
      ramp_risk_level: RISK[i % 3],
      cloud_impact_factor: 0.12,
      bess_reserve_recommendation_kw: 5,
      reserve_action: "Hold 5 kW reserve",
    };
  }),
  summary: {
    max_ramp_rate_kw_per_min: 1.2,
    max_ramp_down_kw_per_min: -1.1,
    max_ramp_up_kw_per_min: 1.2,
    ramp_risk_score: 42,
    highest_risk_level: "high",
    high_risk_event_count: 3,
    critical_risk_event_count: 0,
    avg_uncertainty_band_kw: 18.0,
    recommended_bess_capacity_kw: 12.0,
    primary_action_advisory: "Keep 12 kW BESS headroom during afternoon ramp-down.",
  },
};

export const onlineStatus = {
  plant_id: "1",
  scaling_factor: 0.94,
  bias_kw: -0.4,
  samples_observed_today: 18,
  recent_rmse_kw: 5.4,
  status: "ADAPTING_SOILING_HAZE",
  last_updated: NOW,
  alpha: 0.2,
  decay_factor: 0.95,
};

export const alerts = [
  {
    id: 1,
    plant_id: 2,
    timestamp: NOW,
    alert_type: "UNDERPERFORMANCE",
    severity: "CRITICAL",
    message: "Output 14.2% below clear-sky expected for 3 consecutive hours on string S-04.",
    expected_power_kw: 92,
    actual_power_kw: 79,
    deviation_percent: -14.2,
    is_resolved: false,
    resolved_at: null,
    created_at: NOW,
  },
  {
    id: 2,
    plant_id: 1,
    timestamp: NOW,
    alert_type: "SOILING",
    severity: "WARNING",
    message: "Soiling ratio estimate fell to 0.93 — 21 days since last rain.",
    expected_power_kw: null,
    actual_power_kw: null,
    deviation_percent: -7.0,
    is_resolved: false,
    resolved_at: null,
    created_at: NOW,
  },
  {
    id: 3,
    plant_id: 2,
    timestamp: NOW,
    alert_type: "CLIPPING",
    severity: "INFO",
    message: "Inverter clipping active 11:40–13:10.",
    expected_power_kw: null,
    actual_power_kw: null,
    deviation_percent: null,
    is_resolved: true,
    resolved_at: NOW,
    created_at: NOW,
  },
];

export const weather = {
  latitude: 18.652,
  longitude: 73.761,
  location_name: "Pune",
  timezone_id: "Asia/Kolkata",
  fetched_at: NOW,
  source: "mock",
  current: {
    timestamp: NOW,
    temperature_c: 29.4,
    humidity_pct: 48,
    wind_speed_kph: 9.2,
    cloud_cover_pct: 12,
    uv_index: 7.0,
    irradiance_w_m2: 812,
    condition: "Clear",
    is_day: true,
  },
};

export const taxonomy = [];

/** Fake auth session used by the harness. */
export const loginResponse = {
  token: "fixture-token",
  refresh_token: "fixture-refresh",
  expires_at: "2099-01-01T00:00:00Z",
  user: { email: "parth@pccoe.in", role: "operator" },
};

/** Route table: [method, path regex, body]. Query strings are ignored. */
export const routes = [
  ["GET", /^\/api\/v1\/plants$/, () => plants],
  ["GET", /^\/api\/v1\/plants\/(\d+)$/, (m) => plants.find((p) => p.id === Number(m[1])) ?? plants[1]],
  ["GET", /^\/api\/v1\/plants\/\d+\/config$/, () => plantConfig],
  ["GET", /^\/api\/v1\/forecast\/\d+$/, () => forecastRecords],
  ["GET", /^\/api\/v1\/forecast\/\d+\/summary$/, () => forecastSummary],
  ["GET", /^\/api\/v1\/forecast\/\d+\/probabilistic$/, () => probabilistic],
  ["GET", /^\/api\/v1\/forecast\/\d+\/online-status$/, () => onlineStatus],
  ["GET", /^\/api\/v1\/alerts$/, () => alerts],
  ["GET", /^\/api\/v1\/weather\/\d+\/(current|forecast)$/, () => weather],
  ["GET", /^\/api\/v1\/diagnosis\/taxonomy$/, () => taxonomy],
  ["POST", /^\/api\/v1\/auth\/login$/, () => loginResponse],
  ["GET", /^\/api\/v1\/auth\/me$/, () => ({ mode: "users", kind: "user", role: "operator", user: loginResponse.user })],
];
