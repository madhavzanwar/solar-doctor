// website/nextjs/lib/manualInput.ts
// Maps two normalized sticks [-1..1] to body-frame velocity. Mirrors the limits
// in drone/common/manual.py. Right stick = translate (pitch/roll), left stick =
// throttle/yaw. A deadzone kills jitter near center.

export interface Sticks { rx: number; ry: number; lx: number; ly: number }
export interface Velocity { vx: number; vy: number; vz: number; yaw_rate: number }

const MAX_HORIZ = 8.0;
const MAX_VERT = 3.0;
const MAX_YAW = 1.5;
const DEADZONE = 0.08;

function dz(v: number): number {
  return Math.abs(v) < DEADZONE ? 0 : v;
}

export function sticksToVelocity(s: Sticks): Velocity {
  return {
    vx: dz(-s.ry) * MAX_HORIZ, // stick up (negative) = forward
    vy: dz(s.rx) * MAX_HORIZ,  // stick right = right
    vz: dz(s.ly) * MAX_VERT,   // stick up (negative) = climb (negative down)
    yaw_rate: dz(s.lx) * MAX_YAW,
  };
}

export function buildManualEnvelope(operatorId: string, seq: number, v: Velocity) {
  return { type: "manual", manual: { operator_id: operatorId, seq, ...v } };
}
