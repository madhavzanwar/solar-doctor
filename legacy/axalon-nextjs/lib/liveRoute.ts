// website/nextjs/lib/liveRoute.ts
// Pure helpers for drawing the staged (planned) route on the Live Ops map —
// kept out of LiveMap.tsx so they can be tested without Leaflet.

import type { PlannedPoint } from "@/lib/missionToWaypoints";

export type LatLngTuple = [number, number];

export interface RouteMarker {
  latlng: LatLngTuple;
  label: string;
  kind: "start" | "waypoint" | "end";
}

/** Past this many points, numbering every waypoint turns the map into noise. */
export const MAX_NUMBERED_WAYPOINTS = 60;

export function routeLatLngs(route: PlannedPoint[]): LatLngTuple[] {
  return route
    .filter((p) => Number.isFinite(p.lat) && Number.isFinite(p.lon))
    .map((p) => [p.lat, p.lon] as LatLngTuple);
}

/** [[south, west], [north, east]], or null when there is nothing to frame. */
export function routeBounds(route: PlannedPoint[]): [LatLngTuple, LatLngTuple] | null {
  const pts = routeLatLngs(route);
  if (pts.length === 0) return null;
  const lats = pts.map((p) => p[0]);
  const lons = pts.map((p) => p[1]);
  return [
    [Math.min(...lats), Math.min(...lons)],
    [Math.max(...lats), Math.max(...lons)],
  ];
}

/**
 * Start ("S") and end ("E") markers, with the waypoints between numbered by
 * their 1-based position in the upload order — only while the route is short
 * enough for the numbers to be legible.
 */
export function routeMarkers(
  route: PlannedPoint[],
  maxNumbered: number = MAX_NUMBERED_WAYPOINTS,
): RouteMarker[] {
  const pts = routeLatLngs(route);
  if (pts.length === 0) return [];
  const last = pts.length - 1;
  const numbered = pts.length <= maxNumbered;
  const markers: RouteMarker[] = [];
  pts.forEach((latlng, i) => {
    if (i === 0) markers.push({ latlng, label: "S", kind: "start" });
    else if (i === last) markers.push({ latlng, label: "E", kind: "end" });
    else if (numbered) markers.push({ latlng, label: String(i + 1), kind: "waypoint" });
  });
  return markers;
}

/**
 * Frame the route only when it first appears and the drone isn't reporting a
 * position yet — once telemetry flows, the map follows the drone instead.
 */
export function shouldFitToRoute(state: {
  routeLength: number;
  hasTelemetry: boolean;
  alreadyFitted: boolean;
}): boolean {
  return state.routeLength > 0 && !state.hasTelemetry && !state.alreadyFitted;
}
