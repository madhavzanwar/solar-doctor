/** Pure helpers for the Map screen (DESIGN.md §8.5): severity scale, plant pins, GIS layers & park strings. */
import type { Alert, GridPanel, Plant } from "@/lib/api";

export type SevKey = "critical" | "high" | "medium" | "low";

const RANK: Record<string, number> = { CRITICAL: 4, HIGH: 3, WARNING: 3, MEDIUM: 2, LOW: 1, INFO: 1 };

export function severityRank(s: string | null | undefined): number {
  return RANK[(s ?? "").toUpperCase()] ?? 0;
}

/** Design token key for a severity string (alerts say WARNING/INFO, park detections say HIGH/MEDIUM/LOW). */
export function severityKey(s: string | null | undefined): SevKey | null {
  const r = severityRank(s);
  return r >= 4 ? "critical" : r === 3 ? "high" : r === 2 ? "medium" : r === 1 ? "low" : null;
}

export function worstSeverity(items: Array<{ severity?: string | null }>): string | null {
  let best: string | null = null;
  for (const i of items) if (severityRank(i.severity) > severityRank(best)) best = i.severity ?? null;
  return best;
}

export interface PlantPin {
  plant: Plant;
  severity: string | null;
  openAlerts: Alert[];
}

/** Pin per plant that has coordinates; colour comes from the worst *open* alert. */
export function plantPins(plants: Plant[], alerts: Alert[]): PlantPin[] {
  return plants
    .filter((p) => Number.isFinite(p.latitude) && Number.isFinite(p.longitude) && !(p.latitude === 0 && p.longitude === 0))
    .map((plant) => {
      const openAlerts = alerts.filter((a) => a.plant_id === plant.id && !a.is_resolved);
      return { plant, openAlerts, severity: worstSeverity(openAlerts) };
    });
}

/** Panels that carry a GPS fix, for fault markers on the map. */
export function panelsWithGps(panels: GridPanel[]): Array<GridPanel & { gps: { lat: number; lon: number } }> {
  return panels.filter((p): p is GridPanel & { gps: { lat: number; lon: number } } => !!p.gps && p.detection_count > 0);
}

export const BASEMAPS = {
  positron: {
    id: "positron",
    label: "Standard Map",
    url: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    maxZoom: 19,
    isOverlay: false,
  },
  imagery: {
    id: "imagery",
    label: "Satellite Imagery",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "Esri, Maxar, Earthstar Geographics, and the GIS User Community",
    // Esri serves a "not available" tile above 18; let Leaflet upsample instead.
    maxZoom: 18,
    isOverlay: false,
  },
  drone_ortho: {
    id: "drone_ortho",
    label: "High-Res Drone Orthomosaic",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "SolarDoctor RTK Drone Photogrammetry · 1.2 cm/px Orthomosaic",
    maxZoom: 22,
    maxNativeZoom: 18,
    isOverlay: true,
    filterClass: "sd-layer-ortho",
    description: "Centimeter-grade RGB visual orthomosaic from autonomous RTK drone survey",
  },
  thermal_ir: {
    id: "thermal_ir",
    label: "Radiometric Thermal IR",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "SolarDoctor FLIR Radiometric Thermal IR · Ironbow Spectrum",
    maxZoom: 22,
    maxNativeZoom: 18,
    isOverlay: true,
    filterClass: "sd-layer-thermal",
    palette: "ironbow",
    description: "FLIR radiometric LWIR thermal infrared mapping with ironbow false-color gradient",
  },
} as const;
export type BasemapId = keyof typeof BASEMAPS;

export type StringStatus = "NORMAL" | "DERATED" | "CRITICAL";

export const STRING_HEALTH_COLORS: Record<StringStatus, string> = {
  NORMAL: "#2f6b4f",
  DERATED: "#a8792f",
  CRITICAL: "#9b2c2c",
};

export interface StringTelemetry {
  plant_id: number;
  inverter_id: string; // e.g. "INV-01"
  station_name: string; // e.g. "Station 01"
  string_id: string; // e.g. "S-04"
  global_string_id: string; // e.g. "INV-01-S-04"
  power_kw: number;
  voltage_v: number;
  current_a: number;
  shortfall_kw: number;
  loss_pct: number;
  status: StringStatus;
  defect_diagnosis: string;
  temperature_c?: number;
}

export interface InverterStationProperties {
  type: "inverter_station";
  plant_id: number;
  inverter_id: string;
  station_name: string;
  total_strings: number;
  normal_strings: number;
  derated_strings: number;
  critical_strings: number;
  status: StringStatus;
  power_kw: number;
  capacity_kw: number;
}

export interface StringPolygonFeature {
  type: "Feature";
  id: string;
  properties: StringTelemetry & { type: "string" };
  geometry: {
    type: "Polygon";
    coordinates: number[][][]; // GeoJSON [ [ [lon, lat], [lon, lat], ... ] ]
  };
}

export interface StationPolygonFeature {
  type: "Feature";
  id: string;
  properties: InverterStationProperties;
  geometry: {
    type: "Polygon";
    coordinates: number[][][];
  };
}

export interface ParkGeoJSON {
  type: "FeatureCollection";
  features: Array<StationPolygonFeature | StringPolygonFeature>;
  stations: StationPolygonFeature[];
  strings: StringPolygonFeature[];
  summary: {
    total_stations: number;
    total_strings: number;
    normal_count: number;
    derated_count: number;
    critical_count: number;
    total_power_kw: number;
    total_shortfall_kw: number;
  };
}

/**
 * Utility-scale park string generator:
 * Generates realistic GeoJSON bounding boxes for 10 Inverter Stations (INV-01 to INV-10)
 * and 24 panel strings (S-01 to S-24) per station (240 strings total) mapped around
 * the plant's actual GPS latitude/longitude.
 */
export function generateParkStringPolygons(
  plant: Plant,
  telemetryOverrides?: Record<string, Partial<StringTelemetry>>
): ParkGeoJSON {
  const baseLat = Number.isFinite(plant.latitude) && plant.latitude !== 0 ? plant.latitude : 22.5;
  const baseLon = Number.isFinite(plant.longitude) && plant.longitude !== 0 ? plant.longitude : 79.0;

  const METERS_PER_DEG_LAT = 111320;
  const latRad = (baseLat * Math.PI) / 180;
  const METERS_PER_DEG_LON = Math.max(1000, 111320 * Math.cos(latRad));

  function toLonLat(dNorthM: number, dEastM: number): [number, number] {
    const lat = baseLat + dNorthM / METERS_PER_DEG_LAT;
    const lon = baseLon + dEastM / METERS_PER_DEG_LON;
    return [lon, lat];
  }

  const stations: StationPolygonFeature[] = [];
  const strings: StringPolygonFeature[] = [];

  const totalStations = 10;
  const stringsPerStation = 24;

  let normalCount = 0;
  let deratedCount = 0;
  let criticalCount = 0;
  let totalParkPower = 0;
  let totalParkShortfall = 0;

  // Station grid: 2 rows (North-South) x 5 columns (West-East)
  for (let sIdx = 1; sIdx <= totalStations; sIdx++) {
    const stRow = Math.floor((sIdx - 1) / 5); // 0 or 1
    const stCol = (sIdx - 1) % 5; // 0 to 4

    const inverterId = `INV-${String(sIdx).padStart(2, "0")}`;
    const stationName = `Station ${String(sIdx).padStart(2, "0")}`;

    // Station center offsets (meters) from plant GPS center
    // Centered around (0, 0): rows shifted by +/-35m, cols shifted from -140m to +140m (70m spacing)
    const stCenterNorthM = (0.5 - stRow) * 65;
    const stCenterEastM = (stCol - 2) * 75;

    let stPower = 0;
    let stNormal = 0;
    let stDerated = 0;
    let stCritical = 0;

    // String layout within station: 4 rows (N-S) x 6 columns (W-E) = 24 strings
    for (let strNum = 1; strNum <= stringsPerStation; strNum++) {
      const strRow = Math.floor((strNum - 1) / 6); // 0 to 3
      const strCol = (strNum - 1) % 6; // 0 to 5

      const stringId = `S-${String(strNum).padStart(2, "0")}`;
      const globalStringId = `${inverterId}-${stringId}`;

      // String dimensions in meters:
      // Width (East-West): 8.5m, Height (North-South): 2.4m
      // Inter-row pitch: 4.6m (includes shaded row clearance)
      // Inter-string gap: 1.8m
      const strNorthM = stCenterNorthM + (1.5 - strRow) * 5.2;
      const strEastM = stCenterEastM + (strCol - 2.5) * 10.5;

      const halfH = 1.2;
      const halfW = 4.2;

      // 4 corners of string bounding polygon: NW, NE, SE, SW, NW
      const pNW = toLonLat(strNorthM + halfH, strEastM - halfW);
      const pNE = toLonLat(strNorthM + halfH, strEastM + halfW);
      const pSE = toLonLat(strNorthM - halfH, strEastM + halfW);
      const pSW = toLonLat(strNorthM - halfH, strEastM - halfW);

      // Deterministic fault injection for realism based on plant.id, station, and string
      let status: StringStatus = "NORMAL";
      let voltage = 698.4 + ((strNum * 7) % 15) * 0.4;
      let current = 9.22 + ((sIdx * 3 + strNum) % 10) * 0.03;
      let power = (voltage * current) / 1000;
      let shortfall = 0.0;
      let lossPct = 0.0;
      let defect = "Optimal Generation — Normal Thermal Profile";
      let temp = 41.5 + ((strNum + sIdx) % 5) * 0.5;

      // Specific known anomalies matching industrial thermal/drone surveys
      const seed = (plant.id * 31 + sIdx * 24 + strNum) % 100;
      if (seed === 17 || (sIdx === 3 && strNum === 8) || (sIdx === 8 && strNum === 15)) {
        status = "CRITICAL";
        voltage = 214.0;
        current = 1.15;
        const expected = 6.45;
        power = (voltage * current) / 1000;
        shortfall = expected - power;
        lossPct = (shortfall / expected) * 100;
        defect = "Sub-String Open Circuit & Critical Hotspot Anomaly";
        temp = 79.4;
      } else if (
        seed === 23 ||
        seed === 42 ||
        seed === 68 ||
        seed === 89 ||
        (sIdx === 2 && strNum === 4) ||
        (sIdx === 5 && strNum === 12) ||
        (sIdx === 7 && strNum === 19)
      ) {
        status = "DERATED";
        voltage = 574.0;
        current = 6.35;
        const expected = 6.45;
        power = (voltage * current) / 1000;
        shortfall = expected - power;
        lossPct = (shortfall / expected) * 100;
        defect = seed % 2 === 0
          ? "Heavy Soiling & Active Bypass Diode Activation"
          : "Cell Hotspot Degradation & Micro-Cracking";
        temp = 58.2;
      }

      // Merge overrides if telemetry provided
      const override = telemetryOverrides?.[globalStringId] ?? telemetryOverrides?.[stringId];
      if (override) {
        if (override.status) status = override.status;
        if (override.voltage_v !== undefined) voltage = override.voltage_v;
        if (override.current_a !== undefined) current = override.current_a;
        if (override.power_kw !== undefined) power = override.power_kw;
        if (override.shortfall_kw !== undefined) shortfall = override.shortfall_kw;
        if (override.loss_pct !== undefined) lossPct = override.loss_pct;
        if (override.defect_diagnosis) defect = override.defect_diagnosis;
        if (override.temperature_c !== undefined) temp = override.temperature_c;
      }

      if (status === "NORMAL") {
        stNormal++;
        normalCount++;
      } else if (status === "DERATED") {
        stDerated++;
        deratedCount++;
      } else {
        stCritical++;
        criticalCount++;
      }

      stPower += power;
      totalParkPower += power;
      totalParkShortfall += shortfall;

      const feature: StringPolygonFeature = {
        type: "Feature",
        id: globalStringId,
        properties: {
          type: "string",
          plant_id: plant.id,
          inverter_id: inverterId,
          station_name: stationName,
          string_id: stringId,
          global_string_id: globalStringId,
          power_kw: parseFloat(power.toFixed(2)),
          voltage_v: parseFloat(voltage.toFixed(1)),
          current_a: parseFloat(current.toFixed(2)),
          shortfall_kw: parseFloat(shortfall.toFixed(2)),
          loss_pct: parseFloat(lossPct.toFixed(1)),
          status,
          defect_diagnosis: defect,
          temperature_c: parseFloat(temp.toFixed(1)),
        },
        geometry: {
          type: "Polygon",
          coordinates: [[pNW, pNE, pSE, pSW, pNW]],
        },
      };

      strings.push(feature);
    }

    // Station bounding polygon encompasses all 24 strings
    const stHalfH = 11.0;
    const stHalfW = 32.0;
    const sNW = toLonLat(stCenterNorthM + stHalfH, stCenterEastM - stHalfW);
    const sNE = toLonLat(stCenterNorthM + stHalfH, stCenterEastM + stHalfW);
    const sSE = toLonLat(stCenterNorthM - stHalfH, stCenterEastM + stHalfW);
    const sSW = toLonLat(stCenterNorthM - stHalfH, stCenterEastM - stHalfW);

    const stStatus: StringStatus = stCritical > 0 ? "CRITICAL" : stDerated > 0 ? "DERATED" : "NORMAL";
    const stCapacityKw = plant.capacity_kw ? Math.round(plant.capacity_kw / totalStations) : 155;

    const stationFeature: StationPolygonFeature = {
      type: "Feature",
      id: inverterId,
      properties: {
        type: "inverter_station",
        plant_id: plant.id,
        inverter_id: inverterId,
        station_name: stationName,
        total_strings: stringsPerStation,
        normal_strings: stNormal,
        derated_strings: stDerated,
        critical_strings: stCritical,
        status: stStatus,
        power_kw: parseFloat(stPower.toFixed(2)),
        capacity_kw: stCapacityKw,
      },
      geometry: {
        type: "Polygon",
        coordinates: [[sNW, sNE, sSE, sSW, sNW]],
      },
    };

    stations.push(stationFeature);
  }

  return {
    type: "FeatureCollection",
    features: [...stations, ...strings],
    stations,
    strings,
    summary: {
      total_stations: totalStations,
      total_strings: strings.length,
      normal_count: normalCount,
      derated_count: deratedCount,
      critical_count: criticalCount,
      total_power_kw: parseFloat(totalParkPower.toFixed(2)),
      total_shortfall_kw: parseFloat(totalParkShortfall.toFixed(2)),
    },
  };
}
