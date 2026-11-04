// website/nextjs/lib/liveOps.ts
// Browser-side live-ops client: parses telemetry frames and manages the ops
// WebSocket subscription to the relay. Mirrors drone/common/telemetry.py.

export type LinkTier = "GREEN" | "AMBER" | "RED";

export interface Telemetry {
  drone_id: string;
  ts: number;
  seq: number;
  lat: number;
  lon: number;
  alt_rel_m: number;
  alt_amsl_m: number;
  heading_deg: number;
  groundspeed_ms: number;
  battery_pct: number;
  battery_voltage: number;
  mode: string;
  armed: boolean;
  gps_fix: number;
  satellites: number;
  roll_deg: number;
  pitch_deg: number;
  yaw_deg: number;
  link_tier: LinkTier;
}

export function parseTelemetryFrame(raw: string): Telemetry | null {
  try {
    const env = JSON.parse(raw);
    if (env?.type !== "telemetry" || !env.telemetry) return null;
    return env.telemetry as Telemetry;
  } catch {
    return null;
  }
}

// --- Phase 2: commands, acks, control ---

export type CommandType =
  | "ARM" | "DISARM" | "TAKEOFF" | "RTL" | "LAND"
  | "PAUSE" | "RESUME" | "GOTO" | "SET_MODE" | "UPLOAD_MISSION";

export interface Ack { cmd_id: string; success: boolean; message: string }
export interface ControlReply { action: string; granted?: boolean; holder?: string | null }

function randomId(): string {
  // crypto.randomUUID is available in modern browsers; fall back for tests/node.
  return typeof crypto !== "undefined" && "randomUUID" in crypto
    ? crypto.randomUUID()
    : Math.random().toString(36).slice(2) + Date.now().toString(36);
}

export function buildCommandEnvelope(type: CommandType, params: Record<string, unknown> = {}) {
  return { type: "command", command: { cmd_id: randomId(), type, params } };
}

export function buildControlEnvelope(action: "acquire" | "release" | "status", operatorId: string) {
  return { type: "control", control: { action, operator_id: operatorId } };
}

export function parseAckFrame(raw: string): Ack | null {
  try {
    const env = JSON.parse(raw);
    return env?.type === "ack" && env.ack ? (env.ack as Ack) : null;
  } catch {
    return null;
  }
}

export function parseControlFrame(raw: string): ControlReply | null {
  try {
    const env = JSON.parse(raw);
    return env?.type === "control" && env.control ? (env.control as ControlReply) : null;
  } catch {
    return null;
  }
}

export interface LiveOpsHandlers {
  onTelemetry: (t: Telemetry) => void;
  onStatus?: (s: "connecting" | "open" | "closed") => void;
  onAck?: (a: Ack) => void;
  onControl?: (c: ControlReply) => void;
  onSignal?: (raw: string) => void;
}

export interface LiveOpsHandle {
  /** False when the frame was dropped because the socket isn't open. */
  send: (env: object) => boolean;
  dispose: () => void;
}

/** Opens the ops WebSocket and pumps telemetry/ack/control to the handlers.
 *  Returns a send-capable handle. Auto-reconnects with backoff. */
export function connectLiveOps(
  baseWsUrl: string,
  droneId: string,
  opsToken: string,
  operatorId: string,
  handlers: LiveOpsHandlers
): LiveOpsHandle {
  let ws: WebSocket | null = null;
  let closed = false;
  let backoff = 1000;

  const open = () => {
    if (closed) return;
    handlers.onStatus?.("connecting");
    const url = `${baseWsUrl}/ws/ops/${droneId}?token=${encodeURIComponent(opsToken)}&operator=${encodeURIComponent(operatorId)}`;
    ws = new WebSocket(url);
    ws.onopen = () => {
      backoff = 1000;
      handlers.onStatus?.("open");
    };
    ws.onmessage = (ev) => {
      const data = ev.data as string;
      const t = parseTelemetryFrame(data);
      if (t) { handlers.onTelemetry(t); return; }
      const ack = parseAckFrame(data);
      if (ack) { handlers.onAck?.(ack); return; }
      const ctl = parseControlFrame(data);
      if (ctl) { handlers.onControl?.(ctl); return; }
      if (data.includes('"type":"signal"')) { handlers.onSignal?.(data); return; }
    };
    ws.onclose = () => {
      handlers.onStatus?.("closed");
      if (!closed) setTimeout(open, (backoff = Math.min(backoff * 2, 15000)));
    };
    ws.onerror = () => ws?.close();
  };

  open();
  return {
    send: (env: object) => {
      // WebSocket.send throws while CONNECTING and warns while CLOSING. Frames are
      // dropped, not queued: a command replayed after a reconnect could fly a
      // stale ARM/TAKEOFF long after the operator pressed it.
      if (!ws || ws.readyState !== WebSocket.OPEN) return false;
      ws.send(JSON.stringify(env));
      return true;
    },
    dispose: () => { closed = true; ws?.close(); },
  };
}
