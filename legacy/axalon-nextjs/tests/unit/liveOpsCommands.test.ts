// website/nextjs/tests/unit/liveOpsCommands.test.ts
import { describe, it, expect } from "vitest";
import {
  buildCommandEnvelope,
  buildControlEnvelope,
  parseAckFrame,
  parseControlFrame,
} from "@/lib/liveOps";

describe("command builders", () => {
  it("builds a command envelope with a cmd_id", () => {
    const env = buildCommandEnvelope("TAKEOFF", { alt: 40 });
    expect(env.type).toBe("command");
    expect(env.command.type).toBe("TAKEOFF");
    expect(env.command.params.alt).toBe(40);
    expect(typeof env.command.cmd_id).toBe("string");
    expect(env.command.cmd_id.length).toBeGreaterThan(0);
  });

  it("builds an acquire control envelope", () => {
    const env = buildControlEnvelope("acquire", "op-1");
    expect(env.type).toBe("control");
    expect(env.control.action).toBe("acquire");
    expect(env.control.operator_id).toBe("op-1");
  });
});

describe("frame parsers", () => {
  it("parses an ack frame", () => {
    const raw = JSON.stringify({ type: "ack", ack: { cmd_id: "c1", success: true, message: "ok" } });
    expect(parseAckFrame(raw)).toEqual({ cmd_id: "c1", success: true, message: "ok" });
  });

  it("returns null for non-ack", () => {
    expect(parseAckFrame(JSON.stringify({ type: "telemetry" }))).toBeNull();
    expect(parseAckFrame("bad")).toBeNull();
  });

  it("parses a control frame", () => {
    const raw = JSON.stringify({ type: "control", control: { action: "acquire", granted: true, holder: "op-1" } });
    const c = parseControlFrame(raw);
    expect(c?.granted).toBe(true);
    expect(c?.holder).toBe("op-1");
  });
});
