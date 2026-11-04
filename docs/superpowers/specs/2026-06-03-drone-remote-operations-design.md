# Axalon Drone Remote Operations — System Design

**Date:** 2026-06-03
**Status:** Approved (brainstorm)
**Scope:** Whole-system design + 6-phase build program. First implementation slice = Phase 1.

---

## 1. Problem

Operate a custom inspection drone **live from the Axalon platform** (`axalonsystems.com/platform`).
The drone carries a **Pixhawk/Cube running ArduPilot**, a **Jetson Orin Nano** companion
computer, a **USB webcam (RGB)**, and a **Sensmart iTL612R Pro thermal core**. The operator
sits at a browser, potentially anywhere on the internet, and wants live telemetry, live video
(RGB + thermal), high-level mission control, and — when the link is good enough — manual control.

The platform backend today is **Hugging Face Spaces (FastAPI)** for inspection jobs, **Vercel**
for the Next.js frontend, **Supabase Postgres** for data, **Cloudflare** for TLS. None of these
is suitable for long-lived realtime sockets / WebRTC signaling / TURN, so live ops needs a new
always-on relay component.

This is explicitly a **multi-spec program**. This document is the umbrella design; each build
phase below gets its own spec → plan → build cycle.

## 2. Goals / Non-Goals

**Goals**
- Live telemetry (position, attitude, battery, mode, GPS sats, link health) in the browser.
- Live video: RGB (piloting) + thermal pseudo-color (live hotspot spotting).
- Mission control: upload mission, arm, takeoff, pause, resume, RTL, land, goto-here.
- Tiered manual control gated on measured link quality (sticks only on a low-latency link).
- Works over **both** on-site WiFi (low latency) and LTE/4G (behind carrier NAT).
- Reuse the existing mission planner (Leaflet map, saved missions, waypoint exporters).
- ~90% buildable/testable against **ArduPilot SITL** before real hardware exists.

**Non-Goals (this program)**
- Raw real-time stick flying *over the public internet* (designed out as unsafe).
- Live orthomosaic / 3D / digital-twin streaming (heavy compute, out of scope).
- Replacing the post-flight inspection pipeline (live ops *hands off* to it, doesn't replace it).
- Multi-drone swarm coordination (the design is per-drone; relay supports many drones but no
  cross-drone choreography).

## 3. Architecture

The drone always dials **out**, so carrier NAT / LTE is never an inbound problem.

```
 Pixhawk(ArduPilot) --UART--> Jetson Orin Nano          Oracle A1 VM              Browser (/platform)
        ▲                     ┌──────────────┐         ┌──────────────┐         ┌──────────────┐
        │  MAVLink            │ drone-agent  │  WSS out │   relay      │  WSS    │  Live Ops    │
        └─────────────────────┤ (systemd)    ├────────►│  + coturn    │◄───────►│  cockpit     │
                              │  GStreamer   │═════════ WebRTC media ═══════════►│  video+HUD   │
                              └──────────────┘ (P2P, or relayed via coturn)      └──────────────┘
```

### 3.1 Hosts & why
- **Relay = Oracle A1 free VM** (4 ARM cores / 24 GB Always-Free). Holds persistent sockets,
  runs `coturn`, optionally a MAVLink router. Free, full control, native UDP/TURN. Small enough
  to lift to Fly.io later if needed (not a one-way door).
- **HF Spaces stays** as the inspection/report backend; it does **not** overlap with live ops.
- **Cloudflare** terminates TLS for `wss://` and `turns://`.

## 4. Components

### 4.1 `axalon-drone-agent` (Jetson Orin Nano, Python, systemd)
- **MAVLink link:** `pymavlink` to the Cube over UART/USB.
- **Telemetry pump:** reads MAVLink, emits normalized telemetry JSON at 4–10 Hz to the relay.
- **Command executor:** receives command frames, validates against an allow-list + altitude/
  geofence checks, translates to MAVLink (arm, mode, takeoff, mission upload, goto, RTL, land).
  **Never blind-forwards.**
- **Video:** GStreamer pipelines → WebRTC; two tracks — webcam (V4L2 → H.264 via Orin NVENC) and
  thermal (iTL612R pseudo-color → H.264).
- **Recording:** writes RAW16 thermal + RGB pairs to local disk for the existing post-flight
  inspection pipeline (timestamped for GPS injection per `drone-camera-specs`).
- **Heartbeat / deadman:** expects relay heartbeats; on loss > threshold triggers a configured
  ArduPilot failsafe (Hold / RTL / Land).
- **Link probe:** measures RTT/jitter to the relay, publishes a **link tier** (GREEN/AMBER/RED).

### 4.2 `axalon-relay` (Oracle A1 VM, Python async)
- **Drone registry:** authenticates each drone with a per-drone bootstrap token; tracks by `drone_id`.
- **Operator connections:** authenticated with the platform session/JWT.
- **Telemetry fan-out:** drone → all subscribed browsers.
- **Command routing:** browser → drone, gated by a **single-operator control lock** (server-enforced).
- **WebRTC signaling:** brokers SDP/ICE between Jetson and browser.
- **Audit:** command log persisted to Supabase.
- **`coturn`** (same box): STUN + TURN relay for media when P2P fails (CGNAT on LTE).

### 4.3 Cockpit (Vercel Next.js, new `/platform` "Live Ops" tab)
- Reuses the mission-planner **Leaflet** map: drone marker + heading arrow + breadcrumb trail.
- Telemetry HUD: battery, altitude, ground speed, mode, GPS sats, **link tier**, latency.
- Video panels: RGB + thermal (toggle / side-by-side) via WebRTC.
- Command buttons with confirm gates on destructive ops (arm/takeoff/land).
- Control-lock acquire/release; non-holders are view-only.
- Manual stick widget — **only enabled on GREEN link**, with live latency + deadman indicator.
- "Upload to drone" on existing saved missions → relay → agent → ArduPilot mission upload.

## 5. Data Flows
- **Telemetry:** Pixhawk →(MAVLink)→ agent →(WSS JSON)→ relay →(WSS fan-out)→ browsers. 4–10 Hz.
- **Commands:** browser →(WSS, control-lock checked)→ relay →(WSS)→ agent →(MAVLink)→ Pixhawk.
  Each command ACKed back along the same path with a `cmd_id`.
- **Video:** agent GStreamer/WebRTC ⇄ (signaling via relay; media P2P or via coturn) ⇄ browser.
  H.264, hardware-encoded.
- **Recording:** agent local disk → after landing → existing upload→inspect pipeline (HF backend).

## 6. Safety Model (link-quality-aware tiers)

| Tier | Link | Allowed |
|------|------|---------|
| **GREEN** | on-site WiFi, < 50 ms | Tier 3 manual sticks + everything below |
| **AMBER** | LTE, < 300 ms | Tier 2: arm/takeoff/pause/resume/RTL/land/goto, mission upload |
| **RED** | degraded / lost | commands disabled, RTL armed, deadman primed |

- Tier is computed from the agent's link probe; the relay enforces it server-side (UI gating is
  cosmetic, the relay is authoritative).
- Command allow-list + altitude/geofence validation **on the agent**.
- Confirm gates on arm / takeoff / land in the UI.
- ArduPilot fence is the hard boundary; platform shows soft warnings.
- Deadman: agent → ArduPilot failsafe on relay heartbeat loss.
- Exactly one operator holds the control lock at a time.

## 7. Auth & Security
- **Drone:** per-drone bootstrap token provisioned once, stored on the Jetson; relay verifies.
- **Operator:** existing platform session, upgraded to a real session/JWT for control actions.
- All transport is WSS/TLS (Cloudflare); TURN uses time-limited credentials.
- Full command audit trail in Supabase.
- Control actions require an authenticated session **and** the control lock.

## 8. Testing Strategy
- **ArduPilot SITL** is the backbone of testing — telemetry, commands, mission upload, the safety
  state machine, and the cockpit can all run against simulation, no hardware required.
- **Agent:** unit tests for MAVLink translation + safety/allow-list against SITL.
- **Relay:** unit/integration tests for routing, control-lock, authz, fan-out, tier enforcement.
- **Frontend:** component tests (HUD, command buttons, tier gating); e2e against SITL + relay.
- **Link-tier state machine:** unit tested in isolation.
- Coverage target 80%+ per the project testing rules.

## 9. Build Program (each phase = its own spec → plan → build)

1. **Phase 1 — Relay + agent skeleton + live telemetry (Tier 1) over SITL.**
   The backbone: drone→cloud→browser telemetry on the map. No video, no commands. Proves the
   whole transport path, testable with zero hardware. **← first implementation slice.**
2. **Phase 2 — Commands + control-lock + safety state machine (Tier 2) over SITL.**
3. **Phase 3 — Video: WebRTC + coturn** (webcam first, then thermal).
4. **Phase 4 — Cockpit UI** wiring telemetry + commands + video into the `/platform` Live Ops tab.
5. **Phase 5 — Manual tier (Tier 3) + link-quality gating.**
6. **Phase 6 — Hardware bring-up** (real Pixhawk + Jetson) + recording → inspection-pipeline handoff.

## 10. Open Questions / Deferred
- Exact telemetry JSON schema (settle in Phase 1 spec).
- Whether the relay also acts as a MAVLink router (mavlink-router/mavp2p) for desktop GCS
  (Mission Planner/QGC) access in parallel — nice-to-have, decide in Phase 2.
- Thermal live encode CPU budget on the Orin (validate in Phase 3).
- Oracle Always-Free idle-reclaim mitigation (keep-alive cron vs paid pin) — ops detail for Phase 1 deploy.
