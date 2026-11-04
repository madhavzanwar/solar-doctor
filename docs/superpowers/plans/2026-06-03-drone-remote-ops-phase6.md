# Drone Remote Ops — Phase 6 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the whole stack onto real hardware (Pixhawk/Cube + Jetson Orin Nano), and close the loop with the existing inspection pipeline: the agent records RGB + thermal frame pairs in flight, injects GPS by timestamp, and on landing hands the capture off to the platform's batch inspection endpoint.

**Architecture:** Two strands. (1) **Hardware bring-up** — point the agent's MAVLink at the real Cube over serial, plus systemd/udev/calibration/failsafe setup (mostly ops/docs). (2) **Recording → handoff** — the agent tees frames to disk during flight (timestamped), matches each frame to the nearest telemetry sample for GPS (pure, tested), detects landing (armed→disarmed edge, pure, tested), then POSTs the capture folder + `park_id` to the existing platform batch endpoint.

**Tech Stack:** Builds on Phases 1–5. Python `pymavlink` (serial), `httpx` for the handoff POST. Reuses the post-flight pipeline already in `platform/` (see CLAUDE.md / the `analysis-pipeline` skill). No new frontend.

**Spec:** `docs/superpowers/specs/2026-06-03-drone-remote-operations-design.md` (Phase 6: hardware + recording→pipeline handoff).
**Depends on:** Phases 1–5 implemented; the existing platform inspection pipeline + a batch ingest endpoint.

---

## Conventions
- Python under `drone/`; tests `python -m pytest drone/tests -v`. Commit after every green step.
- **GPS injection** matches saved-frame timestamps to the telemetry log; sub-second tolerance.
- Per `drone-camera-specs`, the thermal core has NO EXIF GPS — injection is mandatory.

---

## Task 1: Verify the real batch ingest endpoint

**Files:** (read-only investigation, no code yet)

- [ ] **Step 1: Find the platform endpoint the handoff will call**

Read `platform/api/app.py` and the `analysis-pipeline` skill. Identify the existing
batch/ingest endpoint (the one the `/platform` upload UI already uses — likely a
`POST /batch` or `POST /ingest`/`/jobs` accepting a folder/zip + `park_id`). Record
its exact path, auth (Bearer), and request shape. **Do not guess** — the handoff
client in Task 5 must match it. Note the findings in this task's checkbox before
proceeding. If no suitable endpoint exists, the smallest addition is a
`POST /batch` that accepts `{park_id, folder}`; add it following the `platform-api`
skill conventions, but prefer the existing one.

- [ ] **Step 2: Record the contract**

Write the discovered contract as a comment block at the top of the (soon-to-exist)
`drone/agent/handoff.py` once created in Task 5, e.g.:
`# POST {BASE}/batch  Bearer {token}  json={"park_id": str, "folder": str} -> {"job_id": str}`

---

## Task 2: GPS injection (timestamp → nearest telemetry sample)

**Files:**
- Create: `drone/agent/gps_inject.py`
- Test: `drone/tests/test_gps_inject.py`

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_gps_inject.py
import pytest
from drone.agent.gps_inject import nearest_fix, TelemetryFix


def _log():
    return [
        TelemetryFix(ts=100.0, lat=28.40, lon=77.10, alt_rel_m=40.0),
        TelemetryFix(ts=100.5, lat=28.41, lon=77.10, alt_rel_m=40.0),
        TelemetryFix(ts=101.0, lat=28.42, lon=77.10, alt_rel_m=41.0),
    ]


def test_picks_closest_sample_in_time():
    fix = nearest_fix(_log(), frame_ts=100.6, tolerance_s=0.5)
    assert fix is not None
    assert fix.lat == 28.41  # 100.5 is nearest to 100.6


def test_returns_none_outside_tolerance():
    assert nearest_fix(_log(), frame_ts=200.0, tolerance_s=0.5) is None


def test_empty_log_returns_none():
    assert nearest_fix([], frame_ts=100.0, tolerance_s=0.5) is None


def test_exact_match():
    fix = nearest_fix(_log(), frame_ts=101.0, tolerance_s=0.5)
    assert fix.alt_rel_m == 41.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_gps_inject.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.agent.gps_inject'`

- [ ] **Step 3: Write `drone/agent/gps_inject.py`**

```python
# drone/agent/gps_inject.py
"""Match a saved frame's capture timestamp to the nearest telemetry GPS sample.

The thermal core has no EXIF GPS (see drone-camera-specs), so the agent keeps a
rolling telemetry log during flight and, post-flight, stamps each frame with the
closest-in-time fix. Pure + tested; the file IO that uses it lives in recorder.py.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TelemetryFix:
    ts: float
    lat: float
    lon: float
    alt_rel_m: float


def nearest_fix(log: list[TelemetryFix], frame_ts: float,
                tolerance_s: float) -> TelemetryFix | None:
    if not log:
        return None
    best = min(log, key=lambda f: abs(f.ts - frame_ts))
    return best if abs(best.ts - frame_ts) <= tolerance_s else None
```

- [ ] **Step 4: Run test**

Run: `python -m pytest drone/tests/test_gps_inject.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add drone/agent/gps_inject.py drone/tests/test_gps_inject.py
git commit -m "feat(agent): GPS injection by nearest telemetry timestamp"
```

---

## Task 3: Landing detector (armed→disarmed edge)

**Files:**
- Create: `drone/agent/landing.py`
- Test: `drone/tests/test_landing.py`

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_landing.py
from drone.agent.landing import LandingDetector


def test_detects_arm_then_disarm_transition():
    d = LandingDetector()
    assert d.update(armed=False) is False
    assert d.update(armed=True) is False   # took off
    assert d.update(armed=True) is False
    assert d.update(armed=False) is True   # landed -> fire once


def test_fires_only_once_per_flight():
    d = LandingDetector()
    d.update(armed=True)
    assert d.update(armed=False) is True
    assert d.update(armed=False) is False  # already fired
    d.update(armed=True)                    # new flight
    assert d.update(armed=False) is True    # fires again


def test_no_fire_if_never_armed():
    d = LandingDetector()
    assert d.update(armed=False) is False
    assert d.update(armed=False) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_landing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.agent.landing'`

- [ ] **Step 3: Write `drone/agent/landing.py`**

```python
# drone/agent/landing.py
"""Detect a landing as an armed->disarmed edge, firing the handoff exactly once
per flight. Pure state machine driven by the `armed` telemetry field.
"""
from __future__ import annotations


class LandingDetector:
    def __init__(self) -> None:
        self._was_armed = False
        self._flew = False

    def update(self, armed: bool) -> bool:
        landed = False
        if armed:
            self._was_armed = True
            self._flew = True
        elif self._was_armed and self._flew:
            landed = True
            self._flew = False  # consume; require a new arm to fire again
        self._was_armed = armed
        return landed
```

- [ ] **Step 4: Run test**

Run: `python -m pytest drone/tests/test_landing.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add drone/agent/landing.py drone/tests/test_landing.py
git commit -m "feat(agent): landing detector (armed->disarmed edge, fires once)"
```

---

## Task 4: Capture sidecar writer (frame → GPS sidecar JSON)

**Files:**
- Create: `drone/agent/recorder.py`
- Test: `drone/tests/test_recorder.py`

The recorder's pure core builds the per-frame sidecar (filename + injected GPS) and
the capture manifest. Actual camera frame capture is hardware glue verified on the
Jetson; here we test the sidecar/manifest construction with a temp dir.

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_recorder.py
import json
from pathlib import Path
from drone.agent.gps_inject import TelemetryFix
from drone.agent.recorder import write_sidecar, build_manifest


def test_write_sidecar_embeds_gps(tmp_path):
    fix = TelemetryFix(ts=100.5, lat=28.41, lon=77.10, alt_rel_m=40.0)
    p = write_sidecar(tmp_path, frame_name="img_001.jpg", frame_ts=100.6, fix=fix)
    data = json.loads(Path(p).read_text())
    assert data["frame"] == "img_001.jpg"
    assert data["lat"] == 28.41
    assert data["alt_rel_m"] == 40.0
    assert data["gps_source"] == "telemetry-injected"


def test_write_sidecar_marks_missing_gps(tmp_path):
    p = write_sidecar(tmp_path, frame_name="img_002.jpg", frame_ts=999.0, fix=None)
    data = json.loads(Path(p).read_text())
    assert data["gps_source"] == "none"
    assert data["lat"] is None


def test_build_manifest_lists_frames():
    m = build_manifest(park_id="park-7", frames=["img_001.jpg", "img_002.jpg"])
    assert m["park_id"] == "park-7"
    assert m["frame_count"] == 2
    assert "img_001.jpg" in m["frames"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_recorder.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.agent.recorder'`

- [ ] **Step 3: Write `drone/agent/recorder.py`**

```python
# drone/agent/recorder.py
"""Capture recording helpers.

Pure parts (tested): write a per-frame GPS sidecar and build the capture manifest
the handoff sends to the platform. The live frame-grab loop (GStreamer/V4L2 +
thermal RAW16) is hardware glue added in main.py on the Jetson; it reuses
`build_video_pipeline`'s `tee` for the RGB track and the iTL612R SDK for thermal.
"""
from __future__ import annotations

import json
from pathlib import Path

from drone.agent.gps_inject import TelemetryFix


def write_sidecar(out_dir, frame_name: str, frame_ts: float,
                  fix: TelemetryFix | None) -> str:
    payload = {
        "frame": frame_name,
        "ts": frame_ts,
        "lat": fix.lat if fix else None,
        "lon": fix.lon if fix else None,
        "alt_rel_m": fix.alt_rel_m if fix else None,
        "gps_source": "telemetry-injected" if fix else "none",
    }
    path = Path(out_dir) / (Path(frame_name).stem + ".json")
    path.write_text(json.dumps(payload, indent=2))
    return str(path)


def build_manifest(park_id: str, frames: list[str]) -> dict:
    return {"park_id": park_id, "frame_count": len(frames), "frames": list(frames)}
```

- [ ] **Step 4: Run test**

Run: `python -m pytest drone/tests/test_recorder.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add drone/agent/recorder.py drone/tests/test_recorder.py
git commit -m "feat(agent): capture sidecar + manifest builders"
```

---

## Task 5: Handoff client (POST capture → platform batch)

**Files:**
- Create: `drone/agent/handoff.py`
- Test: `drone/tests/test_handoff.py`

Uses the contract recorded in Task 1. The payload builder is pure + tested; the POST
itself is a thin `httpx` call (tested with a stub transport).

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_handoff.py
import pytest
import httpx
from drone.agent.handoff import build_handoff_payload, post_handoff


def test_payload_shape():
    p = build_handoff_payload(park_id="park-7", folder="/data/cap-1")
    assert p == {"park_id": "park-7", "folder": "/data/cap-1"}


async def test_post_handoff_sends_bearer_and_returns_job_id():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"job_id": "job-42"})

    transport = httpx.MockTransport(handler)
    out = await post_handoff(
        base_url="https://api.example.com", token="t0k",
        park_id="park-7", folder="/data/cap-1", transport=transport)
    assert out["job_id"] == "job-42"
    assert captured["auth"] == "Bearer t0k"
    assert captured["url"].endswith("/batch")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_handoff.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.agent.handoff'`

- [ ] **Step 3: Write `drone/agent/handoff.py`**

```python
# drone/agent/handoff.py
"""Post a completed capture to the platform's batch inspection endpoint.

Contract (verified in Phase 6 Task 1 — UPDATE if the real endpoint differs):
  POST {BASE}/batch  Authorization: Bearer {token}
  json = {"park_id": str, "folder": str}  ->  {"job_id": str}

`transport` is injectable so the POST is unit-tested without a server.
"""
from __future__ import annotations

import httpx


def build_handoff_payload(park_id: str, folder: str) -> dict:
    return {"park_id": park_id, "folder": folder}


async def post_handoff(*, base_url: str, token: str, park_id: str, folder: str,
                       transport: httpx.BaseTransport | None = None,
                       timeout_s: float = 30.0) -> dict:
    async with httpx.AsyncClient(transport=transport, timeout=timeout_s) as client:
        resp = await client.post(
            f"{base_url.rstrip('/')}/batch",
            headers={"Authorization": f"Bearer {token}"},
            json=build_handoff_payload(park_id, folder),
        )
        resp.raise_for_status()
        return resp.json()
```

> If Task 1 found the endpoint is not `/batch` or the field names differ, update the
> URL/payload here **and** the docstring to match — do not leave the assumed shape.

- [ ] **Step 4: Run test**

Run: `python -m pytest drone/tests/test_handoff.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add drone/agent/handoff.py drone/tests/test_handoff.py
git commit -m "feat(agent): capture handoff client to platform batch endpoint"
```

---

## Task 6: Agent main wiring — record in flight, hand off on landing

**Files:**
- Modify: `drone/agent/main.py`
- Modify: `drone/agent/config.py` (recording + handoff env)

Glue. Adds a rolling telemetry log, a landing check in the telemetry loop, and an
async handoff task. The live frame-grab itself is the only piece that needs the real
cameras; gate it behind `RECORDING_ENABLED` so SITL runs skip it.

- [ ] **Step 1: Add config**

In `drone/agent/config.py`, add:

```python
    recording_enabled: bool
    capture_dir: str
    park_id: str
    platform_api_url: str
    platform_token: str
    gps_tolerance_s: float
```

In `from_env`:

```python
            recording_enabled=os.getenv("RECORDING_ENABLED", "0") == "1",
            capture_dir=os.getenv("CAPTURE_DIR", "/data/captures"),
            park_id=os.getenv("PARK_ID", ""),
            platform_api_url=os.getenv("PLATFORM_API_URL", ""),
            platform_token=os.getenv("PLATFORM_TOKEN", ""),
            gps_tolerance_s=float(os.getenv("GPS_TOLERANCE_S", "0.5")),
```

- [ ] **Step 2: Wire recording + landing handoff into `main.py`**

Add imports and a rolling telemetry log + landing detector:

```python
    from drone.agent.gps_inject import TelemetryFix, nearest_fix
    from drone.agent.landing import LandingDetector
    from drone.agent.recorder import write_sidecar, build_manifest
    from drone.agent.handoff import post_handoff

    telem_log: list = []          # rolling TelemetryFix log (cap to ~last 20 min)
    landing = LandingDetector()
```

In `telemetry_loop`, after building `telem`, append to the log and check for landing:

```python
                    telem_log.append(TelemetryFix(
                        ts=telem.ts, lat=telem.lat, lon=telem.lon, alt_rel_m=telem.alt_rel_m))
                    if len(telem_log) > 24000:   # ~20 min @ 20Hz
                        del telem_log[: len(telem_log) - 24000]
                    if cfg.recording_enabled and landing.update(telem.armed):
                        asyncio.create_task(_do_handoff())
```

Add the handoff coroutine inside `run()` (it injects GPS into each captured frame's
sidecar, builds the manifest, and POSTs):

```python
    async def _do_handoff():
        import os as _os
        frames = [f for f in _os.listdir(cfg.capture_dir)
                  if f.endswith((".jpg", ".raw"))]
        for fname in frames:
            # capture ts is encoded in the filename suffix _<unixms>; fall back to mtime
            try:
                stem = fname.rsplit("_", 1)[1].split(".")[0]
                frame_ts = int(stem) / 1000.0
            except Exception:
                frame_ts = _os.path.getmtime(_os.path.join(cfg.capture_dir, fname))
            fix = nearest_fix(telem_log, frame_ts, cfg.gps_tolerance_s)
            write_sidecar(cfg.capture_dir, fname, frame_ts, fix)
        build_manifest(cfg.park_id, frames)  # written next to captures if desired
        if cfg.platform_api_url and cfg.park_id:
            await post_handoff(base_url=cfg.platform_api_url, token=cfg.platform_token,
                               park_id=cfg.park_id, folder=cfg.capture_dir)
```

> The live frame-grab loop (writing `img_<unixms>.jpg` + `img_<unixms>.raw` pairs) is
> hardware glue: add it as a fourth task in `asyncio.gather` only when `recording_enabled`,
> reading the webcam via V4L2 and the thermal RAW16 via the iTL612R SDK. It is verified
> on the Jetson, not in CI.

- [ ] **Step 3: Run the full unit suite**

Run: `python -m pytest drone/tests -v`
Expected: all unit tests PASS; SITL e2e SKIPPED.

- [ ] **Step 4: Commit**

```bash
git add drone/agent/main.py drone/agent/config.py
git commit -m "feat(agent): in-flight telemetry log + landing-triggered capture handoff"
```

---

## Task 7: Hardware bring-up runbook

**Files:**
- Modify: `docs/DEPLOY_DRONE_OPS.md`

Ops/docs — no code. Captures everything needed to move from SITL to the real Cube.

- [ ] **Step 1: Append the hardware section to `docs/DEPLOY_DRONE_OPS.md`**

````markdown
## Phase 6 — real hardware bring-up

### Wiring & serial
- Connect the Cube's TELEM2 (or a spare UART) to the Jetson UART (e.g. `/dev/ttyTHS1`)
  or via USB (`/dev/ttyACM0`). Set the Cube's `SERIALx_PROTOCOL=2` (MAVLink2),
  `SERIALx_BAUD=921`.
- Agent env for hardware:
  `MAVLINK_URL=serial:/dev/ttyTHS1:921600` (replace the SITL `udpin:` URL).

### udev (stable device name)
```bash
# /etc/udev/rules.d/99-axalon.rules
SUBSYSTEM=="tty", ATTRS{idVendor}=="2dae", SYMLINK+="cube"   # example Cube VID
```
Then use `MAVLINK_URL=serial:/dev/cube:921600`.

### ArduPilot pre-flight params (set once, via Mission Planner / MAVProxy)
- `FENCE_ENABLE=1`, `FENCE_ALT_MAX`, `FENCE_RADIUS` — geofence is the hard boundary.
- `FS_GCS_ENABLE` + a sensible `FS_OPTIONS` so the autopilot also fails safe if it
  loses the companion link (defense in depth alongside the agent deadman).
- Battery failsafe (`BATT_LOW_VOLT`, `BATT_FS_LOW_ACT=2` RTL).
- Calibrate: accel, compass, RC, ESC — standard ArduCopter first-flight checklist.

### systemd on the Jetson
Reuse the `axalon-drone-agent.service` from Phase 1 with the hardware env:
`MAVLINK_URL=serial:/dev/cube:921600`, `VIDEO_ENABLED=1`, `RECORDING_ENABLED=1`,
`CAPTURE_DIR=/data/captures`, `PARK_ID=<park>`, `PLATFORM_API_URL=<HF backend>`,
`PLATFORM_TOKEN=<token>`. `Restart=always`.

### First-flight safety checklist
1. Props OFF: confirm telemetry on `/platform` Live Ops, confirm ARM/DISARM acks.
2. Props OFF: confirm RTL/LAND mode changes reflect in the HUD.
3. Tethered/low hover: confirm GREEN tier on-site, manual pad translates + hovers on release.
4. Confirm geofence + battery failsafe trigger as configured.
5. Full mission: upload from planner, fly AUTO, watch telemetry + video, land →
   confirm a batch job appears in the platform.
````

- [ ] **Step 2: Commit**

```bash
git add docs/DEPLOY_DRONE_OPS.md
git commit -m "docs: hardware bring-up runbook for drone remote ops"
```

---

## Self-Review Notes (resolved)
- **Spec coverage (Phase 6):** hardware bring-up (Task 7), recording → inspection-pipeline handoff
  (Tasks 2–6: GPS injection, landing detection, sidecar/manifest, handoff client, main wiring). ✔
- **Endpoint not guessed:** Task 1 mandates verifying the real platform batch endpoint before the
  handoff client is written; Task 5 + its docstring must be updated if the contract differs. ✔
- **CI-safe:** all new logic (GPS injection, landing, sidecar, handoff payload) is pure + tested;
  the live frame-grab + serial MAVLink are hardware glue gated behind `RECORDING_ENABLED` /
  the hardware `MAVLINK_URL`, so `python -m pytest drone/tests` stays green without a drone. ✔
- **Defense in depth on link loss:** the agent deadman (Phase 2) + ArduPilot `FS_GCS`/geofence
  (Task 7) both fail safe. ✔
- **GPS injection is mandatory** per drone-camera-specs (thermal core has no EXIF GPS) — covered by
  Tasks 2 + 6. ✔
- **Carried hardening items** (from Phases 2.1/3.1): command audit log → Supabase, OPS_TOKEN →
  platform JWT, coturn TLS, thermal second track — none are Phase 6 blockers; track them in the
  backlog. ✔
```
