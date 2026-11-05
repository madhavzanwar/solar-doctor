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
