// website/nextjs/tests/unit/liveVideo.test.ts
import { describe, it, expect, vi } from "vitest";
import {
  buildSignalEnvelope, parseSignalFrame, fetchIceServers,
} from "@/lib/liveVideo";

describe("signal helpers", () => {
  it("builds an offer signal envelope", () => {
    const env = buildSignalEnvelope("offer", "op-1", { sdp: "v=0" });
    expect(env.type).toBe("signal");
    expect(env.signal.kind).toBe("offer");
    expect(env.signal.operator_id).toBe("op-1");
    expect(env.signal.sdp).toBe("v=0");
  });

  it("builds an ice signal envelope", () => {
    const env = buildSignalEnvelope("ice", "op-1", {
      candidate: { candidate: "c", sdpMLineIndex: 0 },
    });
    expect(env.signal.candidate?.sdpMLineIndex).toBe(0);
  });

  it("parses a signal frame", () => {
    const raw = JSON.stringify({ type: "signal", signal: { kind: "answer", operator_id: "op-1", sdp: "v=0" } });
    const s = parseSignalFrame(raw);
    expect(s?.kind).toBe("answer");
    expect(s?.sdp).toBe("v=0");
  });

  it("returns null for non-signal frames", () => {
    expect(parseSignalFrame(JSON.stringify({ type: "telemetry" }))).toBeNull();
    expect(parseSignalFrame("nope")).toBeNull();
  });
});

describe("fetchIceServers", () => {
  it("hits the relay turn endpoint and returns iceServers", async () => {
    const servers = [{ urls: "stun:turn.example.com:3478" }];
    global.fetch = vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ iceServers: servers }),
    }) as unknown as typeof fetch;
    const out = await fetchIceServers("https://relay.example.com", "otok", "op-1");
    expect(out).toEqual(servers);
  });

  it("falls back to a public STUN server on failure", async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false }) as unknown as typeof fetch;
    const out = await fetchIceServers("https://relay.example.com", "otok", "op-1");
    expect(out[0].urls).toContain("stun:");
  });
});
