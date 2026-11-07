/** Pure helpers for the Map screen (DESIGN.md §8.5): severity scale and plant pin data. */
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
    label: "Map",
    url: "https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png",
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/attributions">CARTO</a>',
    maxZoom: 19,
  },
  imagery: {
    label: "Imagery",
    url: "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    attribution: "Imagery &copy; Esri",
    // Esri serves a "not available" tile above 18; let Leaflet upsample instead.
    maxZoom: 18,
  },
} as const;
export type BasemapId = keyof typeof BASEMAPS;
