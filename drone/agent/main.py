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

        from drone.common.signaling import SignalKind, SignalMsg

        publisher = None
        if cfg.video_enabled:
            # Jetson-only import: keeps CI (no GStreamer) able to import main.py
            from drone.agent.webrtc_publisher import WebRTCPublisher

            async def send_signal(sig: SignalMsg) -> None:
                await ws.send(Envelope(type="signal", signal=sig).model_dump_json())

            publisher = WebRTCPublisher(cfg, send_signal)

        from drone.agent.manual_control import ManualController, ManualDeadman
        manual = ManualController(commander)
        manual_dm = ManualDeadman(cfg.manual_deadman_s)
        manual_active = {"on": False}

        from drone.agent.gps_inject import TelemetryFix, nearest_fix
        from drone.agent.landing import LandingDetector
        from drone.agent.recorder import write_sidecar, build_manifest
        from drone.agent.handoff import zip_capture, post_handoff

        telem_log: list[TelemetryFix] = []   # rolling fix log for post-flight GPS inject
        landing = LandingDetector()

        async def _do_handoff():
            # On landing: stamp each captured frame with the nearest-in-time GPS fix
            # (thermal core has no EXIF GPS), then POST the capture to the platform.
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
            build_manifest(cfg.park_id, frames)
            if cfg.platform_api_url and cfg.park_id:
                zip_bytes = zip_capture(cfg.capture_dir)
                await post_handoff(base_url=cfg.platform_api_url, token=cfg.platform_token,
                                   park_id=cfg.park_id, zip_bytes=zip_bytes)

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
                    telem_log.append(TelemetryFix(
                        ts=telem.ts, lat=telem.lat, lon=telem.lon, alt_rel_m=telem.alt_rel_m))
                    if len(telem_log) > 24000:   # ~20 min @ 20Hz: bound memory
                        del telem_log[: len(telem_log) - 24000]
                    if cfg.recording_enabled and landing.update(telem.armed):
                        asyncio.create_task(_do_handoff())
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
                elif env.type == "signal" and env.signal is not None and publisher is not None:
                    if env.signal.kind is SignalKind.OFFER:
                        await publisher.handle_offer(env.signal)
                    elif env.signal.kind is SignalKind.ICE:
                        await publisher.handle_ice(env.signal)
                    elif env.signal.kind is SignalKind.BYE:
                        await publisher.handle_bye(env.signal)
                elif env.type == "manual" and env.manual is not None:
                    manual_active["on"] = True
                    manual_dm.beat(time.time())
                    manual.apply(env.manual)

        async def heartbeat_loop():
            period = 1.0 / cfg.heartbeat_hz
            while True:
                await ws.send(Envelope(type="heartbeat", ts=time.time()).model_dump_json())
                if deadman.expired(time.time()):
                    commander.rtl()  # link presumed lost -> fail safe
                if manual_active["on"] and manual_dm.expired(time.time()):
                    manual.hover()  # manual input went stale -> hold position
                    manual_active["on"] = False
                await asyncio.sleep(period)

        await asyncio.gather(telemetry_loop(), recv_loop(), heartbeat_loop())


def main() -> None:
    asyncio.run(run(AgentConfig.from_env()))


if __name__ == "__main__":
    main()
