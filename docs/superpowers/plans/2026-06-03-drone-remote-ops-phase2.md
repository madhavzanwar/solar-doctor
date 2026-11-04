# Drone Remote Ops — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the read-only telemetry pipe from Phase 1 into a controllable one — the browser can send high-level flight commands (arm, takeoff, RTL, land, pause, resume, goto, set-mode, upload-mission) that reach ArduPilot, behind a single-operator control lock and a link-tier safety gate, all proven against SITL.

**Architecture:** Commands ride the same WebSocket as telemetry using the existing `Envelope` (new `command`/`ack`/`control` variants). The **relay** is the authority: it enforces the control lock and the link-tier policy before forwarding any command to the drone. The **agent** independently re-validates every command against an allow-list + altitude bounds before touching MAVLink (defense in depth — never blind-forward). A deadman on the agent triggers ArduPilot RTL if the relay link dies.

**Tech Stack:** Builds on Phase 1 — Python `pymavlink`/`fastapi`/`pydantic`, `pytest`; frontend Next.js + `vitest`. No new dependencies.

**Spec:** `docs/superpowers/specs/2026-06-03-drone-remote-operations-design.md` (Phase 2: commands, control-lock, safety tiers).
**Depends on:** `docs/superpowers/plans/2026-06-03-drone-remote-ops-phase1.md` (must be implemented first).

---

## Conventions

- Same as Phase 1: Python under `drone/`, tests via `python -m pytest drone/tests -v`; frontend via `cd website/nextjs && npx vitest run <file>`.
- Commit after every green step.
- **Operator identity:** the browser generates a random `operator_id` per session and passes it as a query param on the ops socket; the relay uses it for the control lock.

---

## Task 1: Command / Ack / Control schema + extend Envelope

**Files:**
- Create: `drone/common/commands.py`
- Modify: `drone/common/telemetry.py` (extend `Envelope`)
- Test: `drone/tests/test_commands_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_commands_schema.py
import pytest
from pydantic import ValidationError
from drone.common.commands import (
    Command, Ack, ControlMsg, CommandType, ControlAction,
)
from drone.common.telemetry import Envelope


def test_command_roundtrips():
    c = Command(cmd_id="abc", type=CommandType.TAKEOFF, params={"alt": 40.0})
    again = Command.model_validate_json(c.model_dump_json())
    assert again == c
    assert again.type is CommandType.TAKEOFF
    assert again.params["alt"] == 40.0


def test_command_defaults_empty_params():
    c = Command(cmd_id="x", type=CommandType.RTL)
    assert c.params == {}


def test_unknown_command_type_rejected():
    with pytest.raises(ValidationError):
        Command(cmd_id="x", type="FLIP")


def test_envelope_carries_command_and_ack_and_control():
    env = Envelope(
        type="command",
        command=Command(cmd_id="1", type=CommandType.ARM),
    )
    rt = Envelope.model_validate_json(env.model_dump_json())
    assert rt.command is not None and rt.command.type is CommandType.ARM

    ack_env = Envelope(type="ack", ack=Ack(cmd_id="1", success=True, message="ok"))
    assert Envelope.model_validate_json(ack_env.model_dump_json()).ack.success is True

    ctl_env = Envelope(
        type="control",
        control=ControlMsg(action=ControlAction.ACQUIRE, operator_id="op-7"),
    )
    rt2 = Envelope.model_validate_json(ctl_env.model_dump_json())
    assert rt2.control.action is ControlAction.ACQUIRE
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_commands_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.common.commands'`

- [ ] **Step 3: Write `drone/common/commands.py`**

```python
# drone/common/commands.py
"""Command, acknowledgement, and control-lock message schemas.

These ride the same WebSocket as telemetry via the shared Envelope. Keeping them
in their own module avoids an import cycle: telemetry.Envelope imports these, and
these import nothing from telemetry.
"""
from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class CommandType(str, Enum):
    ARM = "ARM"
    DISARM = "DISARM"
    TAKEOFF = "TAKEOFF"
    RTL = "RTL"
    LAND = "LAND"
    PAUSE = "PAUSE"            # hold position (BRAKE)
    RESUME = "RESUME"          # continue AUTO mission
    GOTO = "GOTO"             # fly to a lat/lon/alt (guided)
    SET_MODE = "SET_MODE"
    UPLOAD_MISSION = "UPLOAD_MISSION"


class Command(BaseModel):
    cmd_id: str
    type: CommandType
    params: dict = Field(default_factory=dict)


class Ack(BaseModel):
    cmd_id: str
    success: bool
    message: str = ""


class ControlAction(str, Enum):
    ACQUIRE = "acquire"
    RELEASE = "release"
    STATUS = "status"


class ControlMsg(BaseModel):
    action: ControlAction
    operator_id: str = ""
    granted: bool | None = None   # set by relay in the reply
    holder: str | None = None     # current lock holder, set by relay in the reply
```

- [ ] **Step 4: Extend `Envelope` in `drone/common/telemetry.py`**

Replace the existing `Envelope` class with:

```python
from drone.common.commands import Ack, Command, ControlMsg


class Envelope(BaseModel):
    """Top-level frame on the wire. `type` discriminates message kinds:
    'telemetry' | 'command' | 'ack' | 'control' | 'heartbeat'."""
    type: str
    telemetry: Telemetry | None = None
    command: Command | None = None
    ack: Ack | None = None
    control: ControlMsg | None = None
    ts: float | None = None   # used by heartbeat frames for RTT measurement
```

(Add the import near the top of the file, after the existing imports.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest drone/tests/test_commands_schema.py drone/tests/test_telemetry_schema.py -v`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add drone/common/commands.py drone/common/telemetry.py drone/tests/test_commands_schema.py
git commit -m "feat(drone): command/ack/control schema + extended envelope"
```

---

## Task 2: Relay control lock

**Files:**
- Create: `drone/relay/control_lock.py`
- Test: `drone/tests/test_control_lock.py`

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_control_lock.py
from drone.relay.control_lock import ControlLock


def test_first_operator_acquires():
    lock = ControlLock()
    assert lock.acquire("d1", "op-a") is True
    assert lock.holder("d1") == "op-a"


def test_second_operator_is_denied_while_held():
    lock = ControlLock()
    lock.acquire("d1", "op-a")
    assert lock.acquire("d1", "op-b") is False
    assert lock.holder("d1") == "op-a"


def test_reacquire_by_same_operator_is_idempotent():
    lock = ControlLock()
    lock.acquire("d1", "op-a")
    assert lock.acquire("d1", "op-a") is True


def test_release_frees_lock_only_for_holder():
    lock = ControlLock()
    lock.acquire("d1", "op-a")
    assert lock.release("d1", "op-b") is False  # not the holder
    assert lock.release("d1", "op-a") is True
    assert lock.holder("d1") is None
    assert lock.acquire("d1", "op-b") is True   # now free


def test_holds_predicate():
    lock = ControlLock()
    lock.acquire("d1", "op-a")
    assert lock.holds("d1", "op-a") is True
    assert lock.holds("d1", "op-b") is False
    assert lock.holds("d2", "op-a") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_control_lock.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.relay.control_lock'`

- [ ] **Step 3: Write minimal implementation**

```python
# drone/relay/control_lock.py
"""Single-operator control lock, keyed by drone_id.

Exactly one operator may hold a given drone's lock at a time. Acquiring is
idempotent for the current holder. Only flight commands from the lock holder are
forwarded by the relay; everyone else is view-only.
"""
from __future__ import annotations


class ControlLock:
    def __init__(self) -> None:
        self._holder: dict[str, str] = {}

    def acquire(self, drone_id: str, operator_id: str) -> bool:
        current = self._holder.get(drone_id)
        if current is None or current == operator_id:
            self._holder[drone_id] = operator_id
            return True
        return False

    def release(self, drone_id: str, operator_id: str) -> bool:
        if self._holder.get(drone_id) == operator_id:
            del self._holder[drone_id]
            return True
        return False

    def holder(self, drone_id: str) -> str | None:
        return self._holder.get(drone_id)

    def holds(self, drone_id: str, operator_id: str) -> bool:
        return self._holder.get(drone_id) == operator_id
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest drone/tests/test_control_lock.py -v`
Expected: PASS (5 passed)

- [ ] **Step 5: Commit**

```bash
git add drone/relay/control_lock.py drone/tests/test_control_lock.py
git commit -m "feat(relay): single-operator control lock"
```

---

## Task 3: Relay tier policy + command authorization

**Files:**
- Create: `drone/relay/tier_policy.py`
- Test: `drone/tests/test_tier_policy.py`

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_tier_policy.py
from drone.common.commands import CommandType
from drone.common.telemetry import LinkTier
from drone.relay.tier_policy import is_allowed, authorize_command


def test_amber_allows_mission_control_commands():
    assert is_allowed(LinkTier.AMBER, CommandType.TAKEOFF)
    assert is_allowed(LinkTier.AMBER, CommandType.RTL)
    assert is_allowed(LinkTier.AMBER, CommandType.UPLOAD_MISSION)


def test_green_allows_everything_amber_allows():
    for ct in CommandType:
        assert is_allowed(LinkTier.GREEN, ct)


def test_red_blocks_all_commands():
    for ct in CommandType:
        assert not is_allowed(LinkTier.RED, ct)


def test_authorize_requires_lock():
    ok, reason = authorize_command(
        holds_lock=False, tier=LinkTier.AMBER, cmd_type=CommandType.ARM
    )
    assert ok is False
    assert "lock" in reason.lower()


def test_authorize_blocks_command_on_red_tier():
    ok, reason = authorize_command(
        holds_lock=True, tier=LinkTier.RED, cmd_type=CommandType.TAKEOFF
    )
    assert ok is False
    assert "tier" in reason.lower()


def test_authorize_allows_when_lock_held_and_tier_permits():
    ok, reason = authorize_command(
        holds_lock=True, tier=LinkTier.AMBER, cmd_type=CommandType.GOTO
    )
    assert ok is True
    assert reason == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_tier_policy.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.relay.tier_policy'`

- [ ] **Step 3: Write minimal implementation**

```python
# drone/relay/tier_policy.py
"""Link-tier command policy + authorization, enforced authoritatively on the relay.

Phase 2 commands are all "mission control" class: allowed on GREEN and AMBER,
blocked on RED (degraded link). Manual stick commands arrive in Phase 5 and will
be GREEN-only — this table is where that distinction will live.
"""
from __future__ import annotations

from drone.common.commands import CommandType
from drone.common.telemetry import LinkTier

# Mission-control command set (everything in Phase 2).
_MISSION_CONTROL: set[CommandType] = set(CommandType)

_ALLOWED: dict[LinkTier, set[CommandType]] = {
    LinkTier.GREEN: set(_MISSION_CONTROL),   # + manual in Phase 5
    LinkTier.AMBER: set(_MISSION_CONTROL),
    LinkTier.RED: set(),                       # degraded: block all
}


def is_allowed(tier: LinkTier, cmd_type: CommandType) -> bool:
    return cmd_type in _ALLOWED[tier]


def authorize_command(
    *, holds_lock: bool, tier: LinkTier, cmd_type: CommandType
) -> tuple[bool, str]:
    if not holds_lock:
        return False, "you do not hold the control lock"
    if not is_allowed(tier, cmd_type):
        return False, f"{cmd_type.value} not allowed at link tier {tier.value}"
    return True, ""
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest drone/tests/test_tier_policy.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add drone/relay/tier_policy.py drone/tests/test_tier_policy.py
git commit -m "feat(relay): link-tier command policy + authorization"
```

---

## Task 4: Extend RelayManager (drone send + tier tracking)

**Files:**
- Modify: `drone/relay/manager.py`
- Test: `drone/tests/test_relay_manager_phase2.py`

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_relay_manager_phase2.py
import pytest
from drone.common.telemetry import LinkTier
from drone.relay.manager import RelayManager


class FakeSink:
    def __init__(self):
        self.sent: list[str] = []

    async def send_text(self, data: str):
        self.sent.append(data)


async def test_send_to_drone_delivers_to_registered_drone():
    mgr = RelayManager()
    drone = FakeSink()
    mgr.register_drone("d1", drone)
    ok = await mgr.send_to_drone("d1", "cmd-frame")
    assert ok is True
    assert drone.sent == ["cmd-frame"]


async def test_send_to_offline_drone_returns_false():
    mgr = RelayManager()
    assert await mgr.send_to_drone("ghost", "x") is False


def test_tier_defaults_to_red_until_set():
    mgr = RelayManager()
    assert mgr.tier_for("d1") is LinkTier.RED


def test_set_and_read_tier():
    mgr = RelayManager()
    mgr.set_tier("d1", LinkTier.AMBER)
    assert mgr.tier_for("d1") is LinkTier.AMBER


async def test_fan_to_operators_sends_to_all():
    mgr = RelayManager()
    a, b = FakeSink(), FakeSink()
    mgr.add_operator("d1", a)
    mgr.add_operator("d1", b)
    await mgr.fan_to_operators("d1", "ack-frame")
    assert a.sent == ["ack-frame"] and b.sent == ["ack-frame"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_relay_manager_phase2.py -v`
Expected: FAIL — `AttributeError: 'RelayManager' object has no attribute 'send_to_drone'`

- [ ] **Step 3: Extend the implementation**

In `drone/relay/manager.py`, add the import at the top:

```python
from drone.common.telemetry import LinkTier
```

In `RelayManager.__init__`, add:

```python
        self._tier: dict[str, LinkTier] = {}
```

Add these methods to the class:

```python
    # --- link tier (authoritative, updated from telemetry) ---
    def set_tier(self, drone_id: str, tier: LinkTier) -> None:
        self._tier[drone_id] = tier

    def tier_for(self, drone_id: str) -> LinkTier:
        return self._tier.get(drone_id, LinkTier.RED)  # unknown link = safe default

    # --- sending ---
    async def send_to_drone(self, drone_id: str, raw: str) -> bool:
        sink = self._drones.get(drone_id)
        if sink is None:
            return False
        await sink.send_text(raw)
        return True

    async def fan_to_operators(self, drone_id: str, raw: str) -> None:
        dead = []
        for sink in list(self.operators_for(drone_id)):
            try:
                await sink.send_text(raw)
            except Exception:
                dead.append(sink)
        for sink in dead:
            self.remove_operator(drone_id, sink)
```

Then refactor `broadcast_telemetry` to reuse `fan_to_operators`:

```python
    async def broadcast_telemetry(self, drone_id: str, raw: str) -> None:
        await self.fan_to_operators(drone_id, raw)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest drone/tests/test_relay_manager_phase2.py drone/tests/test_relay_manager.py -v`
Expected: PASS (all — Phase 1 manager tests still green)

- [ ] **Step 5: Commit**

```bash
git add drone/relay/manager.py drone/tests/test_relay_manager_phase2.py
git commit -m "feat(relay): manager drone-send + tier tracking + ack fan-out"
```

---

## Task 5: Relay server — command routing, control lock, tier enforcement, heartbeat echo

**Files:**
- Modify: `drone/relay/server.py`
- Test: `drone/tests/test_relay_server_phase2.py`

The ops socket now reads inbound frames (control + command). Operator identity is
a query param. The drone socket now handles `ack` (fan to operators) and
`heartbeat` (echo back to the drone for RTT), and records the link tier from
telemetry.

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_relay_server_phase2.py
import json
import pytest
from fastapi.testclient import TestClient
from drone.relay.server import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DRONE_TOKENS", "sitl-01:dtok")
    monkeypatch.setenv("OPS_TOKEN", "otok")
    return TestClient(create_app())


def _telemetry_frame(tier="AMBER"):
    return json.dumps({
        "type": "telemetry",
        "telemetry": {
            "drone_id": "sitl-01", "ts": 1, "seq": 0,
            "lat": 28.4, "lon": 77.1, "alt_rel_m": 40, "alt_amsl_m": 255,
            "heading_deg": 90, "groundspeed_ms": 5, "battery_pct": 80,
            "battery_voltage": 22.0, "mode": "GUIDED", "armed": False,
            "gps_fix": 3, "satellites": 14, "roll_deg": 0, "pitch_deg": 0,
            "yaw_deg": 90, "link_tier": tier,
        },
    })


def test_operator_acquires_control(client):
    with client.websocket_connect("/ws/ops/sitl-01?token=otok&operator=op-a") as ops:
        ops.send_text(json.dumps({"type": "control",
                                  "control": {"action": "acquire", "operator_id": "op-a"}}))
        reply = json.loads(ops.receive_text())
        assert reply["type"] == "control"
        assert reply["control"]["granted"] is True
        assert reply["control"]["holder"] == "op-a"


def test_command_forwarded_to_drone_when_lock_held_and_tier_ok(client):
    with client.websocket_connect("/ws/drone/sitl-01?token=dtok") as drone:
        # establish tier via a telemetry frame
        drone.send_text(_telemetry_frame("AMBER"))
        with client.websocket_connect("/ws/ops/sitl-01?token=otok&operator=op-a") as ops:
            ops.send_text(json.dumps({"type": "control",
                                      "control": {"action": "acquire", "operator_id": "op-a"}}))
            ops.receive_text()  # control grant
            ops.send_text(json.dumps({"type": "command",
                                      "command": {"cmd_id": "c1", "type": "ARM"}}))
            fwd = json.loads(drone.receive_text())
            assert fwd["type"] == "command"
            assert fwd["command"]["type"] == "ARM"


def test_command_rejected_without_lock(client):
    with client.websocket_connect("/ws/drone/sitl-01?token=dtok") as drone:
        drone.send_text(_telemetry_frame("AMBER"))
        with client.websocket_connect("/ws/ops/sitl-01?token=otok&operator=op-a") as ops:
            ops.send_text(json.dumps({"type": "command",
                                      "command": {"cmd_id": "c2", "type": "ARM"}}))
            reply = json.loads(ops.receive_text())
            assert reply["type"] == "ack"
            assert reply["ack"]["success"] is False
            assert "lock" in reply["ack"]["message"].lower()


def test_command_rejected_on_red_tier(client):
    with client.websocket_connect("/ws/drone/sitl-01?token=dtok") as drone:
        drone.send_text(_telemetry_frame("RED"))
        with client.websocket_connect("/ws/ops/sitl-01?token=otok&operator=op-a") as ops:
            ops.send_text(json.dumps({"type": "control",
                                      "control": {"action": "acquire", "operator_id": "op-a"}}))
            ops.receive_text()
            ops.send_text(json.dumps({"type": "command",
                                      "command": {"cmd_id": "c3", "type": "TAKEOFF",
                                                  "params": {"alt": 40}}}))
            reply = json.loads(ops.receive_text())
            assert reply["ack"]["success"] is False
            assert "tier" in reply["ack"]["message"].lower()


def test_ack_from_drone_fans_to_operator(client):
    with client.websocket_connect("/ws/drone/sitl-01?token=dtok") as drone:
        with client.websocket_connect("/ws/ops/sitl-01?token=otok&operator=op-a") as ops:
            drone.send_text(json.dumps({"type": "ack",
                                        "ack": {"cmd_id": "c1", "success": True, "message": "armed"}}))
            reply = json.loads(ops.receive_text())
            assert reply["type"] == "ack" and reply["ack"]["cmd_id"] == "c1"


def test_heartbeat_echoed_back_to_drone(client):
    with client.websocket_connect("/ws/drone/sitl-01?token=dtok") as drone:
        drone.send_text(json.dumps({"type": "heartbeat", "ts": 123.0}))
        reply = json.loads(drone.receive_text())
        assert reply["type"] == "heartbeat" and reply["ts"] == 123.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_relay_server_phase2.py -v`
Expected: FAIL — control/command frames are not handled yet (assorted assertion / timeout failures)

- [ ] **Step 3: Rewrite `drone/relay/server.py`**

```python
# drone/relay/server.py
"""Relay FastAPI app (Phase 2).

- /ws/drone/{drone_id}?token=... : agent pushes telemetry/ack/heartbeat; receives commands.
- /ws/ops/{drone_id}?token=...&operator=... : browser sends control/command; receives telemetry/ack/control.

The relay is the command authority: it enforces the control lock and the
link-tier policy before forwarding any command to the drone.
"""
from __future__ import annotations

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status

from drone.common.commands import Ack, ControlAction, ControlMsg
from drone.common.telemetry import Envelope
from drone.relay.auth import AuthError, verify_drone_token, verify_operator_token
from drone.relay.control_lock import ControlLock
from drone.relay.manager import RelayManager
from drone.relay.tier_policy import authorize_command


def create_app() -> FastAPI:
    app = FastAPI(title="Axalon Drone Relay")
    mgr = RelayManager()
    lock = ControlLock()
    app.state.manager = mgr
    app.state.lock = lock

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
                env = Envelope.model_validate_json(raw)
                if env.type == "telemetry" and env.telemetry is not None:
                    mgr.set_tier(drone_id, env.telemetry.link_tier)
                    await mgr.fan_to_operators(drone_id, raw)
                elif env.type == "ack":
                    await mgr.fan_to_operators(drone_id, raw)
                elif env.type == "heartbeat":
                    await ws.send_text(raw)  # echo for RTT measurement
        except WebSocketDisconnect:
            pass
        finally:
            mgr.unregister_drone(drone_id)

    @app.websocket("/ws/ops/{drone_id}")
    async def ops_ws(ws: WebSocket, drone_id: str, token: str = "", operator: str = ""):
        try:
            verify_operator_token(token)
        except AuthError:
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        await ws.accept()
        mgr.add_operator(drone_id, ws)
        try:
            while True:
                raw = await ws.receive_text()
                env = Envelope.model_validate_json(raw)
                if env.type == "control" and env.control is not None:
                    await _handle_control(ws, lock, drone_id, env.control)
                elif env.type == "command" and env.command is not None:
                    await _handle_command(ws, mgr, lock, drone_id, operator, raw, env)
        except WebSocketDisconnect:
            pass
        finally:
            mgr.remove_operator(drone_id, ws)

    async def _handle_control(ws, lock, drone_id, ctl: ControlMsg):
        if ctl.action is ControlAction.ACQUIRE:
            granted = lock.acquire(drone_id, ctl.operator_id)
        elif ctl.action is ControlAction.RELEASE:
            granted = lock.release(drone_id, ctl.operator_id)
        else:  # STATUS
            granted = lock.holds(drone_id, ctl.operator_id)
        reply = Envelope(type="control", control=ControlMsg(
            action=ctl.action, operator_id=ctl.operator_id,
            granted=granted, holder=lock.holder(drone_id),
        ))
        await ws.send_text(reply.model_dump_json())

    async def _handle_command(ws, mgr, lock, drone_id, operator, raw, env):
        cmd = env.command
        ok, reason = authorize_command(
            holds_lock=lock.holds(drone_id, operator),
            tier=mgr.tier_for(drone_id),
            cmd_type=cmd.type,
        )
        if not ok:
            nack = Envelope(type="ack", ack=Ack(cmd_id=cmd.cmd_id, success=False, message=reason))
            await ws.send_text(nack.model_dump_json())
            return
        delivered = await mgr.send_to_drone(drone_id, raw)
        if not delivered:
            nack = Envelope(type="ack", ack=Ack(
                cmd_id=cmd.cmd_id, success=False, message="drone offline"))
            await ws.send_text(nack.model_dump_json())

    return app


app = create_app()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest drone/tests/test_relay_server_phase2.py drone/tests/test_relay_server.py -v`
Expected: PASS (all — Phase 1 server tests still green)

- [ ] **Step 5: Commit**

```bash
git add drone/relay/server.py drone/tests/test_relay_server_phase2.py
git commit -m "feat(relay): command routing, control lock, tier enforcement, heartbeat echo"
```

---

## Task 6: Agent commander (MAVLink command interface)

**Files:**
- Create: `drone/agent/commander.py`
- Test: `drone/tests/test_commander.py`

`MavCommander` is the protocol the executor calls. `PymavlinkCommander` is the
real implementation (thin glue over `mavutil`, covered by the SITL e2e in Task 9).
The unit test here pins the protocol surface with a fake.

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_commander.py
from drone.agent.commander import MavCommander


def test_protocol_surface_is_callable_via_duck_typing():
    # A fake satisfying the protocol can be used wherever MavCommander is expected.
    class Fake:
        def __init__(self):
            self.calls = []

        def arm(self): self.calls.append(("arm",))
        def disarm(self): self.calls.append(("disarm",))
        def set_mode(self, mode): self.calls.append(("set_mode", mode))
        def takeoff(self, alt_m): self.calls.append(("takeoff", alt_m))
        def rtl(self): self.calls.append(("rtl",))
        def land(self): self.calls.append(("land",))
        def goto(self, lat, lon, alt_m): self.calls.append(("goto", lat, lon, alt_m))
        def upload_mission(self, waypoints): self.calls.append(("upload_mission", len(waypoints)))

    f: MavCommander = Fake()
    f.arm()
    f.takeoff(40.0)
    assert f.calls == [("arm",), ("takeoff", 40.0)]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_commander.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.agent.commander'`

- [ ] **Step 3: Write minimal implementation**

```python
# drone/agent/commander.py
"""MAVLink command surface used by the command executor.

`MavCommander` is the contract; `PymavlinkCommander` is the real implementation
over an established mavutil connection. The executor depends on the protocol, so
it can be unit-tested with a fake and never needs a live autopilot.
"""
from __future__ import annotations

from typing import Protocol

from pymavlink import mavutil


class MavCommander(Protocol):
    def arm(self) -> None: ...
    def disarm(self) -> None: ...
    def set_mode(self, mode: str) -> None: ...
    def takeoff(self, alt_m: float) -> None: ...
    def rtl(self) -> None: ...
    def land(self) -> None: ...
    def goto(self, lat: float, lon: float, alt_m: float) -> None: ...
    def upload_mission(self, waypoints: list[dict]) -> None: ...


class PymavlinkCommander:
    """Real implementation. `conn` is a connected mavutil.mavlink_connection."""

    def __init__(self, conn) -> None:
        self._c = conn

    def _arm_disarm(self, value: int) -> None:
        self._c.mav.command_long_send(
            self._c.target_system, self._c.target_component,
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0,
            value, 0, 0, 0, 0, 0, 0)

    def arm(self) -> None:
        self._arm_disarm(1)

    def disarm(self) -> None:
        self._arm_disarm(0)

    def set_mode(self, mode: str) -> None:
        mode_id = self._c.mode_mapping()[mode]
        self._c.mav.set_mode_send(
            self._c.target_system,
            mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, mode_id)

    def takeoff(self, alt_m: float) -> None:
        self.set_mode("GUIDED")
        self.arm()
        self._c.mav.command_long_send(
            self._c.target_system, self._c.target_component,
            mavutil.mavlink.MAV_CMD_NAV_TAKEOFF, 0,
            0, 0, 0, 0, 0, 0, alt_m)

    def rtl(self) -> None:
        self.set_mode("RTL")

    def land(self) -> None:
        self.set_mode("LAND")

    def goto(self, lat: float, lon: float, alt_m: float) -> None:
        self.set_mode("GUIDED")
        self._c.mav.set_position_target_global_int_send(
            0, self._c.target_system, self._c.target_component,
            mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
            0b0000111111111000,
            int(lat * 1e7), int(lon * 1e7), alt_m,
            0, 0, 0, 0, 0, 0, 0, 0)

    def upload_mission(self, waypoints: list[dict]) -> None:
        """waypoints: list of {seq, lat, lon, alt_m}. Standard MISSION_COUNT +
        MISSION_ITEM_INT upload handshake."""
        n = len(waypoints)
        self._c.mav.mission_count_send(
            self._c.target_system, self._c.target_component, n)
        for wp in waypoints:
            self._c.mav.mission_item_int_send(
                self._c.target_system, self._c.target_component,
                wp["seq"],
                mavutil.mavlink.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT,
                mavutil.mavlink.MAV_CMD_NAV_WAYPOINT,
                0, 1, 0, 0, 0, 0,
                int(wp["lat"] * 1e7), int(wp["lon"] * 1e7), wp["alt_m"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest drone/tests/test_commander.py -v`
Expected: PASS (1 passed)

- [ ] **Step 5: Commit**

```bash
git add drone/agent/commander.py drone/tests/test_commander.py
git commit -m "feat(agent): MAVLink commander protocol + pymavlink impl"
```

---

## Task 7: Agent command executor (validate + dispatch)

**Files:**
- Create: `drone/agent/command_executor.py`
- Test: `drone/tests/test_command_executor.py`

Defense in depth: even though the relay gates commands, the agent re-validates
every command against an allow-list + altitude bounds before touching MAVLink.

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_command_executor.py
import pytest
from drone.common.commands import Command, CommandType
from drone.agent.command_executor import CommandExecutor


class FakeCommander:
    def __init__(self):
        self.calls = []

    def arm(self): self.calls.append(("arm",))
    def disarm(self): self.calls.append(("disarm",))
    def set_mode(self, mode): self.calls.append(("set_mode", mode))
    def takeoff(self, alt_m): self.calls.append(("takeoff", alt_m))
    def rtl(self): self.calls.append(("rtl",))
    def land(self): self.calls.append(("land",))
    def goto(self, lat, lon, alt_m): self.calls.append(("goto", lat, lon, alt_m))
    def upload_mission(self, wps): self.calls.append(("upload_mission", len(wps)))


def _exec():
    return CommandExecutor(FakeCommander(), min_alt_m=5.0, max_alt_m=120.0)


def test_arm_dispatches_and_acks_success():
    ex = _exec()
    ack = ex.execute(Command(cmd_id="1", type=CommandType.ARM))
    assert ack.success is True
    assert ("arm",) in ex.commander.calls


def test_takeoff_validates_altitude_bounds():
    ex = _exec()
    ack = ex.execute(Command(cmd_id="2", type=CommandType.TAKEOFF, params={"alt": 500}))
    assert ack.success is False
    assert "altitude" in ack.message.lower()
    assert ex.commander.calls == []  # never dispatched


def test_takeoff_within_bounds_dispatches():
    ex = _exec()
    ack = ex.execute(Command(cmd_id="3", type=CommandType.TAKEOFF, params={"alt": 40}))
    assert ack.success is True
    assert ("takeoff", 40.0) in ex.commander.calls


def test_pause_and_resume_map_to_modes():
    ex = _exec()
    ex.execute(Command(cmd_id="4", type=CommandType.PAUSE))
    ex.execute(Command(cmd_id="5", type=CommandType.RESUME))
    assert ("set_mode", "BRAKE") in ex.commander.calls
    assert ("set_mode", "AUTO") in ex.commander.calls


def test_goto_validates_lat_lon_and_alt():
    ex = _exec()
    bad = ex.execute(Command(cmd_id="6", type=CommandType.GOTO,
                             params={"lat": 200, "lon": 0, "alt": 40}))
    assert bad.success is False
    good = ex.execute(Command(cmd_id="7", type=CommandType.GOTO,
                              params={"lat": 28.4, "lon": 77.1, "alt": 40}))
    assert good.success is True
    assert ("goto", 28.4, 77.1, 40.0) in ex.commander.calls


def test_missing_required_param_is_a_clean_nack():
    ex = _exec()
    ack = ex.execute(Command(cmd_id="8", type=CommandType.TAKEOFF, params={}))
    assert ack.success is False
    assert ex.commander.calls == []


def test_commander_exception_becomes_failed_ack():
    class Boom(FakeCommander):
        def rtl(self): raise RuntimeError("link lost")
    ex = CommandExecutor(Boom(), min_alt_m=5.0, max_alt_m=120.0)
    ack = ex.execute(Command(cmd_id="9", type=CommandType.RTL))
    assert ack.success is False
    assert "link lost" in ack.message
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_command_executor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.agent.command_executor'`

- [ ] **Step 3: Write minimal implementation**

```python
# drone/agent/command_executor.py
"""Validate and dispatch commands to the MAVLink commander.

Every command is re-checked here (allow-list + altitude/coordinate bounds) even
though the relay already gated it — the agent never trusts an upstream gate. A
dispatch failure becomes a failed Ack instead of crashing the agent.
"""
from __future__ import annotations

from drone.agent.commander import MavCommander
from drone.common.commands import Ack, Command, CommandType


class CommandExecutor:
    def __init__(self, commander: MavCommander, min_alt_m: float, max_alt_m: float) -> None:
        self.commander = commander
        self.min_alt_m = min_alt_m
        self.max_alt_m = max_alt_m

    def _check_alt(self, alt) -> float:
        if alt is None:
            raise ValueError("missing required param: alt")
        alt = float(alt)
        if not (self.min_alt_m <= alt <= self.max_alt_m):
            raise ValueError(
                f"altitude {alt} outside bounds [{self.min_alt_m}, {self.max_alt_m}]")
        return alt

    def execute(self, cmd: Command) -> Ack:
        try:
            self._dispatch(cmd)
            return Ack(cmd_id=cmd.cmd_id, success=True, message="ok")
        except Exception as e:
            return Ack(cmd_id=cmd.cmd_id, success=False, message=str(e))

    def _dispatch(self, cmd: Command) -> None:
        p = cmd.params
        t = cmd.type
        if t is CommandType.ARM:
            self.commander.arm()
        elif t is CommandType.DISARM:
            self.commander.disarm()
        elif t is CommandType.TAKEOFF:
            self.commander.takeoff(self._check_alt(p.get("alt")))
        elif t is CommandType.RTL:
            self.commander.rtl()
        elif t is CommandType.LAND:
            self.commander.land()
        elif t is CommandType.PAUSE:
            self.commander.set_mode("BRAKE")
        elif t is CommandType.RESUME:
            self.commander.set_mode("AUTO")
        elif t is CommandType.SET_MODE:
            mode = p.get("mode")
            if not mode:
                raise ValueError("missing required param: mode")
            self.commander.set_mode(str(mode))
        elif t is CommandType.GOTO:
            lat, lon = p.get("lat"), p.get("lon")
            if lat is None or lon is None:
                raise ValueError("missing required params: lat/lon")
            lat, lon = float(lat), float(lon)
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                raise ValueError("lat/lon out of range")
            self.commander.goto(lat, lon, self._check_alt(p.get("alt")))
        elif t is CommandType.UPLOAD_MISSION:
            wps = p.get("waypoints")
            if not isinstance(wps, list) or not wps:
                raise ValueError("missing required param: waypoints")
            self.commander.upload_mission(wps)
        else:  # pragma: no cover - enum is exhaustive
            raise ValueError(f"unsupported command: {t}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest drone/tests/test_command_executor.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add drone/agent/command_executor.py drone/tests/test_command_executor.py
git commit -m "feat(agent): command executor with allow-list + bounds validation"
```

---

## Task 8: Agent safety — deadman + link tier from RTT

**Files:**
- Create: `drone/agent/safety.py`
- Test: `drone/tests/test_safety.py`

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_safety.py
from drone.common.telemetry import LinkTier
from drone.agent.safety import Deadman, tier_from_rtt


def test_tier_green_under_50ms():
    assert tier_from_rtt(0.02) is LinkTier.GREEN


def test_tier_amber_under_300ms():
    assert tier_from_rtt(0.20) is LinkTier.AMBER


def test_tier_red_above_300ms():
    assert tier_from_rtt(0.5) is LinkTier.RED


def test_tier_red_when_rtt_unknown():
    assert tier_from_rtt(None) is LinkTier.RED


def test_deadman_not_expired_after_recent_beat():
    dm = Deadman(timeout_s=3.0)
    dm.beat(now=100.0)
    assert dm.expired(now=102.0) is False


def test_deadman_expires_after_timeout():
    dm = Deadman(timeout_s=3.0)
    dm.beat(now=100.0)
    assert dm.expired(now=104.0) is True


def test_deadman_expired_before_any_beat():
    dm = Deadman(timeout_s=3.0)
    assert dm.expired(now=1.0) is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_safety.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.agent.safety'`

- [ ] **Step 3: Write minimal implementation**

```python
# drone/agent/safety.py
"""Agent-side safety primitives: link-tier classification + deadman timer.

`tier_from_rtt` maps a measured round-trip time to the safety tier the relay
enforces. `Deadman` tracks the last sign of life from the relay; when it expires
the agent triggers an ArduPilot failsafe (RTL) — see main.py.
"""
from __future__ import annotations

from drone.common.telemetry import LinkTier

GREEN_MAX_RTT_S = 0.05   # 50 ms
AMBER_MAX_RTT_S = 0.30   # 300 ms


def tier_from_rtt(rtt_s: float | None) -> LinkTier:
    if rtt_s is None:
        return LinkTier.RED
    if rtt_s <= GREEN_MAX_RTT_S:
        return LinkTier.GREEN
    if rtt_s <= AMBER_MAX_RTT_S:
        return LinkTier.AMBER
    return LinkTier.RED


class Deadman:
    def __init__(self, timeout_s: float) -> None:
        self.timeout_s = timeout_s
        self._last: float | None = None

    def beat(self, now: float) -> None:
        self._last = now

    def expired(self, now: float) -> bool:
        if self._last is None:
            return True
        return (now - self._last) > self.timeout_s
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest drone/tests/test_safety.py -v`
Expected: PASS (7 passed)

- [ ] **Step 5: Commit**

```bash
git add drone/agent/safety.py drone/tests/test_safety.py
git commit -m "feat(agent): link-tier classification + deadman timer"
```

---

## Task 9: Agent main wiring (bidirectional) + SITL e2e

**Files:**
- Modify: `drone/agent/main.py`
- Modify: `drone/agent/config.py` (add altitude bounds + heartbeat/deadman timings)
- Create: `drone/tests/test_e2e_commands_sitl.py`
- Modify: `docs/DEPLOY_DRONE_OPS.md` (note the Phase 2 command flow)

`main.py` is glue over tested units (executor, safety, commander), so it has no
unit test; the opt-in SITL e2e covers the integrated command path.

- [ ] **Step 1: Add config fields**

In `drone/agent/config.py`, add fields to `AgentConfig`:

```python
    min_alt_m: float
    max_alt_m: float
    heartbeat_hz: float
    deadman_timeout_s: float
```

In `from_env`, add (inside the `cls(...)` call):

```python
            min_alt_m=float(os.getenv("MIN_ALT_M", "5")),
            max_alt_m=float(os.getenv("MAX_ALT_M", "120")),
            heartbeat_hz=float(os.getenv("HEARTBEAT_HZ", "2")),
            deadman_timeout_s=float(os.getenv("DEADMAN_TIMEOUT_S", "5")),
```

- [ ] **Step 2: Rewrite `drone/agent/main.py` for bidirectional operation**

```python
# drone/agent/main.py
"""Agent entrypoint (Phase 2): telemetry out + commands in + heartbeat/deadman.

Three concurrent loops over one WebSocket:
- telemetry_loop: drain MAVLink, build Telemetry (stamped with current link tier), send.
- recv_loop: handle inbound commands (-> executor -> ack) and heartbeat echoes (-> RTT).
- heartbeat_loop: send heartbeats for RTT; trip the deadman -> RTL if the relay goes silent.

Glue only — executor, safety, commander, and the schema are unit-tested.
"""
from __future__ import annotations

import asyncio
import time

import websockets
from pymavlink import mavutil

from drone.agent.command_executor import CommandExecutor
from drone.agent.commander import PymavlinkCommander
from drone.agent.config import AgentConfig
from drone.agent.mavlink_source import TelemetryAccumulator
from drone.agent.safety import Deadman, tier_from_rtt
from drone.common.telemetry import Envelope


class AgentState:
    def __init__(self) -> None:
        self.tier_rtt_s: float | None = None
        self.seq = 0


async def run(cfg: AgentConfig) -> None:
    mav = mavutil.mavlink_connection(cfg.mavlink_url)
    mav.wait_heartbeat()
    acc = TelemetryAccumulator(cfg.drone_id)
    commander = PymavlinkCommander(mav)
    executor = CommandExecutor(commander, cfg.min_alt_m, cfg.max_alt_m)
    deadman = Deadman(cfg.deadman_timeout_s)
    state = AgentState()
    loop = asyncio.get_event_loop()

    async with websockets.connect(cfg.ops_url()) as ws:
        deadman.beat(time.time())

        async def telemetry_loop():
            while True:
                while True:
                    m = await loop.run_in_executor(None, lambda: mav.recv_match(blocking=False))
                    if m is None:
                        break
                    acc.update(m)
                telem = acc.build(ts=time.time(), seq=state.seq)
                if telem is not None:
                    telem = telem.model_copy(update={"link_tier": tier_from_rtt(state.tier_rtt_s)})
                    await ws.send(Envelope(type="telemetry", telemetry=telem).model_dump_json())
                    state.seq += 1
                await asyncio.sleep(cfg.period_s)

        async def recv_loop():
            async for raw in ws:
                deadman.beat(time.time())
                env = Envelope.model_validate_json(raw)
                if env.type == "command" and env.command is not None:
                    ack = executor.execute(env.command)
                    await ws.send(Envelope(type="ack", ack=ack).model_dump_json())
                elif env.type == "heartbeat" and env.ts is not None:
                    state.tier_rtt_s = time.time() - env.ts

        async def heartbeat_loop():
            period = 1.0 / cfg.heartbeat_hz
            while True:
                await ws.send(Envelope(type="heartbeat", ts=time.time()).model_dump_json())
                if deadman.expired(time.time()):
                    commander.rtl()  # link presumed lost -> fail safe
                await asyncio.sleep(period)

        await asyncio.gather(telemetry_loop(), recv_loop(), heartbeat_loop())


def main() -> None:
    asyncio.run(run(AgentConfig.from_env()))


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Write the opt-in SITL e2e test**

```python
# drone/tests/test_e2e_commands_sitl.py
import asyncio
import json
import os
import uuid

import pytest


def _enabled() -> bool:
    return os.getenv("RUN_SITL_E2E") == "1"


pytestmark = pytest.mark.skipif(
    not _enabled(), reason="set RUN_SITL_E2E=1 with SITL + relay + agent running"
)


async def test_arm_command_round_trips_with_ack():
    """Acquire control, send ARM, expect a success ack from the agent."""
    import websockets

    relay = os.getenv("RELAY_WS_URL", "ws://127.0.0.1:8800")
    ops_token = os.getenv("OPS_TOKEN", "otok")
    drone_id = os.getenv("DRONE_ID", "sitl-01")
    op = "e2e-op"
    url = f"{relay}/ws/ops/{drone_id}?token={ops_token}&operator={op}"

    async with websockets.connect(url) as ws:
        # wait until tier is known (a telemetry frame has set it on the relay)
        await asyncio.sleep(2)
        await ws.send(json.dumps({"type": "control",
                                  "control": {"action": "acquire", "operator_id": op}}))
        grant = json.loads(await asyncio.wait_for(ws.recv(), timeout=10))
        assert grant["control"]["granted"] is True

        cmd_id = str(uuid.uuid4())
        await ws.send(json.dumps({"type": "command",
                                  "command": {"cmd_id": cmd_id, "type": "ARM"}}))

        # the ops socket receives a stream (telemetry + ack); find our ack
        deadline = asyncio.get_event_loop().time() + 15
        ack = None
        while asyncio.get_event_loop().time() < deadline:
            frame = json.loads(await asyncio.wait_for(ws.recv(), timeout=15))
            if frame.get("type") == "ack" and frame["ack"]["cmd_id"] == cmd_id:
                ack = frame["ack"]
                break
        assert ack is not None and ack["success"] is True
```

- [ ] **Step 4: Run unit + skipped e2e**

Run: `python -m pytest drone/tests -v`
Expected: all unit tests PASS; `test_e2e_commands_sitl` SKIPPED.

- [ ] **Step 5: Append Phase 2 note to `docs/DEPLOY_DRONE_OPS.md`**

Add this section:

````markdown
## Phase 2 — commands over SITL

Agent gains command handling + a deadman (RTL on relay-link loss). New agent env:
`MIN_ALT_M=5 MAX_ALT_M=120 HEARTBEAT_HZ=2 DEADMAN_TIMEOUT_S=5`.

Run the command e2e (with SITL + relay + agent up):
```bash
RUN_SITL_E2E=1 RELAY_WS_URL=ws://127.0.0.1:8800 OPS_TOKEN=otok DRONE_ID=sitl-01 \
  python -m pytest drone/tests/test_e2e_commands_sitl.py -v
```
Watch the SITL console: the vehicle should arm. Try TAKEOFF (`{"alt":40}`), then RTL.
````

- [ ] **Step 6: Commit**

```bash
git add drone/agent/main.py drone/agent/config.py drone/tests/test_e2e_commands_sitl.py docs/DEPLOY_DRONE_OPS.md
git commit -m "feat(agent): bidirectional main (commands+heartbeat+deadman) + SITL e2e"
```

---

## Task 10: Frontend command client (extend liveOps.ts)

**Files:**
- Modify: `website/nextjs/lib/liveOps.ts`
- Test: `website/nextjs/tests/unit/liveOpsCommands.test.ts`

Add pure builders/parsers (unit-tested) and upgrade `connectLiveOps` to return a
handle that can `send` frames. The existing telemetry behavior is unchanged.

- [ ] **Step 1: Write the failing test**

```ts
// website/nextjs/tests/unit/liveOpsCommands.test.ts
import { describe, it, expect } from "vitest";
import {
  buildCommandEnvelope,
  buildControlEnvelope,
  parseAckFrame,
  parseControlFrame,
} from "@/lib/liveOps";

describe("command builders", () => {
  it("builds a command envelope with a cmd_id", () => {
    const env = buildCommandEnvelope("TAKEOFF", { alt: 40 });
    expect(env.type).toBe("command");
    expect(env.command.type).toBe("TAKEOFF");
    expect(env.command.params.alt).toBe(40);
    expect(typeof env.command.cmd_id).toBe("string");
    expect(env.command.cmd_id.length).toBeGreaterThan(0);
  });

  it("builds an acquire control envelope", () => {
    const env = buildControlEnvelope("acquire", "op-1");
    expect(env.type).toBe("control");
    expect(env.control.action).toBe("acquire");
    expect(env.control.operator_id).toBe("op-1");
  });
});

describe("frame parsers", () => {
  it("parses an ack frame", () => {
    const raw = JSON.stringify({ type: "ack", ack: { cmd_id: "c1", success: true, message: "ok" } });
    expect(parseAckFrame(raw)).toEqual({ cmd_id: "c1", success: true, message: "ok" });
  });

  it("returns null for non-ack", () => {
    expect(parseAckFrame(JSON.stringify({ type: "telemetry" }))).toBeNull();
    expect(parseAckFrame("bad")).toBeNull();
  });

  it("parses a control frame", () => {
    const raw = JSON.stringify({ type: "control", control: { action: "acquire", granted: true, holder: "op-1" } });
    const c = parseControlFrame(raw);
    expect(c?.granted).toBe(true);
    expect(c?.holder).toBe("op-1");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd website/nextjs && npx vitest run tests/unit/liveOpsCommands.test.ts`
Expected: FAIL — exports `buildCommandEnvelope` etc. not found

- [ ] **Step 3: Extend `website/nextjs/lib/liveOps.ts`**

Append these types, builders, and parsers (keep existing exports):

```ts
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
```

Then upgrade the connection. Replace the `LiveOpsHandlers` interface and add a
handle type:

```ts
export interface LiveOpsHandlers {
  onTelemetry: (t: Telemetry) => void;
  onStatus?: (s: "connecting" | "open" | "closed") => void;
  onAck?: (a: Ack) => void;
  onControl?: (c: ControlReply) => void;
}

export interface LiveOpsHandle {
  send: (env: object) => void;
  dispose: () => void;
}
```

Change the `connectLiveOps` signature to add `operatorId` and return a handle:

```ts
export function connectLiveOps(
  baseWsUrl: string,
  droneId: string,
  opsToken: string,
  operatorId: string,
  handlers: LiveOpsHandlers
): LiveOpsHandle {
```

In `open()`, append the operator to the URL:

```ts
    const url = `${baseWsUrl}/ws/ops/${droneId}?token=${encodeURIComponent(opsToken)}&operator=${encodeURIComponent(operatorId)}`;
```

Replace `ws.onmessage` so it routes telemetry/ack/control:

```ts
    ws.onmessage = (ev) => {
      const data = ev.data as string;
      const t = parseTelemetryFrame(data);
      if (t) { handlers.onTelemetry(t); return; }
      const ack = parseAckFrame(data);
      if (ack) { handlers.onAck?.(ack); return; }
      const ctl = parseControlFrame(data);
      if (ctl) { handlers.onControl?.(ctl); return; }
    };
```

Replace the final `return` (was a bare disposer) with the handle:

```ts
  open();
  return {
    send: (env: object) => ws?.send(JSON.stringify(env)),
    dispose: () => { closed = true; ws?.close(); },
  };
```

- [ ] **Step 4: Run command test + the Phase 1 telemetry test**

Run: `cd website/nextjs && npx vitest run tests/unit/liveOpsCommands.test.ts tests/unit/liveOps.test.ts`
Expected: PASS (both files green)

- [ ] **Step 5: Commit**

```bash
git add website/nextjs/lib/liveOps.ts website/nextjs/tests/unit/liveOpsCommands.test.ts
git commit -m "feat(web): live-ops command builders/parsers + send-capable handle"
```

---

## Task 11: Frontend Live Ops command UI (control lock + buttons + confirm gates)

**Files:**
- Modify: `website/nextjs/components/Platform/LiveOpsTab.tsx`

No new unit test (presentational + live socket); validated against SITL. Confirm
gates use `window.confirm` for the destructive trio (arm/takeoff/land). Note: the
`connectLiveOps` signature changed in Task 10 (now takes `operatorId` and returns
a `LiveOpsHandle`), so this replaces the Phase 1 `LiveOpsTab` body.

- [ ] **Step 1: Rewrite `LiveOpsTab.tsx` to use the send-capable handle**

```tsx
// website/nextjs/components/Platform/LiveOpsTab.tsx
"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  connectLiveOps, buildCommandEnvelope, buildControlEnvelope,
  type Telemetry, type Ack, type ControlReply, type CommandType, type LiveOpsHandle,
} from "@/lib/liveOps";

const RELAY_WS = process.env.NEXT_PUBLIC_RELAY_WS_URL ?? "";
const OPS_TOKEN = process.env.NEXT_PUBLIC_OPS_TOKEN ?? "";

const DESTRUCTIVE: CommandType[] = ["ARM", "TAKEOFF", "LAND"];

export default function LiveOpsTab({ droneId = "sitl-01" }: { droneId?: string }) {
  const operatorId = useMemo(
    () => "op-" + Math.random().toString(36).slice(2, 8), []);
  const [telem, setTelem] = useState<Telemetry | null>(null);
  const [status, setStatus] = useState("idle");
  const [hasControl, setHasControl] = useState(false);
  const [lastAck, setLastAck] = useState<Ack | null>(null);
  const handleRef = useRef<LiveOpsHandle | null>(null);

  useEffect(() => {
    if (!RELAY_WS) { setStatus("no relay configured"); return; }
    const h = connectLiveOps(RELAY_WS, droneId, OPS_TOKEN, operatorId, {
      onTelemetry: setTelem,
      onStatus: setStatus,
      onAck: setLastAck,
      onControl: (c: ControlReply) =>
        setHasControl(c.granted === true && c.holder === operatorId),
    });
    handleRef.current = h;
    return () => h.dispose();
  }, [droneId, operatorId]);

  const send = (env: object) => handleRef.current?.send(env);

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
      </div>

      {lastAck && (
        <p className={lastAck.success ? "ack-ok" : "ack-fail"}>
          {lastAck.success ? "✓" : "✗"} {lastAck.cmd_id.slice(0, 6)}: {lastAck.message}
        </p>
      )}

      {/* Map marker + breadcrumb: same as Phase 1 (reuse PlanMap.tsx Leaflet pattern). */}
      {telem && (
        <p className="liveops-pos">
          {telem.lat.toFixed(5)}, {telem.lon.toFixed(5)} @ {telem.heading_deg.toFixed(0)}°
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `cd website/nextjs && npm run build`
Expected: build succeeds; `/platform` Live Ops tab compiles with command UI.

- [ ] **Step 3: Manual verification against SITL**

With SITL + relay + agent running: open `/platform` → Live Ops, click **Acquire
control**, then **Arm** (confirm), **Takeoff 40m** (confirm) — watch the SITL
console arm and climb; acks should show ✓. Open a second browser tab and confirm
its command buttons stay disabled (it doesn't hold the lock). Verify buttons
disable when tier shows RED.

- [ ] **Step 4: Commit**

```bash
git add website/nextjs/components/Platform/LiveOpsTab.tsx
git commit -m "feat(web): Live Ops command UI with control lock + confirm gates"
```

---

## Task 12: Upload a planned mission to the drone

**Files:**
- Create: `website/nextjs/lib/missionToWaypoints.ts`
- Test: `website/nextjs/tests/unit/missionToWaypoints.test.ts`
- Modify: `website/nextjs/components/Platform/LiveOpsTab.tsx`

Reuse the existing mission planner output. The `UPLOAD_MISSION` command param is
`{waypoints: [{seq, lat, lon, alt_m}]}` (matches `commander.upload_mission`).

- [ ] **Step 1: Write the failing test**

```ts
// website/nextjs/tests/unit/missionToWaypoints.test.ts
import { describe, it, expect } from "vitest";
import { missionToWaypoints } from "@/lib/missionToWaypoints";

describe("missionToWaypoints", () => {
  it("maps planner waypoints to the agent upload format", () => {
    const planned = [
      { lat: 28.4, lon: 77.1, altitude: 40 },
      { lat: 28.41, lon: 77.1, altitude: 40 },
    ];
    const wps = missionToWaypoints(planned);
    expect(wps).toEqual([
      { seq: 0, lat: 28.4, lon: 77.1, alt_m: 40 },
      { seq: 1, lat: 28.41, lon: 77.1, alt_m: 40 },
    ]);
  });

  it("falls back to a default altitude when missing", () => {
    const wps = missionToWaypoints([{ lat: 1, lon: 2 }], 30);
    expect(wps[0].alt_m).toBe(30);
  });

  it("returns empty array for empty input", () => {
    expect(missionToWaypoints([])).toEqual([]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd website/nextjs && npx vitest run tests/unit/missionToWaypoints.test.ts`
Expected: FAIL — cannot resolve `@/lib/missionToWaypoints`

- [ ] **Step 3: Write `website/nextjs/lib/missionToWaypoints.ts`**

```ts
// website/nextjs/lib/missionToWaypoints.ts
// Adapts mission-planner waypoints into the UPLOAD_MISSION command payload the
// drone agent expects ({seq, lat, lon, alt_m}). Keeps the live-ops surface
// decoupled from the planner's internal Waypoint shape.

export interface PlannedPoint {
  lat: number;
  lon: number;
  altitude?: number;
}

export interface AgentWaypoint {
  seq: number;
  lat: number;
  lon: number;
  alt_m: number;
}

export function missionToWaypoints(
  points: PlannedPoint[],
  defaultAltM = 40
): AgentWaypoint[] {
  return points.map((p, i) => ({
    seq: i,
    lat: p.lat,
    lon: p.lon,
    alt_m: p.altitude ?? defaultAltM,
  }));
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd website/nextjs && npx vitest run tests/unit/missionToWaypoints.test.ts`
Expected: PASS (3 passed)

- [ ] **Step 5: Wire an "Upload mission to drone" button into `LiveOpsTab.tsx`**

Add the import:

```tsx
import { missionToWaypoints, type PlannedPoint } from "@/lib/missionToWaypoints";
```

Add `plannedPoints` to the component props (replace the existing props line):

```tsx
export default function LiveOpsTab(
  { droneId = "sitl-01", plannedPoints = [] }:
  { droneId?: string; plannedPoints?: PlannedPoint[] }
) {
```

Add inside the `.liveops-commands` div:

```tsx
        <button
          disabled={!cmdsEnabled || plannedPoints.length === 0}
          onClick={() => sendCmd("UPLOAD_MISSION", { waypoints: missionToWaypoints(plannedPoints) })}
        >
          Upload mission ({plannedPoints.length})
        </button>
```

- [ ] **Step 6: Verify build**

Run: `cd website/nextjs && npm run build`
Expected: build succeeds.

- [ ] **Step 7: Commit**

```bash
git add website/nextjs/lib/missionToWaypoints.ts website/nextjs/tests/unit/missionToWaypoints.test.ts website/nextjs/components/Platform/LiveOpsTab.tsx
git commit -m "feat(web): upload planned mission to drone via UPLOAD_MISSION"
```

---

## Self-Review Notes (resolved)

- **Spec coverage (Phase 2):** commands (Tasks 1, 6, 7), control-lock (Tasks 2, 5, 11),
  link-tier safety enforcement — relay-authoritative (Tasks 3, 5) + agent-side classification
  & deadman (Task 8), mission upload (Tasks 6, 12). **Command audit log is deferred to a
  Phase 2.1 follow-up** (Supabase write in the relay `_handle_command` path) — noted so it isn't
  lost; small additive change, kept out of this TDD chain to avoid coupling the command path to a
  DB in tests. ✔
- **Types consistent:** `CommandType` values match across Python (`commands.py`), the relay
  policy, the executor, and TS (`liveOps.ts`); `Ack`/`ControlMsg` field names
  (`cmd_id`/`success`/`message`, `action`/`operator_id`/`granted`/`holder`) match Python ↔ TS;
  `UPLOAD_MISSION` param shape `{waypoints:[{seq,lat,lon,alt_m}]}` matches
  `PymavlinkCommander.upload_mission` and `missionToWaypoints`. ✔
- **Authoritative gate + defense in depth:** relay enforces lock + tier (Task 5); the agent
  independently re-validates (Task 7) — both tested. ✔
- **Deadman:** agent trips RTL on relay-link loss (Task 9 heartbeat_loop + Task 8 `Deadman`). ✔
- **Signature change flagged:** Task 10 changes `connectLiveOps` (adds `operatorId`, returns a
  handle); Task 11 explicitly notes it replaces the Phase 1 `LiveOpsTab` body so the engineer
  doesn't half-migrate. ✔
- **Auth note carried from Phase 1:** ops auth is still the shared `OPS_TOKEN`; replacing it with
  the platform session/JWT now matters because commands exist — recommended as the first item in a
  Phase 2.1 hardening pass alongside the command audit log. ✔
```
