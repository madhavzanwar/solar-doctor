// website/nextjs/tests/unit/manualInput.test.ts
import { describe, it, expect } from "vitest";
import { sticksToVelocity, buildManualEnvelope } from "@/lib/manualInput";

describe("sticksToVelocity", () => {
  it("maps full-forward right-stick to max vx", () => {
    const v = sticksToVelocity({ rx: 0, ry: -1, lx: 0, ly: 0 });
    expect(v.vx).toBeCloseTo(8.0);   // -ry (up) = forward
    expect(v.vy).toBeCloseTo(0);
  });

  it("applies a deadzone near center", () => {
    const v = sticksToVelocity({ rx: 0.03, ry: 0.03, lx: 0, ly: 0 });
    expect(v.vx).toBe(0);
    expect(v.vy).toBe(0);
  });

  it("left stick controls vertical + yaw", () => {
    const v = sticksToVelocity({ rx: 0, ry: 0, lx: 1, ly: -1 });
    expect(v.yaw_rate).toBeCloseTo(1.5);   // lx full right = max yaw
    expect(v.vz).toBeCloseTo(-3.0);        // ly up = climb (negative down)
  });
});

describe("buildManualEnvelope", () => {
  it("wraps a velocity into a manual envelope with seq + operator", () => {
    const env = buildManualEnvelope("op-1", 7, { vx: 1, vy: 0, vz: 0, yaw_rate: 0 });
    expect(env.type).toBe("manual");
    expect(env.manual.operator_id).toBe("op-1");
    expect(env.manual.seq).toBe(7);
    expect(env.manual.vx).toBe(1);
  });
});
