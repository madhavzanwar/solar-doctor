// website/nextjs/tests/unit/track.test.ts
import { describe, it, expect } from "vitest";
import { appendTrackPoint, type LatLon } from "@/lib/track";

describe("appendTrackPoint", () => {
  it("appends a point", () => {
    const t = appendTrackPoint([], { lat: 1, lon: 2 }, 100);
    expect(t).toEqual([{ lat: 1, lon: 2 }]);
  });

  it("caps the buffer at maxLen (drops oldest)", () => {
    let t: LatLon[] = [];
    for (let i = 0; i < 5; i++) t = appendTrackPoint(t, { lat: i, lon: 0 }, 3);
    expect(t.map((p) => p.lat)).toEqual([2, 3, 4]);
  });

  it("skips a near-duplicate consecutive point (<~0.5m)", () => {
    const t1 = appendTrackPoint([], { lat: 28.4, lon: 77.1 }, 100);
    const t2 = appendTrackPoint(t1, { lat: 28.4000001, lon: 77.1000001 }, 100);
    expect(t2.length).toBe(1); // negligible move ignored
  });

  it("keeps a meaningful move", () => {
    const t1 = appendTrackPoint([], { lat: 28.4, lon: 77.1 }, 100);
    const t2 = appendTrackPoint(t1, { lat: 28.401, lon: 77.1 }, 100);
    expect(t2.length).toBe(2);
  });
});
