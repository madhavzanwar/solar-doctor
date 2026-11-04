// website/nextjs/components/Platform/VideoPanel.tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { buildSignalEnvelope, parseSignalFrame, fetchIceServers } from "@/lib/liveVideo";

const RELAY_HTTP = process.env.NEXT_PUBLIC_RELAY_HTTP_URL ?? "";
const OPS_TOKEN = process.env.NEXT_PUBLIC_OPS_TOKEN ?? "";

interface Props {
  operatorId: string;
  send: (env: object) => void;                       // send over the live-ops socket
  registerSignalHandler: (fn: (raw: string) => void) => void;  // inbound signal frames
}

export default function VideoPanel({ operatorId, send, registerSignalHandler }: Props) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const [state, setState] = useState("idle");

  const start = async () => {
    setState("connecting");
    const iceServers = await fetchIceServers(RELAY_HTTP, OPS_TOKEN, operatorId);
    const pc = new RTCPeerConnection({ iceServers });
    pcRef.current = pc;

    pc.addTransceiver("video", { direction: "recvonly" });
    pc.ontrack = (ev) => {
      if (videoRef.current) videoRef.current.srcObject = ev.streams[0];
      setState("streaming");
    };
    pc.onicecandidate = (ev) => {
      if (ev.candidate) {
        send(buildSignalEnvelope("ice", operatorId, {
          candidate: {
            candidate: ev.candidate.candidate,
            sdpMLineIndex: ev.candidate.sdpMLineIndex ?? 0,
          },
        }));
      }
    };

    registerSignalHandler((raw) => {
      const sig = parseSignalFrame(raw);
      if (!sig) return;
      if (sig.kind === "answer" && sig.sdp) {
        pc.setRemoteDescription({ type: "answer", sdp: sig.sdp });
      } else if (sig.kind === "ice" && sig.candidate) {
        pc.addIceCandidate({
          candidate: sig.candidate.candidate,
          sdpMLineIndex: sig.candidate.sdpMLineIndex,
        });
      }
    });

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    send(buildSignalEnvelope("offer", operatorId, { sdp: offer.sdp }));
  };

  useEffect(() => () => {
    pcRef.current?.close();
    send(buildSignalEnvelope("bye", operatorId));
  }, [operatorId, send]);

  return (
    <div className="video-panel">
      <div className="video-panel-controls">
        <button onClick={start} disabled={state === "streaming"}>Start video</button>
        <span>{state}</span>
      </div>
      <video ref={videoRef} autoPlay playsInline muted className="video-panel-feed" />
    </div>
  );
}
