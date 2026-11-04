// website/nextjs/components/Platform/ManualPad.tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { sticksToVelocity, buildManualEnvelope, type Sticks } from "@/lib/manualInput";

interface Props {
  operatorId: string;
  enabled: boolean;                  // tier === GREEN && hasControl
  send: (env: object) => void;
}

const RATE_HZ = 15;

export default function ManualPad({ operatorId, enabled, send }: Props) {
  const sticks = useRef<Sticks>({ rx: 0, ry: 0, lx: 0, ly: 0 });
  const seq = useRef(0);
  const [active, setActive] = useState(false);

  // send loop: only while enabled AND a stick is engaged
  useEffect(() => {
    if (!enabled) return;
    const id = setInterval(() => {
      const s = sticks.current;
      const engaged = s.rx || s.ry || s.lx || s.ly;
      if (!engaged) return;
      send(buildManualEnvelope(operatorId, seq.current++, sticksToVelocity(s)));
    }, 1000 / RATE_HZ);
    return () => clearInterval(id);
  }, [enabled, operatorId, send]);

  const onMove = (which: "r" | "l") => (e: React.PointerEvent<HTMLDivElement>) => {
    if (!enabled || e.buttons === 0) return;
    const r = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - r.left) / r.width) * 2 - 1;
    const y = ((e.clientY - r.top) / r.height) * 2 - 1;
    const cx = Math.max(-1, Math.min(1, x));
    const cy = Math.max(-1, Math.min(1, y));
    if (which === "r") { sticks.current.rx = cx; sticks.current.ry = cy; }
    else { sticks.current.lx = cx; sticks.current.ly = cy; }
    setActive(true);
  };
  const onRelease = (which: "r" | "l") => () => {
    if (which === "r") { sticks.current.rx = 0; sticks.current.ry = 0; }
    else { sticks.current.lx = 0; sticks.current.ly = 0; }
    setActive(false);
  };

  if (!enabled) {
    return <div className="manual-pad-disabled">Manual control: GREEN link + control lock required</div>;
  }

  return (
    <div className="manual-pad">
      <div className="manual-stick" onPointerMove={onMove("l")} onPointerUp={onRelease("l")}
           onPointerLeave={onRelease("l")}>throttle / yaw</div>
      <div className="manual-stick" onPointerMove={onMove("r")} onPointerUp={onRelease("r")}
           onPointerLeave={onRelease("r")}>pitch / roll</div>
      <span className="manual-state">{active ? "● commanding" : "○ idle"}</span>
    </div>
  );
}
