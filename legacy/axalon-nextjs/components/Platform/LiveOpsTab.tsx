// website/nextjs/components/Platform/LiveOpsTab.tsx
"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import dynamic from "next/dynamic";
import {
  connectLiveOps, buildCommandEnvelope, buildControlEnvelope,
  type Telemetry, type Ack, type ControlReply, type CommandType, type LiveOpsHandle,
} from "@/lib/liveOps";
import { missionToWaypoints, type PlannedPoint } from "@/lib/missionToWaypoints";
import { appendTrackPoint, type LatLon } from "@/lib/track";
import VideoPanel from "@/components/Platform/VideoPanel";
import ManualPad from "@/components/Platform/ManualPad";

const LiveMap = dynamic(() => import("@/components/Platform/LiveMap"), { ssr: false });

const RELAY_WS = process.env.NEXT_PUBLIC_RELAY_WS_URL ?? "";
const OPS_TOKEN = process.env.NEXT_PUBLIC_OPS_TOKEN ?? "";

const DESTRUCTIVE: CommandType[] = ["ARM", "TAKEOFF", "LAND"];
const MAX_TRACK = 500;
// Stable default: LiveMap rebuilds route layers whenever this identity changes.
const NO_PLANNED_POINTS: PlannedPoint[] = [];

export default function LiveOpsTab(
  { droneId = "sitl-01", plannedPoints = NO_PLANNED_POINTS }:
  { droneId?: string; plannedPoints?: PlannedPoint[] }
) {
  const operatorId = useMemo(
    () => "op-" + Math.random().toString(36).slice(2, 8), []);
  const [telem, setTelem] = useState<Telemetry | null>(null);
  const [status, setStatus] = useState("idle");
  const [hasControl, setHasControl] = useState(false);
  const [lastAck, setLastAck] = useState<Ack | null>(null);
  const [track, setTrack] = useState<LatLon[]>([]);
  const handleRef = useRef<LiveOpsHandle | null>(null);
  const signalHandlerRef = useRef<((raw: string) => void) | null>(null);

  useEffect(() => {
    if (!RELAY_WS) { setStatus("no relay configured"); return; }
    const h = connectLiveOps(RELAY_WS, droneId, OPS_TOKEN, operatorId, {
      onTelemetry: (t) => {
        setTelem(t);
        setTrack((cur) => appendTrackPoint(cur, { lat: t.lat, lon: t.lon }, MAX_TRACK));
      },
      onStatus: setStatus,
      onAck: setLastAck,
      onControl: (c: ControlReply) =>
        setHasControl(c.granted === true && c.holder === operatorId),
      onSignal: (raw: string) => signalHandlerRef.current?.(raw),
    });
    handleRef.current = h;
    return () => h.dispose();
  }, [droneId, operatorId]);

  // Stable identity: VideoPanel's unmount effect depends on `send`, so a new
  // function each render sent the video "bye" on every status/telemetry update.
  const send = useCallback((env: object) => handleRef.current?.send(env) ?? false, []);

  const acquire = () => send(buildControlEnvelope("acquire", operatorId));
  const release = () => { send(buildControlEnvelope("release", operatorId)); setHasControl(false); };

  const sendCmd = (type: CommandType, params: Record<string, unknown> = {}) => {
    if (DESTRUCTIVE.includes(type) &&
        !window.confirm(`Confirm ${type}${params.alt ? ` to ${params.alt} m` : ""}?`)) return;
    send(buildCommandEnvelope(type, params));
  };

  const tier = telem?.link_tier ?? "RED";
  const cmdsEnabled = hasControl && tier !== "RED";

  return (
    <div className="liveops">
      <div className="liveops-hud">
        <span>Link: {status}</span>
        <span>Tier: {tier}</span>
        {telem && <>
          <span>Mode: {telem.mode}</span>
          <span>{telem.armed ? "ARMED" : "DISARMED"}</span>
          <span>Alt: {telem.alt_rel_m.toFixed(1)} m</span>
          <span>Bat: {telem.battery_pct.toFixed(0)}%</span>
        </>}
      </div>

      <LiveMap
        position={telem ? { lat: telem.lat, lon: telem.lon } : null}
        headingDeg={telem?.heading_deg ?? 0}
        track={track}
        plannedRoute={plannedPoints}
      />

      <div className="liveops-side">
        <div className="liveops-control">
          {hasControl
            ? <button onClick={release}>Release control</button>
            : <button onClick={acquire}>Acquire control</button>}
          <span>{hasControl ? "You have control" : "View-only"}</span>
        </div>

        <div className="liveops-commands">
          <button disabled={!cmdsEnabled} onClick={() => sendCmd("ARM")}>Arm</button>
          <button disabled={!cmdsEnabled} onClick={() => sendCmd("TAKEOFF", { alt: 40 })}>Takeoff 40m</button>
          <button disabled={!cmdsEnabled} onClick={() => sendCmd("PAUSE")}>Pause</button>
          <button disabled={!cmdsEnabled} onClick={() => sendCmd("RESUME")}>Resume</button>
          <button disabled={!cmdsEnabled} onClick={() => sendCmd("RTL")}>RTL</button>
          <button disabled={!cmdsEnabled} onClick={() => sendCmd("LAND")}>Land</button>
          <button
            disabled={!cmdsEnabled || plannedPoints.length === 0}
            onClick={() => sendCmd("UPLOAD_MISSION", { waypoints: missionToWaypoints(plannedPoints) })}
          >
            Upload mission ({plannedPoints.length})
          </button>
        </div>

        {lastAck && (
          <p className={lastAck.success ? "ack-ok" : "ack-fail"}>
            {lastAck.success ? "✓" : "✗"} {lastAck.cmd_id.slice(0, 6)}: {lastAck.message}
          </p>
        )}

        <ManualPad
          operatorId={operatorId}
          enabled={hasControl && tier === "GREEN"}
          send={send}
        />

        <VideoPanel
          operatorId={operatorId}
          send={send}
          registerSignalHandler={(fn) => { signalHandlerRef.current = fn; }}
        />
      </div>
    </div>
  );
}
