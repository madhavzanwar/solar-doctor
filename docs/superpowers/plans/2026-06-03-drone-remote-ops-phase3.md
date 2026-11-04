# Drone Remote Ops — Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stream live video from the Jetson to the browser over WebRTC — the USB webcam (RGB) first, then the iTL612R thermal pseudo-color feed — with a coturn TURN relay on the Oracle VM so video survives carrier NAT (LTE), and signaling carried over the existing relay WebSocket.

**Architecture:** The agent runs a GStreamer `webrtcbin` pipeline that hardware-encodes (Orin NVENC, H.264) one or two video tracks. SDP/ICE signaling rides the existing `Envelope` (new `signal` variant); the relay routes signaling frames between a specific operator and the drone (per-peer, not fan-out). Media flows peer-to-peer when possible, falling back to `coturn` on the Oracle VM (same box as the relay). The browser uses native `RTCPeerConnection`.

**Tech Stack:** Builds on Phases 1–2. New on the Jetson: GStreamer 1.0 + `gst-python` + `webrtcbin`/`nvv4l2h264enc` (system packages, NOT pip). New on the Oracle VM: `coturn` (system package). No new Python pip deps; no new frontend deps (native WebRTC).

**Spec:** `docs/superpowers/specs/2026-06-03-drone-remote-operations-design.md` (Phase 3: video, WebRTC + coturn).
**Depends on:** Phases 1 & 2 plans implemented (the `Envelope`, relay manager/server, agent main, and `liveOps.ts` from those phases).

---

## Conventions

- Same as prior phases: Python under `drone/`, tests via `python -m pytest drone/tests -v`; frontend via `cd website/nextjs && npx vitest run <file>`.
- Commit after every green step.
- **Per-peer routing:** unlike telemetry/ack (fanned to all operators), signaling targets a single `operator_id`. The relay routes by it.
- **No-hardware demo:** the agent video publisher supports a `videotestsrc` test pattern so the whole WebRTC path is demoable without a camera.

---

## Task 1: Signaling schema + extend Envelope

**Files:**
- Create: `drone/common/signaling.py`
- Modify: `drone/common/telemetry.py` (add `signal` to `Envelope`)
- Test: `drone/tests/test_signaling_schema.py`

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_signaling_schema.py
import pytest
from pydantic import ValidationError
from drone.common.signaling import SignalMsg, SignalKind
from drone.common.telemetry import Envelope


def test_offer_roundtrips():
    s = SignalMsg(kind=SignalKind.OFFER, operator_id="op-1", sdp="v=0...")
    again = SignalMsg.model_validate_json(s.model_dump_json())
    assert again == s
    assert again.kind is SignalKind.OFFER


def test_ice_candidate_carries_dict():
    s = SignalMsg(kind=SignalKind.ICE, operator_id="op-1",
                  candidate={"candidate": "candidate:...", "sdpMLineIndex": 0})
    assert s.candidate["sdpMLineIndex"] == 0


def test_unknown_kind_rejected():
    with pytest.raises(ValidationError):
        SignalMsg(kind="banana", operator_id="op-1")


def test_envelope_carries_signal():
    env = Envelope(type="signal",
                   signal=SignalMsg(kind=SignalKind.ANSWER, operator_id="op-2", sdp="v=0"))
    rt = Envelope.model_validate_json(env.model_dump_json())
    assert rt.signal is not None
    assert rt.signal.operator_id == "op-2"
    assert rt.signal.kind is SignalKind.ANSWER
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_signaling_schema.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.common.signaling'`

- [ ] **Step 3: Write `drone/common/signaling.py`**

```python
# drone/common/signaling.py
"""WebRTC signaling messages, carried over the same Envelope as everything else.

The relay treats these as opaque except for `operator_id`, which it uses to route
the frame to the right peer (signaling is per-peer, unlike telemetry fan-out).
"""
from __future__ import annotations

from enum import Enum
from pydantic import BaseModel


class SignalKind(str, Enum):
    OFFER = "offer"
    ANSWER = "answer"
    ICE = "ice"
    BYE = "bye"


class SignalMsg(BaseModel):
    kind: SignalKind
    operator_id: str
    sdp: str | None = None
    candidate: dict | None = None
```

- [ ] **Step 4: Extend `Envelope` in `drone/common/telemetry.py`**

Add the import after the existing `from drone.common.commands import ...` line:

```python
from drone.common.signaling import SignalMsg
```

Add the field to the `Envelope` class (alongside `command`/`ack`/`control`):

```python
    signal: SignalMsg | None = None
```

(Update the `Envelope` docstring `type` list to include `'signal'`.)

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest drone/tests/test_signaling_schema.py drone/tests/test_commands_schema.py -v`
Expected: PASS (all)

- [ ] **Step 6: Commit**

```bash
git add drone/common/signaling.py drone/common/telemetry.py drone/tests/test_signaling_schema.py
git commit -m "feat(drone): WebRTC signaling schema + envelope signal variant"
```

---

## Task 2: Manager operator-id registry + targeted send

**Files:**
- Modify: `drone/relay/manager.py`
- Test: `drone/tests/test_relay_manager_phase3.py`

Telemetry/ack fan out to all operators; signaling must reach exactly one. Add an
operator-id registry alongside the existing per-drone operator set.

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_relay_manager_phase3.py
import asyncio
import pytest
from drone.relay.manager import RelayManager


class FakeSink:
    def __init__(self):
        self.sent = []

    async def send_text(self, data: str):
        self.sent.append(data)


async def test_send_to_operator_targets_one():
    mgr = RelayManager()
    a, b = FakeSink(), FakeSink()
    mgr.register_operator("d1", "op-a", a)
    mgr.register_operator("d1", "op-b", b)
    ok = await mgr.send_to_operator("d1", "op-a", "frame")
    assert ok is True
    assert a.sent == ["frame"]
    assert b.sent == []


async def test_send_to_unknown_operator_returns_false():
    mgr = RelayManager()
    assert await mgr.send_to_operator("d1", "ghost", "x") is False


async def test_unregister_operator_removes_target():
    mgr = RelayManager()
    s = FakeSink()
    mgr.register_operator("d1", "op-a", s)
    mgr.unregister_operator("d1", "op-a")
    assert await mgr.send_to_operator("d1", "op-a", "x") is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_relay_manager_phase3.py -v`
Expected: FAIL — `AttributeError: 'RelayManager' object has no attribute 'register_operator'`

- [ ] **Step 3: Extend the implementation**

In `drone/relay/manager.py`, add to `__init__`:

```python
        self._operators_by_id: dict[str, dict[str, "Sink"]] = {}
```

Add these methods:

```python
    # --- addressable operators (for per-peer signaling) ---
    def register_operator(self, drone_id: str, operator_id: str, sink: "Sink") -> None:
        self._operators_by_id.setdefault(drone_id, {})[operator_id] = sink

    def unregister_operator(self, drone_id: str, operator_id: str) -> None:
        self._operators_by_id.get(drone_id, {}).pop(operator_id, None)

    async def send_to_operator(self, drone_id: str, operator_id: str, raw: str) -> bool:
        sink = self._operators_by_id.get(drone_id, {}).get(operator_id)
        if sink is None:
            return False
        await sink.send_text(raw)
        return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest drone/tests/test_relay_manager_phase3.py drone/tests/test_relay_manager_phase2.py -v`
Expected: PASS (all)

- [ ] **Step 5: Commit**

```bash
git add drone/relay/manager.py drone/tests/test_relay_manager_phase3.py
git commit -m "feat(relay): addressable operator registry for per-peer signaling"
```

---

## Task 3: Relay signaling routing

**Files:**
- Modify: `drone/relay/server.py`
- Test: `drone/tests/test_relay_signaling.py`

Ops → drone: forward the signal (already carries `operator_id`). Drone → ops:
route to the targeted operator. The ops socket also registers itself by id on
connect and unregisters on disconnect.

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_relay_signaling.py
import json
import pytest
from fastapi.testclient import TestClient
from drone.relay.server import create_app


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("DRONE_TOKENS", "sitl-01:dtok")
    monkeypatch.setenv("OPS_TOKEN", "otok")
    return TestClient(create_app())


def test_offer_from_ops_reaches_drone(client):
    with client.websocket_connect("/ws/drone/sitl-01?token=dtok") as drone:
        with client.websocket_connect("/ws/ops/sitl-01?token=otok&operator=op-a") as ops:
            ops.send_text(json.dumps({"type": "signal",
                "signal": {"kind": "offer", "operator_id": "op-a", "sdp": "v=0"}}))
            fwd = json.loads(drone.receive_text())
            assert fwd["type"] == "signal"
            assert fwd["signal"]["kind"] == "offer"
            assert fwd["signal"]["operator_id"] == "op-a"


def test_answer_from_drone_routes_to_target_operator(client):
    with client.websocket_connect("/ws/drone/sitl-01?token=dtok") as drone:
        with client.websocket_connect("/ws/ops/sitl-01?token=otok&operator=op-a") as ops_a:
            with client.websocket_connect("/ws/ops/sitl-01?token=otok&operator=op-b") as ops_b:
                drone.send_text(json.dumps({"type": "signal",
                    "signal": {"kind": "answer", "operator_id": "op-a", "sdp": "v=0"}}))
                reply = json.loads(ops_a.receive_text())
                assert reply["signal"]["kind"] == "answer"
                # op_a received it -> proves targeted routing by operator_id.
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_relay_signaling.py -v`
Expected: FAIL — signal frames are dropped (`receive_text` times out)

- [ ] **Step 3: Edit `drone/relay/server.py`**

In `drone_ws`, inside the `while True` message loop, add a branch:

```python
                elif env.type == "signal" and env.signal is not None:
                    await mgr.send_to_operator(drone_id, env.signal.operator_id, raw)
```

In `ops_ws`, register the operator by id right after `mgr.add_operator(...)`:

```python
        mgr.register_operator(drone_id, operator, ws)
```

and unregister in the `finally` block (alongside `mgr.remove_operator(...)`):

```python
            mgr.unregister_operator(drone_id, operator)
```

In the `ops_ws` message loop, add a branch to forward signals to the drone:

```python
                elif env.type == "signal" and env.signal is not None:
                    await mgr.send_to_drone(drone_id, raw)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest drone/tests/test_relay_signaling.py drone/tests/test_relay_server_phase2.py -v`
Expected: PASS (all — Phase 2 server tests still green)

- [ ] **Step 5: Commit**

```bash
git add drone/relay/server.py drone/tests/test_relay_signaling.py
git commit -m "feat(relay): route WebRTC signaling per operator"
```

---

## Task 4: TURN credential minting + ICE config endpoint

**Files:**
- Create: `drone/relay/turn.py`
- Modify: `drone/relay/server.py` (add `GET /turn-credentials`)
- Modify: `drone/relay/config.py` (TURN env helpers)
- Test: `drone/tests/test_turn.py`

coturn's `use-auth-secret` mode: the username is `<expiry-unix>:<name>` and the
password is `base64(HMAC-SHA1(secret, username))`. This lets the relay hand out
short-lived TURN creds without coturn talking to a database.

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_turn.py
import base64
import hashlib
import hmac
import time

import pytest
from drone.relay.turn import make_turn_credentials, ice_servers


def _urls_text(s):
    return s["urls"] if isinstance(s["urls"], str) else " ".join(s["urls"])


def test_credentials_have_expiring_username():
    user, pwd = make_turn_credentials(secret="s3cr3t", ttl_s=3600, name="op-a")
    expiry_str, _, name = user.partition(":")
    assert name == "op-a"
    assert int(expiry_str) > time.time()


def test_password_is_hmac_of_username():
    user, pwd = make_turn_credentials(secret="s3cr3t", ttl_s=3600, name="op-a")
    expected = base64.b64encode(
        hmac.new(b"s3cr3t", user.encode(), hashlib.sha1).digest()
    ).decode()
    assert pwd == expected


def test_ice_servers_includes_stun_and_turn(monkeypatch):
    monkeypatch.setenv("TURN_SECRET", "s3cr3t")
    monkeypatch.setenv("TURN_HOST", "turn.example.com")
    servers = ice_servers(name="op-a")
    urls = " ".join(_urls_text(s) for s in servers)
    assert "stun:" in urls
    assert "turn:" in urls
    turn = next(s for s in servers if "turn:" in _urls_text(s))
    assert "username" in turn and "credential" in turn


def test_ice_servers_stun_only_when_no_secret(monkeypatch):
    monkeypatch.delenv("TURN_SECRET", raising=False)
    monkeypatch.setenv("TURN_HOST", "turn.example.com")
    servers = ice_servers(name="op-a")
    assert all("turn:" not in _urls_text(s) for s in servers)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_turn.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.relay.turn'`

- [ ] **Step 3: Write `drone/relay/turn.py` and config helpers**

```python
# drone/relay/turn.py
"""Short-lived TURN credentials for coturn `use-auth-secret` mode.

The relay mints time-limited credentials so browsers/agents can use the TURN
relay without coturn needing a user database. STUN is always offered (when a host
is set); TURN is added only when TURN_SECRET is configured.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time


def make_turn_credentials(secret: str, ttl_s: int, name: str) -> tuple[str, str]:
    expiry = int(time.time()) + ttl_s
    username = f"{expiry}:{name}"
    digest = hmac.new(secret.encode(), username.encode(), hashlib.sha1).digest()
    password = base64.b64encode(digest).decode()
    return username, password


def ice_servers(name: str, ttl_s: int = 3600) -> list[dict]:
    host = os.getenv("TURN_HOST", "")
    secret = os.getenv("TURN_SECRET", "")
    servers: list[dict] = []
    if host:
        servers.append({"urls": f"stun:{host}:3478"})
    if host and secret:
        user, pwd = make_turn_credentials(secret, ttl_s, name)
        servers.append({
            "urls": [f"turn:{host}:3478?transport=udp", f"turn:{host}:3478?transport=tcp"],
            "username": user,
            "credential": pwd,
        })
    return servers
```

In `drone/relay/config.py`, add:

```python
def turn_host() -> str:
    return os.getenv("TURN_HOST", "")


def turn_secret() -> str:
    return os.getenv("TURN_SECRET", "")
```

- [ ] **Step 4: Add the endpoint to `drone/relay/server.py`**

Add the import:

```python
from drone.relay.turn import ice_servers
```

Add inside `create_app()` (near `/health`):

```python
    @app.get("/turn-credentials")
    def turn_credentials(token: str = "", name: str = "anon"):
        from fastapi import HTTPException
        from drone.relay.auth import AuthError, verify_operator_token
        try:
            verify_operator_token(token)
        except AuthError:
            raise HTTPException(status_code=403, detail="invalid operator token")
        return {"iceServers": ice_servers(name=name)}
```

- [ ] **Step 5: Write the endpoint test (append to `drone/tests/test_turn.py`)**

```python
def test_turn_endpoint_requires_token(monkeypatch):
    from fastapi.testclient import TestClient
    from drone.relay.server import create_app
    monkeypatch.setenv("DRONE_TOKENS", "sitl-01:dtok")
    monkeypatch.setenv("OPS_TOKEN", "otok")
    monkeypatch.setenv("TURN_HOST", "turn.example.com")
    client = TestClient(create_app())

    assert client.get("/turn-credentials?token=WRONG").status_code == 403
    ok = client.get("/turn-credentials?token=otok&name=op-a")
    assert ok.status_code == 200
    assert "iceServers" in ok.json()
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest drone/tests/test_turn.py -v`
Expected: PASS (all)

- [ ] **Step 7: Commit**

```bash
git add drone/relay/turn.py drone/relay/config.py drone/relay/server.py drone/tests/test_turn.py
git commit -m "feat(relay): TURN credential minting + ICE config endpoint"
```

---

## Task 5: Agent GStreamer pipeline builders

**Files:**
- Create: `drone/agent/video_pipeline.py`
- Test: `drone/tests/test_video_pipeline.py`

Pure string builders for the GStreamer pipelines. Keeping pipeline construction
pure lets us unit-test the wiring (hardware encode, payloader, caps) without
GStreamer installed in CI.

- [ ] **Step 1: Write the failing test**

```python
# drone/tests/test_video_pipeline.py
from drone.agent.video_pipeline import build_video_pipeline


def test_webcam_pipeline_uses_device_and_hardware_encode():
    p = build_video_pipeline(name="rgb", device="/dev/video0",
                             bitrate_bps=4_000_000, use_test_pattern=False)
    assert "v4l2src" in p
    assert "/dev/video0" in p
    assert "nvv4l2h264enc" in p          # Orin hardware H.264
    assert "rtph264pay" in p
    assert "webrtcbin" in p
    assert "name=rgb" in p


def test_test_pattern_pipeline_has_no_device():
    p = build_video_pipeline(name="rgb", device="/dev/video0",
                             bitrate_bps=2_000_000, use_test_pattern=True)
    assert "videotestsrc" in p
    assert "v4l2src" not in p


def test_bitrate_is_embedded():
    p = build_video_pipeline(name="thermal", device="/dev/video1",
                             bitrate_bps=1_500_000, use_test_pattern=False)
    assert "1500000" in p
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest drone/tests/test_video_pipeline.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'drone.agent.video_pipeline'`

- [ ] **Step 3: Write minimal implementation**

```python
# drone/agent/video_pipeline.py
"""GStreamer pipeline strings for WebRTC video on the Jetson Orin.

Hardware-encodes H.264 via NVENC (`nvv4l2h264enc`) and feeds a named `webrtcbin`.
`use_test_pattern=True` swaps the camera for `videotestsrc` so the WebRTC path is
demoable with no hardware. Pure string construction — no GStreamer import here.
"""
from __future__ import annotations


def build_video_pipeline(
    *, name: str, device: str, bitrate_bps: int, use_test_pattern: bool
) -> str:
    if use_test_pattern:
        source = "videotestsrc is-live=true pattern=ball"
    else:
        source = f"v4l2src device={device}"
    return (
        f"webrtcbin name={name} "
        f"{source} ! videoconvert ! nvvidconv ! "
        f"nvv4l2h264enc bitrate={bitrate_bps} insert-sps-pps=true ! "
        f"h264parse ! rtph264pay config-interval=1 pt=96 ! "
        f"application/x-rtp,media=video,encoding-name=H264,payload=96 ! {name}."
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest drone/tests/test_video_pipeline.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add drone/agent/video_pipeline.py drone/tests/test_video_pipeline.py
git commit -m "feat(agent): GStreamer webrtcbin pipeline builders (pure, tested)"
```

---

## Task 6: Agent WebRTC publisher (glue) + config + main integration

**Files:**
- Create: `drone/agent/webrtc_publisher.py`
- Modify: `drone/agent/config.py` (video env)
- Modify: `drone/agent/main.py` (start the publisher; route `signal` frames)
- Modify: `docs/DEPLOY_DRONE_OPS.md` (GStreamer install on Jetson)

`webrtc_publisher.py` is glue over GStreamer + the (tested) pipeline builders. It
has no unit test; it is verified manually via the test-pattern path. It exchanges
SDP/ICE by calling back into the agent's WebSocket using `SignalMsg`.

- [ ] **Step 1: Add video config fields**

In `drone/agent/config.py`, add to `AgentConfig`:

```python
    video_enabled: bool
    webcam_device: str
    thermal_device: str
    video_test_pattern: bool
    video_bitrate_bps: int
```

In `from_env`, add:

```python
            video_enabled=os.getenv("VIDEO_ENABLED", "1") == "1",
            webcam_device=os.getenv("WEBCAM_DEVICE", "/dev/video0"),
            thermal_device=os.getenv("THERMAL_DEVICE", "/dev/video1"),
            video_test_pattern=os.getenv("VIDEO_TEST_PATTERN", "0") == "1",
            video_bitrate_bps=int(os.getenv("VIDEO_BITRATE_BPS", "4000000")),
```

- [ ] **Step 2: Write `drone/agent/webrtc_publisher.py`**

```python
# drone/agent/webrtc_publisher.py
"""WebRTC publisher: one webrtcbin pipeline per operator who requests video.

Glue over GStreamer. The agent receives an OFFER (SignalMsg) from an operator,
spins up a pipeline (webcam track), sets the remote description, creates an
ANSWER, and trickles ICE back via `send_signal`.

`send_signal(SignalMsg)` is provided by main.py and writes to the relay WS.
Requires system GStreamer + gst-python (gi). Imported only on the Jetson (main.py
imports it locally), so CI without GStreamer is unaffected.
"""
from __future__ import annotations

from typing import Awaitable, Callable

import gi  # type: ignore

gi.require_version("Gst", "1.0")
gi.require_version("GstWebRTC", "1.0")
gi.require_version("GstSdp", "1.0")
from gi.repository import Gst, GstSdp, GstWebRTC  # type: ignore  # noqa: E402

from drone.agent.video_pipeline import build_video_pipeline
from drone.common.signaling import SignalKind, SignalMsg

Gst.init(None)

SendSignal = Callable[[SignalMsg], Awaitable[None]]


class WebRTCPublisher:
    def __init__(self, cfg, send_signal: SendSignal) -> None:
        self.cfg = cfg
        self.send_signal = send_signal
        self._peers: dict[str, Gst.Pipeline] = {}

    async def handle_offer(self, sig: SignalMsg) -> None:
        op = sig.operator_id
        desc = build_video_pipeline(
            name="rgb",
            device=self.cfg.webcam_device,
            bitrate_bps=self.cfg.video_bitrate_bps,
            use_test_pattern=self.cfg.video_test_pattern,
        )
        pipe = Gst.parse_launch(desc)
        self._peers[op] = pipe
        webrtc = pipe.get_by_name("rgb")
        webrtc.connect("on-ice-candidate",
                       lambda el, mline, cand: self._on_ice(op, mline, cand))

        _, sdpmsg = GstSdp.SDPMessage.new_from_text(sig.sdp)
        offer = GstWebRTC.WebRTCSessionDescription.new(
            GstWebRTC.WebRTCSDPType.OFFER, sdpmsg)
        promise = Gst.Promise.new()
        webrtc.emit("set-remote-description", offer, promise)
        promise.interrupt()
        pipe.set_state(Gst.State.PLAYING)

        def _on_answer(prom, _):
            reply = prom.get_reply()
            answer = reply.get_value("answer")
            p2 = Gst.Promise.new()
            webrtc.emit("set-local-description", answer, p2)
            p2.interrupt()
            self._post(SignalMsg(kind=SignalKind.ANSWER, operator_id=op,
                                 sdp=answer.sdp.as_text()))

        webrtc.emit("create-answer", None,
                    Gst.Promise.new_with_change_func(_on_answer, None))

    def _on_ice(self, op, mline, candidate):
        self._post(SignalMsg(kind=SignalKind.ICE, operator_id=op,
                             candidate={"candidate": candidate, "sdpMLineIndex": mline}))

    async def handle_ice(self, sig: SignalMsg) -> None:
        pipe = self._peers.get(sig.operator_id)
        if pipe and sig.candidate:
            webrtc = pipe.get_by_name("rgb")
            webrtc.emit("add-ice-candidate",
                        sig.candidate["sdpMLineIndex"], sig.candidate["candidate"])

    async def handle_bye(self, sig: SignalMsg) -> None:
        pipe = self._peers.pop(sig.operator_id, None)
        if pipe:
            pipe.set_state(Gst.State.NULL)

    def _post(self, sig: SignalMsg) -> None:
        import asyncio
        asyncio.create_task(self.send_signal(sig))
```

- [ ] **Step 3: Wire the publisher into `drone/agent/main.py`**

In `run()`, after the WS connect and before `asyncio.gather`, create the publisher
(only if video is enabled):

```python
    from drone.agent.webrtc_publisher import WebRTCPublisher  # Jetson-only import
    from drone.common.signaling import SignalKind, SignalMsg

    publisher = None
    if cfg.video_enabled:
        async def send_signal(sig: SignalMsg) -> None:
            await ws.send(Envelope(type="signal", signal=sig).model_dump_json())
        publisher = WebRTCPublisher(cfg, send_signal)
```

In `recv_loop`, add a branch to dispatch signal frames to the publisher:

```python
                elif env.type == "signal" and env.signal is not None and publisher is not None:
                    if env.signal.kind is SignalKind.OFFER:
                        await publisher.handle_offer(env.signal)
                    elif env.signal.kind is SignalKind.ICE:
                        await publisher.handle_ice(env.signal)
                    elif env.signal.kind is SignalKind.BYE:
                        await publisher.handle_bye(env.signal)
```

- [ ] **Step 4: Run the full unit suite (publisher excluded automatically)**

Run: `python -m pytest drone/tests -v`
Expected: all unit tests PASS; SITL e2e SKIPPED. (The publisher module isn't
imported by any test, and main.py imports it locally, so CI without GStreamer is
unaffected.)

- [ ] **Step 5: Append the Jetson GStreamer install to `docs/DEPLOY_DRONE_OPS.md`**

````markdown
## Phase 3 — video (Jetson GStreamer + relay coturn)

### Jetson packages (NOT pip)
```bash
sudo apt-get install -y \
  gstreamer1.0-tools gstreamer1.0-plugins-base gstreamer1.0-plugins-good \
  gstreamer1.0-plugins-bad gstreamer1.0-plugins-ugly gstreamer1.0-nice \
  python3-gi gir1.2-gst-plugins-bad-1.0
# webrtcbin lives in gstreamer1.0-plugins-bad; nvv4l2h264enc ships with JetPack.
```

### Agent video env
`VIDEO_ENABLED=1 WEBCAM_DEVICE=/dev/video0 THERMAL_DEVICE=/dev/video1 VIDEO_BITRATE_BPS=4000000`
For a no-camera demo: `VIDEO_TEST_PATTERN=1`.
````

- [ ] **Step 6: Commit**

```bash
git add drone/agent/webrtc_publisher.py drone/agent/config.py drone/agent/main.py docs/DEPLOY_DRONE_OPS.md
git commit -m "feat(agent): WebRTC publisher (webrtcbin) + signal routing in main"
```

---

## Task 7: Frontend signaling helpers + ICE config fetch

**Files:**
- Create: `website/nextjs/lib/liveVideo.ts`
- Test: `website/nextjs/tests/unit/liveVideo.test.ts`

Pure builders/parsers (tested) plus a thin `fetchIceServers`. The RTCPeerConnection
wiring lives in the component (Task 8).

- [ ] **Step 1: Write the failing test**

```ts
// website/nextjs/tests/unit/liveVideo.test.ts
import { describe, it, expect, vi } from "vitest";
import {
  buildSignalEnvelope, parseSignalFrame, fetchIceServers,
} from "@/lib/liveVideo";

describe("signal helpers", () => {
  it("builds an offer signal envelope", () => {
    const env = buildSignalEnvelope("offer", "op-1", { sdp: "v=0" });
    expect(env.type).toBe("signal");
    expect(env.signal.kind).toBe("offer");
    expect(env.signal.operator_id).toBe("op-1");
    expect(env.signal.sdp).toBe("v=0");
  });

  it("builds an ice signal envelope", () => {
    const env = buildSignalEnvelope("ice", "op-1", {
      candidate: { candidate: "c", sdpMLineIndex: 0 },
    });
    expect(env.signal.candidate.sdpMLineIndex).toBe(0);
  });

  it("parses a signal frame", () => {
    const raw = JSON.stringify({ type: "signal", signal: { kind: "answer", operator_id: "op-1", sdp: "v=0" } });
    const s = parseSignalFrame(raw);
    expect(s?.kind).toBe("answer");
    expect(s?.sdp).toBe("v=0");
  });

  it("returns null for non-signal frames", () => {
    expect(parseSignalFrame(JSON.stringify({ type: "telemetry" }))).toBeNull();
    expect(parseSignalFrame("nope")).toBeNull();
  });
});

describe("fetchIceServers", () => {
  it("hits the relay turn endpoint and returns iceServers", async () => {
    const servers = [{ urls: "stun:turn.example.com:3478" }];
    global.fetch = vi.fn().mockResolvedValue({
      ok: true, json: async () => ({ iceServers: servers }),
    }) as unknown as typeof fetch;
    const out = await fetchIceServers("https://relay.example.com", "otok", "op-1");
    expect(out).toEqual(servers);
  });

  it("falls back to a public STUN server on failure", async () => {
    global.fetch = vi.fn().mockResolvedValue({ ok: false }) as unknown as typeof fetch;
    const out = await fetchIceServers("https://relay.example.com", "otok", "op-1");
    expect(out[0].urls).toContain("stun:");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd website/nextjs && npx vitest run tests/unit/liveVideo.test.ts`
Expected: FAIL — cannot resolve `@/lib/liveVideo`

- [ ] **Step 3: Write `website/nextjs/lib/liveVideo.ts`**

```ts
// website/nextjs/lib/liveVideo.ts
// WebRTC signaling helpers for the live video feed. Signaling rides the existing
// live-ops WebSocket (send via the LiveOpsHandle from liveOps.ts). ICE servers are
// fetched from the relay's /turn-credentials endpoint.

export type SignalKind = "offer" | "answer" | "ice" | "bye";

export interface SignalMsg {
  kind: SignalKind;
  operator_id: string;
  sdp?: string;
  candidate?: { candidate: string; sdpMLineIndex: number };
}

export function buildSignalEnvelope(
  kind: SignalKind,
  operatorId: string,
  body: { sdp?: string; candidate?: SignalMsg["candidate"] } = {}
) {
  return { type: "signal", signal: { kind, operator_id: operatorId, ...body } };
}

export function parseSignalFrame(raw: string): SignalMsg | null {
  try {
    const env = JSON.parse(raw);
    return env?.type === "signal" && env.signal ? (env.signal as SignalMsg) : null;
  } catch {
    return null;
  }
}

const PUBLIC_STUN: RTCIceServer[] = [{ urls: "stun:stun.l.google.com:19302" }];

export async function fetchIceServers(
  relayHttpUrl: string,
  opsToken: string,
  name: string
): Promise<RTCIceServer[]> {
  try {
    const res = await fetch(
      `${relayHttpUrl}/turn-credentials?token=${encodeURIComponent(opsToken)}&name=${encodeURIComponent(name)}`
    );
    if (!res.ok) return PUBLIC_STUN;
    const data = await res.json();
    return (data.iceServers as RTCIceServer[]) ?? PUBLIC_STUN;
  } catch {
    return PUBLIC_STUN;
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd website/nextjs && npx vitest run tests/unit/liveVideo.test.ts`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add website/nextjs/lib/liveVideo.ts website/nextjs/tests/unit/liveVideo.test.ts
git commit -m "feat(web): WebRTC signaling helpers + ICE config fetch"
```

---

## Task 8: Frontend video panel (RTCPeerConnection + start/stop)

**Files:**
- Modify: `website/nextjs/lib/liveOps.ts` (add `onSignal` passthrough)
- Create: `website/nextjs/components/Platform/VideoPanel.tsx`
- Modify: `website/nextjs/components/Platform/LiveOpsTab.tsx` (mount the panel)

No unit test (browser RTCPeerConnection + media); validated manually with the
agent's test-pattern path. The panel is the WebRTC offerer; the agent answers.

- [ ] **Step 1: Add `onSignal` to `liveOps.ts`**

In `LiveOpsHandlers`, add:

```ts
  onSignal?: (raw: string) => void;
```

In `ws.onmessage`, after the control branch (before the function ends), add a
signal passthrough that forwards the raw frame:

```ts
      if (data.includes('"type":"signal"')) { handlers.onSignal?.(data); return; }
```

- [ ] **Step 2: Create `VideoPanel.tsx`**

```tsx
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
```

- [ ] **Step 3: Mount `VideoPanel` in `LiveOpsTab.tsx`**

Add the import:

```tsx
import VideoPanel from "@/components/Platform/VideoPanel";
```

Add a ref to hold the signal handler:

```tsx
  const signalHandlerRef = useRef<((raw: string) => void) | null>(null);
```

In the `connectLiveOps` handlers object, add the `onSignal` passthrough:

```tsx
      onSignal: (raw: string) => signalHandlerRef.current?.(raw),
```

Render the panel (e.g. below the HUD):

```tsx
      <VideoPanel
        operatorId={operatorId}
        send={send}
        registerSignalHandler={(fn) => { signalHandlerRef.current = fn; }}
      />
```

- [ ] **Step 4: Verify build**

Run: `cd website/nextjs && npm run build`
Expected: build succeeds.

- [ ] **Step 5: Manual verification (no camera needed)**

Start relay (TURN env optional) + the agent with `VIDEO_TEST_PATTERN=1`. Open
`/platform` → Live Ops → **Start video**. The bouncing `videotestsrc` ball should
appear within a few seconds (P2P on LAN; via coturn on LTE). Confirm `state`
reaches `streaming`.

- [ ] **Step 6: Commit**

```bash
git add website/nextjs/lib/liveOps.ts website/nextjs/components/Platform/VideoPanel.tsx website/nextjs/components/Platform/LiveOpsTab.tsx
git commit -m "feat(web): WebRTC video panel wired into Live Ops"
```

---

## Task 9: coturn deployment on the Oracle VM

**Files:**
- Modify: `docs/DEPLOY_DRONE_OPS.md`

Infra task — no code. Documents standing up coturn next to the relay and the env
the relay needs to mint matching credentials.

- [ ] **Step 1: Append the coturn runbook to `docs/DEPLOY_DRONE_OPS.md`**

````markdown
### coturn on the Oracle A1 VM

```bash
sudo apt-get install -y coturn
sudo tee /etc/turnserver.conf >/dev/null <<'EOF'
listening-port=3478
fingerprint
use-auth-secret
static-auth-secret=CHANGE_ME_LONG_RANDOM
realm=relay.axalonsystems.com
total-quota=100
no-tls
no-dtls
EOF
sudo systemctl enable --now coturn
```

Open UDP/TCP 3478 (and the relay port) in the Oracle security list + the VM firewall.

Relay env must match coturn:
`TURN_HOST=relay.axalonsystems.com TURN_SECRET=CHANGE_ME_LONG_RANDOM`
(same value as `static-auth-secret`). Browser fetches creds from
`GET /turn-credentials`; the agent uses the same endpoint or its own env.

For production TLS, terminate `turns:` via Cloudflare Spectrum or a cert on coturn
(`cert`/`pkey` + remove `no-tls`/`no-dtls`). Phase 3 ships plain STUN/TURN; harden
in the Phase 3.1 pass.
````

- [ ] **Step 2: Commit**

```bash
git add docs/DEPLOY_DRONE_OPS.md
git commit -m "docs: coturn deployment runbook for drone video"
```

---

## Phase 3.1 backlog (deferred, noted so it isn't lost)

- **Thermal as a second track:** Task 5's builder already parametrizes `name`/`device`;
  extend `WebRTCPublisher.handle_offer` to add a `thermal` webrtcbin/track and the
  frontend `VideoPanel` to show a second `<video>` + RGB/thermal toggle. Held back so
  Phase 3 lands a working single-feed path first (and so the Orin's dual-encode CPU
  budget can be measured before committing the UI).
- **turns:/TLS** on coturn (Cloudflare Spectrum or coturn cert).
- **Bitrate adaptation** from the link tier (drop bitrate on AMBER).
- **Recording tap:** the same pipeline can `tee` to a filesink for the post-flight
  inspection pipeline — belongs with Phase 6's recording→pipeline handoff.

---

## Self-Review Notes (resolved)

- **Spec coverage (Phase 3):** WebRTC video webcam-first (Tasks 5–8), signaling over the
  relay (Tasks 1–3), coturn TURN for NAT traversal (Tasks 4, 9), no-hardware demo path
  (test pattern, Tasks 5/6/8). **Thermal second track is explicitly deferred to Phase 3.1**
  (documented above) — webcam-first matches the spec's "webcam first, then thermal" ordering. ✔
- **Types consistent:** `SignalKind` values (`offer`/`answer`/`ice`/`bye`) and `SignalMsg`
  field names (`kind`/`operator_id`/`sdp`/`candidate`) match Python (`signaling.py`) ↔ TS
  (`liveVideo.ts`); `candidate` shape `{candidate, sdpMLineIndex}` matches both ends and the
  publisher's `add-ice-candidate` call. ✔
- **Per-peer routing:** signaling routes by `operator_id` via `send_to_operator` (Task 2),
  distinct from telemetry/ack fan-out — tested in Task 3. ✔
- **CI-safe:** `webrtc_publisher.py` imports `gi` (Jetson-only) and is imported *locally* inside
  `main.run()` + never by a test, so `python -m pytest drone/tests` stays green without GStreamer.
  The pipeline builders (the part worth testing) are pure and import nothing. ✔
- **No placeholders:** every code step has full code; the only documented-as-deferred item is the
  thermal second track (Phase 3.1), not a gap in the webcam path. ✔
- **Carried hardening note:** TURN ships without TLS in Phase 3 (`no-tls`/`no-dtls`); flagged for
  the hardening pass alongside the Phase 2.1 audit-log + JWT items. ✔
```
