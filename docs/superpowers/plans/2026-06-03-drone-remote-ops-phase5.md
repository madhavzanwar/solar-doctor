# Drone Remote Ops — Phase 5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Tier-3 manual flight — a browser joystick that sends high-rate velocity input to the drone — but fence it hard: enabled **only on a GREEN link**, holder-only, with a manual-input deadman that zeroes velocity the instant input stops.

**Architecture:** Manual input is too high-rate for the command/ack path, so it gets its own lightweight frame (`type:"manual"`, no ack) sent at ~15 Hz. The relay drops any manual frame unless the sender holds the control lock **and** the drone's link tier is GREEN (authoritative). The agent maps input → MAVLink `SET_POSITION_TARGET` body-frame velocity in GUIDED, and runs a manual deadman: if no manual frame arrives for ~400 ms, it commands zero velocity (hover), independent of the Phase-2 relay-link deadman.

**Tech Stack:** Builds on Phases 1–4. Python `pymavlink`/`fastapi`/`pydantic`, `pytest`; frontend Next.js + `vitest`. No new deps.

**Spec:** `docs/superpowers/specs/2026-06-03-drone-remote-operations-design.md` (Phase 5: manual tier + link gating).
**Depends on:** Phases 1–4 implemented.

---

## Conventions
- Python under `drone/`; tests `python -m pytest drone/tests -v`. Frontend `npx vitest run`.
- Commit after every green step.
- **Body-frame velocity:** vx = forward (m/s), vy = right (m/s), vz = down (m/s), yaw_rate (rad/s).

---

## Task 1: Manual input schema + extend Envelope

**Files:**
- Create: `drone/common/manual.py`
- Modify: `drone/common/telemetry.py` (add `manual` to `Envelope`)
- Test: `drone/tests/test_manual_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_manual_schema.py
import pytest
from pydantic import ValidationError
from drone.common.manual import ManualInput
from drone.common.telemetry import Envelope


def test_manual_roundtrips():
    m = ManualInput(operator_id="op-1", vx=1.0, vy=-0.5, vz=0.0, yaw_rate=0.2, seq=3)
    again = ManualInput.model_validate_json(m.model_dump_json())
    assert again == m


def test_velocity_clamped_to_limits():
    with pytest.raises(ValidationError):
        ManualInput(operator_id="op-1", vx=999, vy=0, vz=0, yaw_rate=0, seq=0)


def test_envelope_carries_manual():
    env = Envelope(type="manual",
                   manual=ManualInput(operator_id="op-1", vx=0, vy=0, vz=0, yaw_rate=0, seq=0))
    rt = Envelope.model_validate_json(env.model_dump_json())
    assert rt.manual is not None and rt.manual.operator_id == "op-1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_manual_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.common.manual'`

- [ ] **Step 3: Write `drone/common/manual.py`**

```python
# drone/common/manual.py
"""High-rate manual flight input. Sent ~15 Hz, no per-frame ack.

Velocities are body-frame and clamped at the schema boundary so a malformed or
hostile frame can never request an absurd speed.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

MAX_HORIZ_MS = 8.0
MAX_VERT_MS = 3.0
MAX_YAW_RATE = 1.5  # rad/s


class ManualInput(BaseModel):
    operator_id: str
    seq: int = Field(..., ge=0)
    vx: float = Field(..., ge=-MAX_HORIZ_MS, le=MAX_HORIZ_MS)  # forward
    vy: float = Field(..., ge=-MAX_HORIZ_MS, le=MAX_HORIZ_MS)  # right
    vz: float = Field(..., ge=-MAX_VERT_MS, le=MAX_VERT_MS)    # down
    yaw_rate: float = Field(..., ge=-MAX_YAW_RATE, le=MAX_YAW_RATE)
```

- [ ] **Step 4: Extend `Envelope` in `drone/common/telemetry.py`**

Add the import after the existing signaling import:

```python
from drone.common.manual import ManualInput
```

Add to the `Envelope` class:

```python
    manual: ManualInput | None = None
```

(Update the docstring `type` list to include `'manual'`.)

- [ ] **Step 5: Run tests**

Run: `python -m pytest drone/tests/test_manual_schema.py drone/tests/test_signaling_schema.py -v`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add drone/common/manual.py drone/common/telemetry.py drone/tests/test_manual_schema.py
git commit -m "feat(drone): manual flight input schema + envelope variant"
```

---

## Task 2: Tier policy — manual is GREEN-only

**Files:**
- Modify: `drone/relay/tier_policy.py`
- Test: `drone/tests/test_tier_policy_manual.py`

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_tier_policy_manual.py
from drone.common.telemetry import LinkTier
from drone.relay.tier_policy import authorize_manual


def test_manual_allowed_on_green_with_lock():
    ok, reason = authorize_manual(holds_lock=True, tier=LinkTier.GREEN)
    assert ok is True and reason == ""


def test_manual_blocked_on_amber():
    ok, reason = authorize_manual(holds_lock=True, tier=LinkTier.AMBER)
    assert ok is False
    assert "green" in reason.lower()


def test_manual_blocked_on_red():
    ok, _ = authorize_manual(holds_lock=True, tier=LinkTier.RED)
    assert ok is False


def test_manual_requires_lock():
    ok, reason = authorize_manual(holds_lock=False, tier=LinkTier.GREEN)
    assert ok is False
    assert "lock" in reason.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_tier_policy_manual.py -v`
Expected: FAIL — `ImportError: cannot import name 'authorize_manual'`

- [ ] **Step 3: Add `authorize_manual` to `drone/relay/tier_policy.py`**

```python
def authorize_manual(*, holds_lock: bool, tier: LinkTier) -> tuple[bool, str]:
    """Manual stick input is GREEN-only (low-latency link) and holder-only."""
    if not holds_lock:
        return False, "you do not hold the control lock"
    if tier is not LinkTier.GREEN:
        return False, f"manual control requires a GREEN link (current: {tier.value})"
    return True, ""
```

- [ ] **Step 4: Run test**

Run: `python -m pytest drone/tests/test_tier_policy_manual.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add drone/relay/tier_policy.py drone/tests/test_tier_policy_manual.py
git commit -m "feat(relay): GREEN-only authorization for manual control"
```

---

## Task 3: Relay routing for manual frames (gated, no ack noise)

**Files:**
- Modify: `drone/relay/server.py`
- Test: `drone/tests/test_relay_manual.py`

Manual frames are dropped silently when unauthorized (no ack per frame — at 15 Hz
that would flood the socket). The UI already knows the tier and disables the stick;
the relay drop is the authoritative backstop.

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_relay_manual.py
import json
import pytest
from fastapi.testclient import TestClient
from drone.relay.server import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DRONE_TOKENS", "sitl-01:dtok")
    monkeypatch.setenv("OPS_TOKEN", "otok")
    return TestClient(create_app())


def _telemetry(tier):
    return json.dumps({"type": "telemetry", "telemetry": {
        "drone_id": "sitl-01", "ts": 1, "seq": 0, "lat": 28.4, "lon": 77.1,
        "alt_rel_m": 40, "alt_amsl_m": 255, "heading_deg": 90, "groundspeed_ms": 0,
        "battery_pct": 80, "battery_voltage": 22.0, "mode": "GUIDED", "armed": True,
        "gps_fix": 3, "satellites": 14, "roll_deg": 0, "pitch_deg": 0, "yaw_deg": 90,
        "link_tier": tier}})


def _manual():
    return json.dumps({"type": "manual", "manual": {
        "operator_id": "op-a", "seq": 1, "vx": 1.0, "vy": 0, "vz": 0, "yaw_rate": 0}})


def test_manual_forwarded_on_green_with_lock(client):
    with client.websocket_connect("/ws/drone/sitl-01?token=dtok") as drone:
        drone.send_text(_telemetry("GREEN"))
        with client.websocket_connect("/ws/ops/sitl-01?token=otok&operator=op-a") as ops:
            ops.send_text(json.dumps({"type": "control",
                "control": {"action": "acquire", "operator_id": "op-a"}}))
            ops.receive_text()  # grant
            ops.send_text(_manual())
            fwd = json.loads(drone.receive_text())
            assert fwd["type"] == "manual" and fwd["manual"]["vx"] == 1.0


def test_manual_dropped_on_amber(client):
    with client.websocket_connect("/ws/drone/sitl-01?token=dtok") as drone:
        drone.send_text(_telemetry("AMBER"))
        with client.websocket_connect("/ws/ops/sitl-01?token=otok&operator=op-a") as ops:
            ops.send_text(json.dumps({"type": "control",
                "control": {"action": "acquire", "operator_id": "op-a"}}))
            ops.receive_text()
            ops.send_text(_manual())
            # Probe: send a heartbeat after. If manual had been forwarded, the drone
            # would receive it first; instead the next frame is the heartbeat echo.
            drone.send_text(json.dumps({"type": "heartbeat", "ts": 9.0}))
            echoed = json.loads(drone.receive_text())
            assert echoed["type"] == "heartbeat"  # manual was dropped, not forwarded
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_relay_manual.py -v`
Expected: FAIL — manual frames not handled (the GREEN test times out on `drone.receive_text()`)

- [ ] **Step 3: Edit `drone/relay/server.py`**

Update the tier-policy import:

```python
from drone.relay.tier_policy import authorize_command, authorize_manual
```

In `ops_ws`'s message loop, add a manual branch:

```python
                elif env.type == "manual" and env.manual is not None:
                    ok, _reason = authorize_manual(
                        holds_lock=lock.holds(drone_id, operator),
                        tier=mgr.tier_for(drone_id),
                    )
                    if ok:
                        await mgr.send_to_drone(drone_id, raw)
                    # unauthorized manual frames are dropped silently (no ack flood)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest drone/tests/test_relay_manual.py drone/tests/test_relay_server_phase2.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add drone/relay/server.py drone/tests/test_relay_manual.py
git commit -m "feat(relay): gate + route manual control frames (GREEN-only)"
```

---

## Task 4: Agent manual mapping + manual deadman

**Files:**
- Create: `drone/agent/manual_control.py`
- Modify: `drone/agent/commander.py` (add `send_velocity`)
- Test: `drone/tests/test_manual_control.py`

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_manual_control.py
from drone.common.manual import ManualInput
from drone.agent.manual_control import ManualController, ManualDeadman


class FakeCommander:
    def __init__(self):
        self.velocities = []

    def send_velocity(self, vx, vy, vz, yaw_rate):
        self.velocities.append((vx, vy, vz, yaw_rate))


def test_apply_forwards_velocity_to_commander():
    c = FakeCommander()
    mc = ManualController(c)
    mc.apply(ManualInput(operator_id="op", seq=1, vx=1.0, vy=0.5, vz=0.0, yaw_rate=0.2))
    assert c.velocities == [(1.0, 0.5, 0.0, 0.2)]


def test_apply_ignores_stale_seq():
    c = FakeCommander()
    mc = ManualController(c)
    mc.apply(ManualInput(operator_id="op", seq=5, vx=1.0, vy=0, vz=0, yaw_rate=0))
    mc.apply(ManualInput(operator_id="op", seq=3, vx=2.0, vy=0, vz=0, yaw_rate=0))  # older
    assert c.velocities == [(1.0, 0, 0, 0)]  # stale frame ignored


def test_deadman_triggers_zero_velocity_after_timeout():
    c = FakeCommander()
    mc = ManualController(c)
    dm = ManualDeadman(timeout_s=0.4)
    mc.apply(ManualInput(operator_id="op", seq=1, vx=1.0, vy=0, vz=0, yaw_rate=0))
    dm.beat(now=10.0)
    assert dm.expired(now=10.2) is False
    assert dm.expired(now=10.5) is True
    mc.hover()
    assert c.velocities[-1] == (0.0, 0.0, 0.0, 0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_manual_control.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.agent.manual_control'`

- [ ] **Step 3: Add `send_velocity` to `drone/agent/commander.py`**

Add to the `MavCommander` Protocol:

```python
    def send_velocity(self, vx: float, vy: float, vz: float, yaw_rate: float) -> None: ...
```

Add to `PymavlinkCommander`:

```python
    def send_velocity(self, vx: float, vy: float, vz: float, yaw_rate: float) -> None:
        # body-frame velocity in GUIDED; type_mask enables vx/vy/vz + yaw_rate only
        self._c.mav.set_position_target_local_ned_send(
            0, self._c.target_system, self._c.target_component,
            mavutil.mavlink.MAV_FRAME_BODY_NED,
            0b0000011111000111,  # use velocity + yaw_rate
            0, 0, 0,
            vx, vy, vz,
            0, 0, 0,
            0, yaw_rate)
```

- [ ] **Step 4: Write `drone/agent/manual_control.py`**

```python
# drone/agent/manual_control.py
"""Apply manual velocity input to the autopilot, with stale-frame rejection.

`ManualController.apply` forwards a ManualInput to the commander, ignoring
out-of-order frames (seq must advance). `ManualDeadman` is a separate, faster
deadman than the relay-link one: if manual frames stop arriving, the agent calls
`hover()` so the drone holds instead of coasting on the last velocity.
"""
from __future__ import annotations

from drone.agent.commander import MavCommander
from drone.common.manual import ManualInput


class ManualController:
    def __init__(self, commander: MavCommander) -> None:
        self.commander = commander
        self._last_seq = -1

    def apply(self, m: ManualInput) -> None:
        if m.seq <= self._last_seq:
            return  # stale / out-of-order
        self._last_seq = m.seq
        self.commander.send_velocity(m.vx, m.vy, m.vz, m.yaw_rate)

    def hover(self) -> None:
        self.commander.send_velocity(0.0, 0.0, 0.0, 0.0)


class ManualDeadman:
    def __init__(self, timeout_s: float) -> None:
        self.timeout_s = timeout_s
        self._last: float | None = None

    def beat(self, now: float) -> None:
        self._last = now

    def expired(self, now: float) -> bool:
        if self._last is None:
            return False  # not in manual mode yet
        return (now - self._last) > self.timeout_s
```

- [ ] **Step 5: Run test**

Run: `python -m pytest drone/tests/test_manual_control.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit**

```bash
git add drone/agent/manual_control.py drone/agent/commander.py drone/tests/test_manual_control.py
git commit -m "feat(agent): manual velocity mapping + manual-input deadman"
```

---

## Task 5: Agent main wiring for manual

**Files:**
- Modify: `drone/agent/main.py`
- Modify: `drone/agent/config.py` (manual deadman timeout)

Glue. The manual deadman runs in the heartbeat loop (already ticking).

- [ ] **Step 1: Add config**

In `drone/agent/config.py`, add field `manual_deadman_s: float` and in `from_env`:

```python
            manual_deadman_s=float(os.getenv("MANUAL_DEADMAN_S", "0.4")),
```

- [ ] **Step 2: Wire into `main.py`**

After the publisher setup, create the manual controller + deadman:

```python
    from drone.agent.manual_control import ManualController, ManualDeadman
    manual = ManualController(commander)
    manual_dm = ManualDeadman(cfg.manual_deadman_s)
    manual_active = {"on": False}
```

In `recv_loop`, add a branch:

```python
                elif env.type == "manual" and env.manual is not None:
                    manual_active["on"] = True
                    manual_dm.beat(time.time())
                    manual.apply(env.manual)
```

In `heartbeat_loop`, after the relay-link deadman check, add the manual hover-on-stale:

```python
                if manual_active["on"] and manual_dm.expired(time.time()):
                    manual.hover()
                    manual_active["on"] = False
```

- [ ] **Step 3: Run the full unit suite**

Run: `python -m pytest drone/tests -v`
Expected: all unit tests PASS; SITL e2e SKIPPED.

- [ ] **Step 4: Commit**

```bash
git add drone/agent/main.py drone/agent/config.py
git commit -m "feat(agent): wire manual control + hover-on-stale into main"
```

---

## Task 6: Frontend manual input (stick→velocity mapping)

**Files:**
- Create: `website/nextjs/lib/manualInput.ts`
- Test: `website/nextjs/tests/unit/manualInput.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd website/nextjs && npx vitest run tests/unit/manualInput.test.ts`
Expected: FAIL — cannot resolve `@/lib/manualInput`

- [ ] **Step 3: Write `website/nextjs/lib/manualInput.ts`**

```ts
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
```

- [ ] **Step 4: Run test**

Run: `cd website/nextjs && npx vitest run tests/unit/manualInput.test.ts`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add website/nextjs/lib/manualInput.ts website/nextjs/tests/unit/manualInput.test.ts
git commit -m "feat(web): stick-to-velocity mapping + manual envelope builder"
```

---

## Task 7: Frontend joystick widget (GREEN-only) + state indicator

**Files:**
- Create: `website/nextjs/components/Platform/ManualPad.tsx`
- Modify: `website/nextjs/components/Platform/LiveOpsTab.tsx` (mount, GREEN-gated)
- Modify: `website/nextjs/app/globals.css` (pad styles)

No unit test (pointer-driven DOM); validated against SITL. The pad sends at ~15 Hz
only while a stick is held, and only when `tier === "GREEN"` and the operator holds
control.

- [ ] **Step 1: Create `ManualPad.tsx`**

```tsx
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
```

- [ ] **Step 2: Mount it GREEN-gated in `LiveOpsTab.tsx`**

Add the import and, in `.liveops-side` below the command bar:

```tsx
import ManualPad from "@/components/Platform/ManualPad";
// ...
      <ManualPad
        operatorId={operatorId}
        enabled={hasControl && tier === "GREEN"}
        send={send}
      />
```

(`tier` and `hasControl` already exist in the component from Phase 2/4.)

- [ ] **Step 3: Add pad styles to the platform stylesheet**

```css
.manual-pad { display: flex; gap: 12px; align-items: center; }
.manual-stick {
  width: 120px; height: 120px; border-radius: 12px;
  border: 1px solid var(--border, #1f2a37); background: #0b1118;
  display: flex; align-items: center; justify-content: center;
  font-size: 11px; color: #6b7a8d; touch-action: none; user-select: none;
}
.manual-pad-disabled { font-size: 12px; color: #6b7a8d; }
.manual-state { font-size: 12px; color: #14b8a6; }
```

- [ ] **Step 4: Verify build**

Run: `cd website/nextjs && npm run build`
Expected: build succeeds.

- [ ] **Step 5: Manual verification (SITL on a LAN / GREEN)**

With SITL + relay + agent on the same LAN (tier reads GREEN), arm + takeoff via the
command bar, then drag a stick — the SITL vehicle should translate; release → it
hovers within ~0.4 s (manual deadman). Force AMBER → the pad disables. Confirm a
second operator without the lock never sees an enabled pad.

- [ ] **Step 6: Commit**

```bash
git add website/nextjs/components/Platform/ManualPad.tsx website/nextjs/components/Platform/LiveOpsTab.tsx website/nextjs/app/globals.css
git commit -m "feat(web): GREEN-only manual joystick pad"
```

---

## Self-Review Notes (resolved)
- **Spec coverage (Phase 5):** manual velocity input (Tasks 1, 4, 6), GREEN-only link gating —
  relay-authoritative (Tasks 2, 3) + UI gate (Task 7), manual-input deadman → hover (Tasks 4, 5). ✔
- **Defense in depth:** the UI disables the pad off-GREEN, the relay drops unauthorized manual
  frames, and the agent's manual deadman hovers on stale input — three independent guards. ✔
- **Types consistent:** `ManualInput` fields (`operator_id`/`seq`/`vx`/`vy`/`vz`/`yaw_rate`) +
  body-frame velocity limits (8/3/1.5) match Python (`manual.py`) ↔ TS (`manualInput.ts`); the
  `send_velocity` MAVLink type_mask enables exactly vx/vy/vz + yaw_rate. ✔
- **No ack flood:** manual frames are unacked and dropped silently when unauthorized (Task 3),
  unlike Phase-2 commands. ✔
- **No placeholders:** full code throughout; the pad's pointer math is intentionally simple
  (absolute position within the pad) — fine for the GREEN-only on-site use case. ✔
```
