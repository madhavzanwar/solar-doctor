# Drone Remote Ops — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the live-telemetry backbone — a Jetson agent reads MAVLink from ArduPilot SITL, ships normalized telemetry over WSS to an always-on relay, which fans it out to the browser, which draws the drone on the map. No video, no commands yet.

**Architecture:** Three Python/TS units that talk over WebSocket. `drone/agent` (Jetson) dials *out* to `drone/relay` (Oracle VM); browsers subscribe to the relay. A shared Pydantic schema (`drone/common`) keeps the wire format honest on both ends. Everything is tested against ArduPilot SITL, so zero hardware is needed for this phase.

**Tech Stack:** Python 3.12, `pymavlink`, `fastapi` + `uvicorn` (relay WS), `websockets` (agent client), `pydantic` v2, `pytest`/`pytest-asyncio`; frontend Next.js + `vitest` + Leaflet (reused from mission planner).

**Spec:** `docs/superpowers/specs/2026-06-03-drone-remote-operations-design.md` (Phase 1).

---

## Conventions

- All new Python lives under `drone/`. Run tests with `python -m pytest drone/tests -v` from repo root.
- Add `drone/requirements.txt`; install with `pip install -r drone/requirements.txt`.
- Frontend tests: `cd website/nextjs && npx vitest run <file>`.
- Commit after every green step.

---

## Task 0: Scaffold the `drone/` package and dependencies

**Files:**
- Create: `drone/__init__.py` (empty)
- Create: `drone/common/__init__.py` (empty)
- Create: `drone/relay/__init__.py` (empty)
- Create: `drone/agent/__init__.py` (empty)
- Create: `drone/tests/__init__.py` (empty)
- Create: `drone/requirements.txt`
- Create: `drone/tests/conftest.py`

- [ ] **Step 1: Create the empty package files**

Create all five `__init__.py` files listed above with no content.

- [ ] **Step 2: Create `drone/requirements.txt`**

```text
pymavlink>=2.4.41
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
websockets>=12.0
pydantic>=2.6.0
pytest>=8.0.0
pytest-asyncio>=0.23.0
httpx>=0.27.0
```

- [ ] **Step 3: Create `drone/pytest.ini` and `drone/tests/conftest.py`**

`drone/pytest.ini`:

```ini
[pytest]
asyncio_mode = auto
testpaths = drone/tests
```

`drone/tests/conftest.py`:

```python
import pytest


@pytest.fixture
def anyio_backend():
    return "asyncio"
```

- [ ] **Step 4: Install and verify**

Run: `pip install -r drone/requirements.txt`
Run: `python -c "import pymavlink, fastapi, websockets, pydantic; print('ok')"`
Expected: `ok`

- [ ] **Step 5: Commit**

```bash
git add drone/ && git commit -m "chore: scaffold drone/ package for remote ops phase 1"
```

---

## Task 1: Shared telemetry schema

**Files:**
- Create: `drone/common/telemetry.py`
- Test: `drone/tests/test_telemetry_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_telemetry_schema.py
import time
import pytest
from pydantic import ValidationError
from drone.common.telemetry import Telemetry, LinkTier


def _valid_kwargs():
    return dict(
        drone_id="sitl-01",
        ts=time.time(),
        lat=28.4001,
        lon=77.1002,
        alt_rel_m=40.0,
        alt_amsl_m=255.0,
        heading_deg=90.0,
        groundspeed_ms=7.5,
        battery_pct=82.0,
        battery_voltage=22.1,
        mode="GUIDED",
        armed=False,
        gps_fix=3,
        satellites=14,
        roll_deg=1.2,
        pitch_deg=-0.5,
        yaw_deg=90.0,
        seq=42,
    )


def test_telemetry_roundtrips_through_json():
    t = Telemetry(**_valid_kwargs())
    raw = t.model_dump_json()
    again = Telemetry.model_validate_json(raw)
    assert again == t
    assert again.link_tier == LinkTier.GREEN  # default until computed


def test_heading_must_be_within_0_360():
    kw = _valid_kwargs()
    kw["heading_deg"] = 400.0
    with pytest.raises(ValidationError):
        Telemetry(**kw)


def test_battery_pct_clamped_range():
    kw = _valid_kwargs()
    kw["battery_pct"] = 150.0
    with pytest.raises(ValidationError):
        Telemetry(**kw)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_telemetry_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.common.telemetry'`

- [ ] **Step 3: Write minimal implementation**

```python
# drone/common/telemetry.py
"""Wire format shared by the drone agent and the relay.

This is the single source of truth for the telemetry frame. Both the agent
(producer) and the relay/browser (consumers) validate against it so the wire
contract can never silently drift.
"""
from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class LinkTier(str, Enum):
    GREEN = "GREEN"   # low latency, manual unlocked (later phases)
    AMBER = "AMBER"   # usable, mission-control only
    RED = "RED"       # degraded/lost, commands disabled


class Telemetry(BaseModel):
    """One telemetry sample, normalized from MAVLink."""
    drone_id: str
    ts: float = Field(..., description="Unix seconds when sampled on the agent")
    seq: int = Field(..., ge=0, description="Monotonic frame counter from the agent")

    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    alt_rel_m: float
    alt_amsl_m: float
    heading_deg: float = Field(..., ge=0.0, le=360.0)
    groundspeed_ms: float = Field(..., ge=0.0)

    battery_pct: float = Field(..., ge=0.0, le=100.0)
    battery_voltage: float = Field(..., ge=0.0)

    mode: str
    armed: bool
    gps_fix: int = Field(..., ge=0)
    satellites: int = Field(..., ge=0)

    roll_deg: float
    pitch_deg: float
    yaw_deg: float

    link_tier: LinkTier = LinkTier.GREEN


class Envelope(BaseModel):
    """Top-level frame on the wire. `type` discriminates message kinds so later
    phases (commands, acks, signaling) reuse the same socket."""
    type: str
    telemetry: Telemetry | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest drone/tests/test_telemetry_schema.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add drone/common/telemetry.py drone/tests/test_telemetry_schema.py
git commit -m "feat(drone): shared telemetry wire schema"
```

---

## Task 2: Relay connection manager + fan-out

**Files:**
- Create: `drone/relay/manager.py`
- Test: `drone/tests/test_relay_manager.py`

The manager is transport-agnostic: it speaks to "sinks" (anything with an async
`send_text(str)`), so it can be unit-tested without real WebSockets.

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_relay_manager.py
import pytest
from drone.relay.manager import RelayManager


class FakeSink:
    def __init__(self):
        self.sent: list[str] = []
        self.closed = False

    async def send_text(self, data: str):
        if self.closed:
            raise RuntimeError("sink closed")
        self.sent.append(data)


async def test_telemetry_fans_out_to_all_ops_for_that_drone():
    mgr = RelayManager()
    ops_a, ops_b = FakeSink(), FakeSink()
    mgr.add_operator("sitl-01", ops_a)
    mgr.add_operator("sitl-01", ops_b)
    mgr.add_operator("other", FakeSink())  # must NOT receive

    await mgr.broadcast_telemetry("sitl-01", '{"hello":1}')

    assert ops_a.sent == ['{"hello":1}']
    assert ops_b.sent == ['{"hello":1}']


async def test_broadcast_to_drone_with_no_operators_is_noop():
    mgr = RelayManager()
    await mgr.broadcast_telemetry("ghost", "{}")  # must not raise


async def test_dead_operator_is_dropped_and_does_not_break_others():
    mgr = RelayManager()
    good, dead = FakeSink(), FakeSink()
    dead.closed = True
    mgr.add_operator("sitl-01", good)
    mgr.add_operator("sitl-01", dead)

    await mgr.broadcast_telemetry("sitl-01", "x")

    assert good.sent == ["x"]
    assert dead not in mgr.operators_for("sitl-01")


async def test_remove_operator():
    mgr = RelayManager()
    s = FakeSink()
    mgr.add_operator("sitl-01", s)
    mgr.remove_operator("sitl-01", s)
    assert s not in mgr.operators_for("sitl-01")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_relay_manager.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.relay.manager'`

- [ ] **Step 3: Write minimal implementation**

```python
# drone/relay/manager.py
"""In-memory registry of connected drones and operators, with telemetry fan-out.

A "sink" is any object with `async def send_text(str)`. FastAPI's WebSocket
satisfies this, and tests use a fake. Keeping the manager transport-agnostic is
what makes the routing logic unit-testable without sockets.
"""
from __future__ import annotations

from typing import Protocol


class Sink(Protocol):
    async def send_text(self, data: str) -> None: ...


class RelayManager:
    def __init__(self) -> None:
        self._operators: dict[str, set[Sink]] = {}
        self._drones: dict[str, Sink] = {}

    # --- operators ---
    def add_operator(self, drone_id: str, sink: Sink) -> None:
        self._operators.setdefault(drone_id, set()).add(sink)

    def remove_operator(self, drone_id: str, sink: Sink) -> None:
        self._operators.get(drone_id, set()).discard(sink)

    def operators_for(self, drone_id: str) -> set[Sink]:
        return self._operators.get(drone_id, set())

    # --- drones ---
    def register_drone(self, drone_id: str, sink: Sink) -> None:
        self._drones[drone_id] = sink

    def unregister_drone(self, drone_id: str) -> None:
        self._drones.pop(drone_id, None)

    def is_online(self, drone_id: str) -> bool:
        return drone_id in self._drones

    # --- fan-out ---
    async def broadcast_telemetry(self, drone_id: str, raw: str) -> None:
        dead: list[Sink] = []
        for sink in list(self.operators_for(drone_id)):
            try:
                await sink.send_text(raw)
            except Exception:
                dead.append(sink)
        for sink in dead:
            self.remove_operator(drone_id, sink)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest drone/tests/test_relay_manager.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add drone/relay/manager.py drone/tests/test_relay_manager.py
git commit -m "feat(relay): connection manager + telemetry fan-out"
```

---

## Task 3: Relay auth

**Files:**
- Create: `drone/relay/config.py`
- Create: `drone/relay/auth.py`
- Test: `drone/tests/test_relay_auth.py`

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_relay_auth.py
import pytest
from drone.relay.auth import verify_drone_token, verify_operator_token, AuthError


def test_valid_drone_token_returns_drone_id(monkeypatch):
    monkeypatch.setenv("DRONE_TOKENS", "sitl-01:secrettok,real-02:othertok")
    assert verify_drone_token("sitl-01", "secrettok") == "sitl-01"


def test_wrong_drone_token_raises(monkeypatch):
    monkeypatch.setenv("DRONE_TOKENS", "sitl-01:secrettok")
    with pytest.raises(AuthError):
        verify_drone_token("sitl-01", "nope")


def test_unknown_drone_id_raises(monkeypatch):
    monkeypatch.setenv("DRONE_TOKENS", "sitl-01:secrettok")
    with pytest.raises(AuthError):
        verify_drone_token("ghost", "secrettok")


def test_operator_token_matches_shared_secret(monkeypatch):
    monkeypatch.setenv("OPS_TOKEN", "opspass")
    assert verify_operator_token("opspass") is True


def test_operator_token_rejects_bad(monkeypatch):
    monkeypatch.setenv("OPS_TOKEN", "opspass")
    with pytest.raises(AuthError):
        verify_operator_token("bad")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_relay_auth.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.relay.auth'`

- [ ] **Step 3: Write minimal implementation**

```python
# drone/relay/config.py
"""Env-driven relay configuration. No secrets in code (project security rule)."""
from __future__ import annotations

import os


def drone_tokens() -> dict[str, str]:
    """Parse DRONE_TOKENS='id1:tok1,id2:tok2' into {id: tok}."""
    raw = os.getenv("DRONE_TOKENS", "").strip()
    out: dict[str, str] = {}
    for pair in filter(None, (p.strip() for p in raw.split(","))):
        drone_id, _, token = pair.partition(":")
        if drone_id and token:
            out[drone_id] = token
    return out


def ops_token() -> str:
    return os.getenv("OPS_TOKEN", "")
```

```python
# drone/relay/auth.py
"""Authentication for the relay's two client kinds.

Phase 1 uses simple shared secrets from env:
- drones authenticate with a per-drone token (DRONE_TOKENS)
- operators authenticate with one shared OPS_TOKEN (replaced by the platform
  session/JWT in a later phase)

Uses hmac.compare_digest to avoid timing leaks.
"""
from __future__ import annotations

import hmac

from drone.relay import config


class AuthError(Exception):
    pass


def verify_drone_token(drone_id: str, token: str) -> str:
    expected = config.drone_tokens().get(drone_id)
    if expected is None or not hmac.compare_digest(expected, token):
        raise AuthError("invalid drone credentials")
    return drone_id


def verify_operator_token(token: str) -> bool:
    expected = config.ops_token()
    if not expected or not hmac.compare_digest(expected, token):
        raise AuthError("invalid operator credentials")
    return True
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest drone/tests/test_relay_auth.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add drone/relay/config.py drone/relay/auth.py drone/tests/test_relay_auth.py
git commit -m "feat(relay): env-driven config + token auth"
```

---

## Task 4: Relay FastAPI app (WS endpoints + health)

**Files:**
- Create: `drone/relay/server.py`
- Test: `drone/tests/test_relay_server.py`

- [ ] **Step 1: Write the failing test**

Uses FastAPI's `TestClient` which supports `websocket_connect`.

```python
# drone/tests/test_relay_server.py
import json
import pytest
from fastapi.testclient import TestClient
from drone.relay.server import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DRONE_TOKENS", "sitl-01:dtok")
    monkeypatch.setenv("OPS_TOKEN", "otok")
    return TestClient(create_app())


def test_health_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_drone_frame_reaches_operator(client):
    # operator subscribes first
    with client.websocket_connect("/ws/ops/sitl-01?token=otok") as ops:
        with client.websocket_connect("/ws/drone/sitl-01?token=dtok") as drone:
            frame = {"type": "telemetry", "telemetry": None}
            drone.send_text(json.dumps(frame))
            received = ops.receive_text()
            assert json.loads(received)["type"] == "telemetry"


def test_drone_rejected_with_bad_token(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/drone/sitl-01?token=WRONG"):
            pass


def test_ops_rejected_with_bad_token(client):
    with pytest.raises(Exception):
        with client.websocket_connect("/ws/ops/sitl-01?token=WRONG"):
            pass
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_relay_server.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.relay.server'`

- [ ] **Step 3: Write minimal implementation**

```python
# drone/relay/server.py
"""Relay FastAPI app.

Two WebSocket endpoints share one RelayManager:
- /ws/drone/{drone_id}?token=... : the Jetson agent pushes telemetry frames here.
- /ws/ops/{drone_id}?token=...   : browsers subscribe; receive fanned-out frames.

Phase 1 only relays drone->ops telemetry. Command routing (ops->drone) is added
in Phase 2 but the manager + envelope already accommodate it.
"""
from __future__ import annotations

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status

from drone.relay.auth import AuthError, verify_drone_token, verify_operator_token
from drone.relay.manager import RelayManager


def create_app() -> FastAPI:
    app = FastAPI(title="Axalon Drone Relay")
    mgr = RelayManager()
    app.state.manager = mgr

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.websocket("/ws/drone/{drone_id}")
    async def drone_ws(ws: WebSocket, drone_id: str, token: str = ""):
        try:
            verify_drone_token(drone_id, token)
        except AuthError:
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        await ws.accept()
        mgr.register_drone(drone_id, ws)
        try:
            while True:
                raw = await ws.receive_text()
                await mgr.broadcast_telemetry(drone_id, raw)
        except WebSocketDisconnect:
            pass
        finally:
            mgr.unregister_drone(drone_id)

    @app.websocket("/ws/ops/{drone_id}")
    async def ops_ws(ws: WebSocket, drone_id: str, token: str = ""):
        try:
            verify_operator_token(token)
        except AuthError:
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        await ws.accept()
        mgr.add_operator(drone_id, ws)
        try:
            while True:
                await ws.receive_text()  # Phase 1: ignore inbound from ops
        except WebSocketDisconnect:
            pass
        finally:
            mgr.remove_operator(drone_id, ws)

    return app


app = create_app()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest drone/tests/test_relay_server.py -v`
Expected: PASS (4 passed)

- [ ] **Step 5: Commit**

```bash
git add drone/relay/server.py drone/tests/test_relay_server.py
git commit -m "feat(relay): FastAPI WS endpoints for drone + ops with auth"
```

---

## Task 5: Agent MAVLink → telemetry normalizer

**Files:**
- Create: `drone/agent/mavlink_source.py`
- Test: `drone/tests/test_mavlink_source.py`

The normalizer accumulates fields from several MAVLink message types into a
`Telemetry`. It is pure (no socket, no real mavlink connection) so it is fully
unit-testable with synthetic message objects.

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_mavlink_source.py
from types import SimpleNamespace
from drone.agent.mavlink_source import TelemetryAccumulator


def msg(type_name, **fields):
    m = SimpleNamespace(**fields)
    m.get_type = lambda: type_name
    return m


def test_accumulator_builds_telemetry_from_message_stream():
    acc = TelemetryAccumulator(drone_id="sitl-01")

    acc.update(msg("GLOBAL_POSITION_INT",
                   lat=284_000_000, lon=771_000_000,  # 1e7 degrees
                   relative_alt=40_000, alt=255_000,  # mm
                   hdg=9000,                            # cdeg
                   vx=500, vy=0))                       # cm/s
    acc.update(msg("ATTITUDE", roll=0.02, pitch=-0.01, yaw=1.57))
    acc.update(msg("SYS_STATUS", battery_remaining=82, voltage_battery=22100))
    acc.update(msg("GPS_RAW_INT", fix_type=3, satellites_visible=14))
    acc.update(msg("HEARTBEAT", custom_mode=4, base_mode=128))  # GUIDED, armed

    t = acc.build(ts=123.0, seq=1)
    assert t.drone_id == "sitl-01"
    assert round(t.lat, 4) == 28.4
    assert round(t.lon, 4) == 77.1
    assert t.alt_rel_m == 40.0
    assert t.alt_amsl_m == 255.0
    assert t.heading_deg == 90.0
    assert round(t.groundspeed_ms, 2) == 5.0
    assert t.battery_pct == 82.0
    assert round(t.battery_voltage, 1) == 22.1
    assert t.gps_fix == 3
    assert t.satellites == 14
    assert t.mode == "GUIDED"
    assert t.armed is True


def test_build_before_any_position_returns_none():
    acc = TelemetryAccumulator(drone_id="sitl-01")
    assert acc.build(ts=1.0, seq=0) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_mavlink_source.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.agent.mavlink_source'`

- [ ] **Step 3: Write minimal implementation**

```python
# drone/agent/mavlink_source.py
"""Translate the ArduPilot MAVLink message stream into our Telemetry schema.

`TelemetryAccumulator` is intentionally pure: feed it decoded mavlink messages
via `update()`, then call `build()` to snapshot the current state. The real
mavlink connection lives in main.py, which keeps this unit testable with
synthetic SimpleNamespace messages.
"""
from __future__ import annotations

import math

from drone.common.telemetry import Telemetry

# ArduCopter flight-mode numbers (custom_mode) -> name.
_COPTER_MODES = {
    0: "STABILIZE", 2: "ALT_HOLD", 3: "AUTO", 4: "GUIDED",
    5: "LOITER", 6: "RTL", 9: "LAND", 16: "POSHOLD",
}
_MAV_MODE_FLAG_SAFETY_ARMED = 128


class TelemetryAccumulator:
    def __init__(self, drone_id: str) -> None:
        self.drone_id = drone_id
        self._pos: dict | None = None
        self._att = {"roll": 0.0, "pitch": 0.0, "yaw": 0.0}
        self._battery_pct = 0.0
        self._battery_v = 0.0
        self._gps_fix = 0
        self._sats = 0
        self._mode = "UNKNOWN"
        self._armed = False

    def update(self, m) -> None:
        t = m.get_type()
        if t == "GLOBAL_POSITION_INT":
            self._pos = {
                "lat": m.lat / 1e7,
                "lon": m.lon / 1e7,
                "alt_rel_m": m.relative_alt / 1000.0,
                "alt_amsl_m": m.alt / 1000.0,
                "heading_deg": (m.hdg / 100.0) % 360.0,
                "groundspeed_ms": math.hypot(m.vx, m.vy) / 100.0,
            }
        elif t == "ATTITUDE":
            self._att = {"roll": m.roll, "pitch": m.pitch, "yaw": m.yaw}
        elif t == "SYS_STATUS":
            self._battery_pct = max(0.0, float(m.battery_remaining))
            self._battery_v = m.voltage_battery / 1000.0
        elif t == "GPS_RAW_INT":
            self._gps_fix = m.fix_type
            self._sats = m.satellites_visible
        elif t == "HEARTBEAT":
            self._mode = _COPTER_MODES.get(m.custom_mode, f"MODE_{m.custom_mode}")
            self._armed = bool(m.base_mode & _MAV_MODE_FLAG_SAFETY_ARMED)

    def build(self, ts: float, seq: int) -> Telemetry | None:
        if self._pos is None:
            return None  # no fix yet — nothing meaningful to send
        return Telemetry(
            drone_id=self.drone_id,
            ts=ts,
            seq=seq,
            lat=self._pos["lat"],
            lon=self._pos["lon"],
            alt_rel_m=self._pos["alt_rel_m"],
            alt_amsl_m=self._pos["alt_amsl_m"],
            heading_deg=self._pos["heading_deg"],
            groundspeed_ms=self._pos["groundspeed_ms"],
            battery_pct=min(100.0, self._battery_pct),
            battery_voltage=self._battery_v,
            mode=self._mode,
            armed=self._armed,
            gps_fix=self._gps_fix,
            satellites=self._sats,
            roll_deg=math.degrees(self._att["roll"]),
            pitch_deg=math.degrees(self._att["pitch"]),
            yaw_deg=math.degrees(self._att["yaw"]) % 360.0,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest drone/tests/test_mavlink_source.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add drone/agent/mavlink_source.py drone/tests/test_mavlink_source.py
git commit -m "feat(agent): MAVLink->Telemetry normalizer (pure, tested)"
```

---

## Task 6: Agent WS client (outbound, with reconnect)

**Files:**
- Create: `drone/agent/ws_client.py`
- Test: `drone/tests/test_ws_client.py`

`RelayClient` wraps a `websockets` connection but takes a "connector" callable so
tests can inject a fake connection instead of opening a real socket.

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_ws_client.py
import pytest
from drone.agent.ws_client import RelayClient


class FakeConn:
    def __init__(self):
        self.sent: list[str] = []
        self.open = True

    async def send(self, data: str):
        if not self.open:
            raise ConnectionError("closed")
        self.sent.append(data)

    async def close(self):
        self.open = False


async def test_send_passes_text_to_connection():
    conn = FakeConn()

    async def connector():
        return conn

    client = RelayClient(connector)
    await client.connect()
    await client.send("frame-1")
    assert conn.sent == ["frame-1"]


async def test_send_triggers_reconnect_after_failure():
    conns = [FakeConn(), FakeConn()]
    conns[0].open = False  # first connection is already dead
    calls = {"n": 0}

    async def connector():
        c = conns[calls["n"]]
        calls["n"] += 1
        return c

    client = RelayClient(connector)
    await client.connect()
    await client.send("frame-1")  # first send fails -> reconnect -> retry
    assert conns[1].sent == ["frame-1"]
    assert calls["n"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_ws_client.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.agent.ws_client'`

- [ ] **Step 3: Write minimal implementation**

```python
# drone/agent/ws_client.py
"""Outbound WebSocket client from the agent to the relay.

Takes an async `connector()` that returns a connection object with
`async send(str)` / `async close()`. In production this opens a real
`websockets` connection; tests inject a fake. On send failure it reconnects once
and retries, so a relay restart or a brief LTE drop doesn't kill the agent.
"""
from __future__ import annotations

from typing import Awaitable, Callable, Protocol


class Connection(Protocol):
    async def send(self, data: str) -> None: ...
    async def close(self) -> None: ...


class RelayClient:
    def __init__(self, connector: Callable[[], Awaitable[Connection]]) -> None:
        self._connector = connector
        self._conn: Connection | None = None

    async def connect(self) -> None:
        self._conn = await self._connector()

    async def send(self, data: str) -> None:
        if self._conn is None:
            await self.connect()
        try:
            await self._conn.send(data)
        except Exception:
            # reconnect once and retry; let a second failure propagate
            await self.connect()
            await self._conn.send(data)

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest drone/tests/test_ws_client.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add drone/agent/ws_client.py drone/tests/test_ws_client.py
git commit -m "feat(agent): relay WS client with reconnect-on-send"
```

---

## Task 7: Agent config + main wiring

**Files:**
- Create: `drone/agent/config.py`
- Create: `drone/agent/main.py`
- Test: `drone/tests/test_agent_config.py`

`main.py` is the only piece touching the real mavlink + websockets libraries; it
is thin glue over the tested units, so it has no unit test of its own (covered by
the Task 8 SITL integration test). `config.py` is tested.

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_agent_config.py
from drone.agent.config import AgentConfig


def test_config_reads_env(monkeypatch):
    monkeypatch.setenv("DRONE_ID", "sitl-01")
    monkeypatch.setenv("DRONE_TOKEN", "dtok")
    monkeypatch.setenv("RELAY_WS_URL", "wss://relay.example.com")
    monkeypatch.setenv("MAVLINK_URL", "udpin:127.0.0.1:14550")
    monkeypatch.setenv("TELEMETRY_HZ", "5")

    cfg = AgentConfig.from_env()
    assert cfg.drone_id == "sitl-01"
    assert cfg.relay_ws_url == "wss://relay.example.com"
    assert cfg.ops_url() == "wss://relay.example.com/ws/drone/sitl-01?token=dtok"
    assert cfg.period_s == 0.2


def test_config_defaults(monkeypatch):
    monkeypatch.delenv("TELEMETRY_HZ", raising=False)
    monkeypatch.setenv("DRONE_ID", "x")
    monkeypatch.setenv("DRONE_TOKEN", "y")
    monkeypatch.setenv("RELAY_WS_URL", "wss://r")
    monkeypatch.setenv("MAVLINK_URL", "udpin:0.0.0.0:14550")
    cfg = AgentConfig.from_env()
    assert cfg.telemetry_hz == 5.0  # default
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_agent_config.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.agent.config'`

- [ ] **Step 3: Write minimal implementation**

```python
# drone/agent/config.py
"""Agent configuration from environment. No secrets in code."""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentConfig:
    drone_id: str
    drone_token: str
    relay_ws_url: str   # base, e.g. wss://relay.example.com
    mavlink_url: str    # e.g. udpin:127.0.0.1:14550 (SITL)
    telemetry_hz: float

    @classmethod
    def from_env(cls) -> "AgentConfig":
        return cls(
            drone_id=os.environ["DRONE_ID"],
            drone_token=os.environ["DRONE_TOKEN"],
            relay_ws_url=os.environ["RELAY_WS_URL"].rstrip("/"),
            mavlink_url=os.environ["MAVLINK_URL"],
            telemetry_hz=float(os.getenv("TELEMETRY_HZ", "5")),
        )

    @property
    def period_s(self) -> float:
        return 1.0 / self.telemetry_hz

    def ops_url(self) -> str:
        return f"{self.relay_ws_url}/ws/drone/{self.drone_id}?token={self.drone_token}"
```

```python
# drone/agent/main.py
"""Agent entrypoint: pump MAVLink telemetry to the relay.

Glue only — every unit it uses is tested elsewhere. Run on the Jetson (or any
box that can reach SITL) as a systemd service. See docs/DEPLOY_DRONE_OPS.md.
"""
from __future__ import annotations

import asyncio
import time

import websockets
from pymavlink import mavutil

from drone.agent.config import AgentConfig
from drone.agent.mavlink_source import TelemetryAccumulator
from drone.agent.ws_client import RelayClient
from drone.common.telemetry import Envelope


async def run(cfg: AgentConfig) -> None:
    mav = mavutil.mavlink_connection(cfg.mavlink_url)
    mav.wait_heartbeat()
    acc = TelemetryAccumulator(cfg.drone_id)

    async def connector():
        return await websockets.connect(cfg.ops_url())

    client = RelayClient(connector)
    await client.connect()

    seq = 0
    loop = asyncio.get_event_loop()
    while True:
        # drain all pending mavlink messages without blocking the event loop
        while True:
            m = await loop.run_in_executor(None, lambda: mav.recv_match(blocking=False))
            if m is None:
                break
            acc.update(m)

        telem = acc.build(ts=time.time(), seq=seq)
        if telem is not None:
            env = Envelope(type="telemetry", telemetry=telem)
            await client.send(env.model_dump_json())
            seq += 1
        await asyncio.sleep(cfg.period_s)


def main() -> None:
    asyncio.run(run(AgentConfig.from_env()))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest drone/tests/test_agent_config.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add drone/agent/config.py drone/agent/main.py drone/tests/test_agent_config.py
git commit -m "feat(agent): config + main telemetry pump wiring"
```

---

## Task 8: End-to-end integration test against ArduPilot SITL

**Files:**
- Create: `drone/tests/test_e2e_sitl.py`
- Create: `docs/DEPLOY_DRONE_OPS.md` (SITL run instructions referenced by the test)

This test is **opt-in** (skipped unless `RUN_SITL_E2E=1`), so CI stays green
without a simulator. It proves the real path: SITL → agent → relay → ops client.

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_e2e_sitl.py
import asyncio
import os

import pytest


def _sitl_enabled() -> bool:
    return os.getenv("RUN_SITL_E2E") == "1"


pytestmark = pytest.mark.skipif(
    not _sitl_enabled(), reason="set RUN_SITL_E2E=1 with ArduPilot SITL + relay + agent running"
)


async def test_telemetry_flows_sitl_to_ops():
    """With SITL + relay + agent running, an ops client receives valid telemetry."""
    import websockets
    from drone.common.telemetry import Envelope

    relay = os.getenv("RELAY_WS_URL", "ws://127.0.0.1:8800")
    ops_token = os.getenv("OPS_TOKEN", "otok")
    drone_id = os.getenv("DRONE_ID", "sitl-01")
    url = f"{relay}/ws/ops/{drone_id}?token={ops_token}"

    async with websockets.connect(url) as ops:
        raw = await asyncio.wait_for(ops.recv(), timeout=15)
        env = Envelope.model_validate_json(raw)
        assert env.type == "telemetry"
        assert env.telemetry is not None
        assert -90 <= env.telemetry.lat <= 90
        assert env.telemetry.mode  # non-empty
```

- [ ] **Step 2: Run test to verify it is skipped (no SITL)**

Run: `python -m pytest drone/tests/test_e2e_sitl.py -v`
Expected: SKIPPED (1 skipped) — "set RUN_SITL_E2E=1 ..."

- [ ] **Step 3: Write `docs/DEPLOY_DRONE_OPS.md` with the run procedure**

````markdown
# Drone Remote Ops — Run & Deploy (Phase 1)

## Local end-to-end with ArduPilot SITL (no hardware)

1. **Install SITL** (once):
   ```bash
   pip install pymavlink mavproxy
   git clone https://github.com/ArduPilot/ardupilot --recursive
   cd ardupilot/ArduCopter && sim_vehicle.py -w   # build + init params
   ```
2. **Start SITL**, forwarding MAVLink to the agent's port:
   ```bash
   sim_vehicle.py -v ArduCopter --out=udp:127.0.0.1:14550 --console --map
   ```
3. **Start the relay**:
   ```bash
   DRONE_TOKENS="sitl-01:dtok" OPS_TOKEN="otok" \
     uvicorn drone.relay.server:app --host 0.0.0.0 --port 8800
   ```
4. **Start the agent**:
   ```bash
   DRONE_ID=sitl-01 DRONE_TOKEN=dtok \
     RELAY_WS_URL=ws://127.0.0.1:8800 \
     MAVLINK_URL=udpin:127.0.0.1:14550 TELEMETRY_HZ=5 \
     python -m drone.agent.main
   ```
5. **Fly it** in the SITL console: `mode guided`, `arm throttle`, `takeoff 40`.
6. **Run the e2e test**:
   ```bash
   RUN_SITL_E2E=1 RELAY_WS_URL=ws://127.0.0.1:8800 OPS_TOKEN=otok DRONE_ID=sitl-01 \
     python -m pytest drone/tests/test_e2e_sitl.py -v
   ```

## Production deploy

### Relay (Oracle A1 VM)
- `/etc/systemd/system/axalon-relay.service`:
  ```ini
  [Unit]
  Description=Axalon Drone Relay
  After=network-online.target
  [Service]
  Environment=DRONE_TOKENS=sitl-01:CHANGE_ME
  Environment=OPS_TOKEN=CHANGE_ME
  ExecStart=/usr/bin/uvicorn drone.relay.server:app --host 0.0.0.0 --port 8800
  WorkingDirectory=/opt/axalon
  Restart=always
  [Install]
  WantedBy=multi-user.target
  ```
- Front with Cloudflare for `wss://relay.axalonsystems.com`.
- Keep-alive cron to avoid Oracle Always-Free idle reclaim:
  `*/15 * * * * curl -s https://relay.axalonsystems.com/health >/dev/null`

### Agent (Jetson Orin Nano)
- `/etc/systemd/system/axalon-drone-agent.service` with `DRONE_ID`, `DRONE_TOKEN`,
  `RELAY_WS_URL=wss://relay.axalonsystems.com`, `MAVLINK_URL` pointing at the real
  Cube (e.g. `serial:/dev/ttyTHS1:921600`). `Restart=always`.
````

- [ ] **Step 4: Commit**

```bash
git add drone/tests/test_e2e_sitl.py docs/DEPLOY_DRONE_OPS.md
git commit -m "test(drone): opt-in SITL e2e + deploy runbook"
```

---

## Task 9: Frontend live-ops WS client + types

**Files:**
- Create: `website/nextjs/lib/liveOps.ts`
- Test: `website/nextjs/tests/unit/liveOps.test.ts`

- [ ] **Step 1: Write the failing test**

```ts
// website/nextjs/tests/unit/liveOps.test.ts
import { describe, it, expect } from "vitest";
import { parseTelemetryFrame, type Telemetry } from "@/lib/liveOps";

describe("parseTelemetryFrame", () => {
  it("extracts telemetry from a valid envelope", () => {
    const raw = JSON.stringify({
      type: "telemetry",
      telemetry: {
        drone_id: "sitl-01", ts: 1, seq: 3,
        lat: 28.4, lon: 77.1, alt_rel_m: 40, alt_amsl_m: 255,
        heading_deg: 90, groundspeed_ms: 5, battery_pct: 82,
        battery_voltage: 22.1, mode: "GUIDED", armed: true,
        gps_fix: 3, satellites: 14, roll_deg: 1, pitch_deg: -1,
        yaw_deg: 90, link_tier: "GREEN",
      },
    });
    const t = parseTelemetryFrame(raw) as Telemetry;
    expect(t.drone_id).toBe("sitl-01");
    expect(t.lat).toBeCloseTo(28.4);
    expect(t.mode).toBe("GUIDED");
  });

  it("returns null for a non-telemetry frame", () => {
    expect(parseTelemetryFrame(JSON.stringify({ type: "ack" }))).toBeNull();
  });

  it("returns null for malformed json", () => {
    expect(parseTelemetryFrame("not json")).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd website/nextjs && npx vitest run tests/unit/liveOps.test.ts`
Expected: FAIL — cannot resolve `@/lib/liveOps`

- [ ] **Step 3: Write minimal implementation**

```ts
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

export interface LiveOpsHandlers {
  onTelemetry: (t: Telemetry) => void;
  onStatus?: (s: "connecting" | "open" | "closed") => void;
}

/** Opens the ops WebSocket and pumps telemetry to the handler. Returns a
 *  disposer. Auto-reconnects with backoff. */
export function connectLiveOps(
  baseWsUrl: string,
  droneId: string,
  opsToken: string,
  handlers: LiveOpsHandlers
): () => void {
  let ws: WebSocket | null = null;
  let closed = false;
  let backoff = 1000;

  const open = () => {
    if (closed) return;
    handlers.onStatus?.("connecting");
    const url = `${baseWsUrl}/ws/ops/${droneId}?token=${encodeURIComponent(opsToken)}`;
    ws = new WebSocket(url);
    ws.onopen = () => {
      backoff = 1000;
      handlers.onStatus?.("open");
    };
    ws.onmessage = (ev) => {
      const t = parseTelemetryFrame(ev.data as string);
      if (t) handlers.onTelemetry(t);
    };
    ws.onclose = () => {
      handlers.onStatus?.("closed");
      if (!closed) setTimeout(open, (backoff = Math.min(backoff * 2, 15000)));
    };
    ws.onerror = () => ws?.close();
  };

  open();
  return () => {
    closed = true;
    ws?.close();
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd website/nextjs && npx vitest run tests/unit/liveOps.test.ts`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add website/nextjs/lib/liveOps.ts website/nextjs/tests/unit/liveOps.test.ts
git commit -m "feat(web): live-ops WS client + telemetry parsing"
```

---

## Task 10: Frontend Live Ops tab (map marker + HUD)

**Files:**
- Create: `website/nextjs/components/Platform/LiveOpsTab.tsx`
- Modify: `website/nextjs/app/platform/page.tsx` (add `'liveops'` tab)

No new unit test (presentational + live socket); validated visually against SITL.
Reuses the Leaflet setup already used by the mission planner — check
`components/Platform/PlanMap.tsx` for the existing dynamic-import (`ssr:false`) pattern and copy it.

- [ ] **Step 1: Read the existing map + tab patterns**

Read `website/nextjs/components/Platform/PlanMap.tsx` (Leaflet dynamic import, `ssr:false`)
and `website/nextjs/app/platform/page.tsx` (how tabs are registered/switched). Match those patterns exactly.

- [ ] **Step 2: Create `LiveOpsTab.tsx`**

```tsx
// website/nextjs/components/Platform/LiveOpsTab.tsx
"use client";

import { useEffect, useRef, useState } from "react";
import { connectLiveOps, type Telemetry } from "@/lib/liveOps";

const RELAY_WS = process.env.NEXT_PUBLIC_RELAY_WS_URL ?? "";
const OPS_TOKEN = process.env.NEXT_PUBLIC_OPS_TOKEN ?? "";

function Hud({ t, status }: { t: Telemetry | null; status: string }) {
  return (
    <div className="liveops-hud">
      <span>Link: {status}</span>
      {t && (
        <>
          <span>Mode: {t.mode}</span>
          <span>{t.armed ? "ARMED" : "DISARMED"}</span>
          <span>Alt: {t.alt_rel_m.toFixed(1)} m</span>
          <span>Spd: {t.groundspeed_ms.toFixed(1)} m/s</span>
          <span>Bat: {t.battery_pct.toFixed(0)}%</span>
          <span>Sats: {t.satellites}</span>
          <span>Tier: {t.link_tier}</span>
        </>
      )}
    </div>
  );
}

export default function LiveOpsTab({ droneId = "sitl-01" }: { droneId?: string }) {
  const [telem, setTelem] = useState<Telemetry | null>(null);
  const [status, setStatus] = useState("idle");

  useEffect(() => {
    if (!RELAY_WS) {
      setStatus("no relay configured");
      return;
    }
    const dispose = connectLiveOps(RELAY_WS, droneId, OPS_TOKEN, {
      onTelemetry: (t) => setTelem(t),
      onStatus: (s) => setStatus(s),
    });
    return dispose;
  }, [droneId]);

  return (
    <div className="liveops">
      <Hud t={telem} status={status} />
      {/* Map: reuse the mission-planner Leaflet wrapper. Render a marker at
          [telem.lat, telem.lon] rotated to telem.heading_deg, plus a breadcrumb
          polyline of recent positions. Follow PlanMap.tsx's dynamic-import shape. */}
      {telem && (
        <p className="liveops-pos">
          {telem.lat.toFixed(5)}, {telem.lon.toFixed(5)} @ {telem.heading_deg.toFixed(0)}°
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Register the tab in `app/platform/page.tsx`**

Add a `'liveops'` entry to the existing tab list/switch (matching how `'overview'`,
`'plan'`, etc. are wired) that renders `<LiveOpsTab />`. Use the same dynamic
`ssr:false` import wrapper the other map-bearing tabs use.

- [ ] **Step 4: Verify build**

Run: `cd website/nextjs && npm run build`
Expected: build succeeds, `/platform` compiles with the new tab.

- [ ] **Step 5: Manual verification against SITL**

With SITL + relay + agent running (Task 8) and `NEXT_PUBLIC_RELAY_WS_URL` /
`NEXT_PUBLIC_OPS_TOKEN` set in `website/nextjs/.env.local`, run `npm run dev`,
open `/platform` → Live Ops, and confirm the HUD updates and position moves as
SITL flies.

- [ ] **Step 6: Commit**

```bash
git add website/nextjs/components/Platform/LiveOpsTab.tsx website/nextjs/app/platform/page.tsx
git commit -m "feat(web): Live Ops tab with telemetry HUD + map marker"
```

---

## Self-Review Notes (resolved)

- **Spec coverage (Phase 1):** relay (Tasks 2–4), agent (Tasks 5–7), telemetry on the
  map in the browser (Tasks 9–10), SITL-based testing (Task 8), shared schema (Task 1).
  Video/commands/manual are explicitly out of Phase 1 per the spec. ✔
- **Types consistent:** `Telemetry`/`Envelope` field names match across Python
  (`drone/common/telemetry.py`) and TS (`lib/liveOps.ts`); relay paths
  `/ws/drone/{id}` and `/ws/ops/{id}` match agent `ops_url()`, the server, the
  frontend client, and the e2e test. ✔
- **No placeholders:** every code step has full code; the only deferred fill-in is the
  Leaflet marker rendering in Task 10, intentionally delegated to the existing
  `PlanMap.tsx` pattern the engineer is told to read and copy. ✔
- **Auth note:** Phase 1 ops auth is a shared `OPS_TOKEN`; the spec calls for replacing
  it with the platform session/JWT — that swap is scheduled with command authz in
  Phase 2 (no point hardening read-only telemetry before commands exist). ✔
```
