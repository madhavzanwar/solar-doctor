// website/nextjs/tests/unit/missionToWaypoints.test.ts
import { describe, it, expect } from "vitest";
import { missionToWaypoints, plannerToPlannedPoints } from "@/lib/missionToWaypoints";

describe("missionToWaypoints", () => {
  it("maps planner waypoints to the agent upload format", () => {
    const planned = [
      { lat: 28.4, lon: 77.1, altitude: 40 },
      { lat: 28.41, lon: 77.1, altitude: 40 },
    ];
    const wps = missionToWaypoints(planned);
    expect(wps).toEqual([
      { seq: 0, lat: 28.4, lon: 77.1, alt_m: 40 },
      { seq: 1, lat: 28.41, lon: 77.1, alt_m: 40 },
    ]);
  });

  it("falls back to a default altitude when missing", () => {
    const wps = missionToWaypoints([{ lat: 1, lon: 2 }], 30);
    expect(wps[0].alt_m).toBe(30);
  });

  it("returns empty array for empty input", () => {
    expect(missionToWaypoints([])).toEqual([]);
  });
});

describe("plannerToPlannedPoints", () => {
  it("carries the planner's alt through as altitude", () => {
    // Planner Waypoint stores altitude as `alt`; PlannedPoint wants `altitude`.
    // Dropping it would upload every point at the 40 m default and silently
    // discard both the planned altitude and terrain-follow offsets.
    const planned = plannerToPlannedPoints([
      { lat: 18.52, lon: 73.85, alt: 55, heading: 90, leg: 0 },
      { lat: 18.53, lon: 73.86, alt: 61.5 },
    ]);
    expect(planned).toEqual([
      { lat: 18.52, lon: 73.85, altitude: 55 },
      { lat: 18.53, lon: 73.86, altitude: 61.5 },
    ]);
    expect(missionToWaypoints(planned).map((w) => w.alt_m)).toEqual([55, 61.5]);
  });

  it("returns empty array for empty input", () => {
    expect(plannerToPlannedPoints([])).toEqual([]);
  });
});

