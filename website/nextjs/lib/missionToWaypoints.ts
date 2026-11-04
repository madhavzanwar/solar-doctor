// website/nextjs/lib/missionToWaypoints.ts
// Adapts mission-planner waypoints into the UPLOAD_MISSION command payload the
// drone agent expects ({seq, lat, lon, alt_m}). Keeps the live-ops surface
// decoupled from the planner's internal Waypoint shape.

import type { Waypoint } from "@/lib/missionGeometry";

export interface PlannedPoint {
  lat: number;
  lon: number;
  altitude?: number;
}

export interface AgentWaypoint {
  seq: number;
  lat: number;
  lon: number;
  alt_m: number;
}

export function missionToWaypoints(
  points: PlannedPoint[],
  defaultAltM = 40
): AgentWaypoint[] {
  return points.map((p, i) => ({
    seq: i,
    lat: p.lat,
    lon: p.lon,
    alt_m: p.altitude ?? defaultAltM,
  }));
}

/**
 * Planner route → Live Ops staging points. The planner stores altitude as
 * `alt`; PlannedPoint uses `altitude`. Passing Waypoint[] straight through type-
 * checks structurally but drops the altitude, so missionToWaypoints would fall
 * back to its 40 m default for every point — discarding the planned altitude and
 * any terrain-follow offsets.
 */
export function plannerToPlannedPoints(waypoints: Waypoint[]): PlannedPoint[] {
  return waypoints.map((w) => ({ lat: w.lat, lon: w.lon, altitude: w.alt }));
}

