/** Response/request types for the physics endpoints, taken from the generated OpenAPI schema (`npm run gen:api`). */
import type { components } from "./api/schema";

type S = components["schemas"];

export type Plant = S["PlantResponse"];
export type PlantCreate = Pick<S["PlantCreate"], "name" | "latitude" | "longitude" | "capacity_kw" | "inverter_capacity_kw"> &
  Partial<S["PlantCreate"]>;
export type PlantConfig = S["PlantConfigResponse"];
export type ForecastRecord = S["ForecastResponse"];
export type ForecastSummary = S["ForecastSummary"];
export type ProbabilisticForecastPoint = S["ProbabilisticForecastPoint"];
export type RampRiskSummary = S["RampRiskSummarySchema"];
export type ProbabilisticForecastResponse = S["ProbabilisticForecastResponse"];
export type OnlineAdapterStatus = S["OnlineAdapterStatusResponse"];
export type Alert = S["AlertResponse"];
export type TechnicianStep = S["TechnicianStep"];
export type DiagnosisResponse = S["DiagnosisResponse"];
export type DiagnosisRequest = Pick<S["DiagnosisRequest"], "plant_id"> & Partial<S["DiagnosisRequest"]>;
export type RootCauseTaxonomyItem = S["RootCauseTaxonomyItem"];

export type {
  DeficitEvent,
  DeficitSeverity,
  GridPanel,
  GridPanelDetection,
  HourlyPoint,
  ParkFault,
  ParkFaultsResponse,
  ParkGrid,
  PeersResponse,
  PeerValue,
  PerformanceAlert,
  PerformanceBaseline,
  PerformanceResponse,
  QcStatus,
  ScanResponse,
  SoilingAnalytics,
  WeatherData,
  WeatherPoint,
} from "./api.types.pending";
