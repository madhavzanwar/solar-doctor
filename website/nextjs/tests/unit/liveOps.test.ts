// website/nextjs/tests/unit/liveOps.test.ts
import { describe, it, expect } from "vitest";
import { parseTelemetryFrame, type Telemetry } from "@/lib/liveOps";

describe("parseTelemetryFrame", () => {
  it("extracts telemetry from a valid envelope", () => {
    const raw = JSON.stringify({
      type: "telemetry",
      telemetry: {
        drone_id: "sitl-01", ts: 1, seq: 3,
        lat: 28.4, lon: 77.1, alt_rel_m: 40, alt_amsl_m: 255,
        heading_deg: 90, groundspeed_ms: 5, battery_pct: 82,
        battery_voltage: 22.1, mode: "GUIDED", armed: true,
        gps_fix: 3, satellites: 14, roll_deg: 1, pitch_deg: -1,
        yaw_deg: 90, link_tier: "GREEN",
      },
    });
    const t = parseTelemetryFrame(raw) as Telemetry;
    expect(t.drone_id).toBe("sitl-01");
    expect(t.lat).toBeCloseTo(28.4);
    expect(t.mode).toBe("GUIDED");
  });

  it("returns null for a non-telemetry frame", () => {
    expect(parseTelemetryFrame(JSON.stringify({ type: "ack" }))).toBeNull();
  });

  it("returns null for malformed json", () => {
    expect(parseTelemetryFrame("not json")).toBeNull();
  });
});
