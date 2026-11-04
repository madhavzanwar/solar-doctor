// website/nextjs/tests/unit/liveOpsConnection.test.tsx
// Live Ops crashed the whole console the first time a relay was configured:
// "InvalidStateError: Failed to execute 'send' on 'WebSocket': Still in CONNECTING state".
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { act, render } from "@testing-library/react";

class FakeWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;
  static instances: FakeWebSocket[] = [];
  readyState = FakeWebSocket.CONNECTING;
  sent: string[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(public url: string) {
    FakeWebSocket.instances.push(this);
  }
  send(data: string) {
    // Mirrors the browser: sending before OPEN throws.
    if (this.readyState !== FakeWebSocket.OPEN) throw new Error("InvalidStateError: Still in CONNECTING state");
    this.sent.push(data);
  }
  close() {
    this.readyState = FakeWebSocket.CLOSED;
  }
}

describe("connectLiveOps send", () => {
  beforeEach(() => {
    FakeWebSocket.instances = [];
    vi.stubGlobal("WebSocket", FakeWebSocket);
  });
  afterEach(() => vi.unstubAllGlobals());

  it("drops frames while the socket is still connecting instead of throwing", async () => {
    const { connectLiveOps } = await import("@/lib/liveOps");
    const handle = connectLiveOps("wss://relay", "drone-01", "tok", "op-a", { onTelemetry: () => {} });

    expect(() => handle.send({ type: "control" })).not.toThrow();
    expect(handle.send({ type: "control" })).toBe(false);
    expect(FakeWebSocket.instances[0].sent).toEqual([]);
    handle.dispose();
  });

  it("sends once the socket is open", async () => {
    const { connectLiveOps } = await import("@/lib/liveOps");
    const handle = connectLiveOps("wss://relay", "drone-01", "tok", "op-a", { onTelemetry: () => {} });
    const ws = FakeWebSocket.instances[0];
    ws.readyState = FakeWebSocket.OPEN;
    ws.onopen?.();

    expect(handle.send({ type: "control" })).toBe(true);
    expect(ws.sent).toHaveLength(1);
    handle.dispose();
  });
});

describe("LiveOpsTab", () => {
  const sendSpy = vi.fn((_env: object) => true);
  let captured: { onStatus?: (s: string) => void } = {};

  beforeEach(() => {
    sendSpy.mockClear();
    captured = {};
    vi.resetModules();
    vi.doMock("@/lib/liveOps", async (orig) => ({
      ...(await orig<typeof import("@/lib/liveOps")>()),
      connectLiveOps: (_u: string, _d: string, _t: string, _o: string, handlers: typeof captured) => {
        captured = handlers;
        return { send: sendSpy, dispose: () => {} };
      },
    }));
    vi.doMock("next/dynamic", () => ({ default: () => () => null }));
    vi.stubEnv("NEXT_PUBLIC_RELAY_WS_URL", "wss://relay");
  });
  afterEach(() => {
    vi.doUnmock("@/lib/liveOps");
    vi.doUnmock("next/dynamic");
    vi.unstubAllEnvs();
  });

  it("does not send the video 'bye' on every re-render", async () => {
    const { default: LiveOpsTab } = await import("@/components/Platform/LiveOpsTab");
    render(<LiveOpsTab droneId="drone-01" />);

    // Status and telemetry updates re-render the tab many times per second.
    act(() => captured.onStatus?.("connecting"));
    act(() => captured.onStatus?.("open"));
    act(() => captured.onStatus?.("closed"));

    const sent = sendSpy.mock.calls.map((c) => JSON.stringify(c[0]));
    expect(sent.filter((s) => s.includes('"bye"'))).toEqual([]);
  });
});
