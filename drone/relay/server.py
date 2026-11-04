# drone/relay/server.py
"""Relay FastAPI app (Phase 2).

- /ws/drone/{drone_id}?token=... : agent pushes telemetry/ack/heartbeat; receives commands.
- /ws/ops/{drone_id}?token=...&operator=... : browser sends control/command; receives telemetry/ack/control.

The relay is the command authority: it enforces the control lock and the
link-tier policy before forwarding any command to the drone.
"""
from __future__ import annotations

import asyncio
import json
import time

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, status
from fastapi.middleware.cors import CORSMiddleware

from drone.common.commands import Ack, ControlAction, ControlMsg
from drone.common.telemetry import Envelope
from drone.relay.auth import AuthError, verify_drone_token, verify_operator_token
from drone.relay.config import cors_origins, ping_interval_s
from drone.relay.control_lock import ControlLock
from drone.relay.manager import RelayManager
from drone.relay.tier_policy import authorize_command, authorize_manual
from drone.relay.turn import ice_servers


async def _keepalive(ws: WebSocket, interval_s: float) -> None:
    """Send a small data frame on an otherwise idle socket.

    Browsers never send WebSocket pings and some proxies ignore control frames
    when deciding a connection is idle, so an operator watching an offline drone
    would be cut off after ~60 s. Clients ignore unknown frame types.
    """
    while True:
        await asyncio.sleep(interval_s)
        try:
            await ws.send_text(json.dumps({"type": "ping", "ts": time.time()}))
        except Exception:
            return  # socket gone; the receive loop handles cleanup


def create_app(*, cors: bool = True) -> FastAPI:
    """Build the relay app.

    cors=False when mounted inside another app (the platform API mounts it at
    /relay): the host's CORS middleware already covers these routes, and a second
    CORSMiddleware would emit a duplicate Access-Control-Allow-Origin header,
    which browsers reject.
    """
    app = FastAPI(title="Axalon Drone Relay")
    if cors:
        # Browsers call GET /turn-credentials cross-origin from the website.
        app.add_middleware(
            CORSMiddleware,
            allow_origins=cors_origins(),
            allow_methods=["GET", "HEAD", "OPTIONS"],
            allow_headers=["*"],
        )
    mgr = RelayManager()
    lock = ControlLock()
    ping_every = ping_interval_s()
    app.state.manager = mgr
    app.state.lock = lock

    @app.api_route("/", methods=["GET", "HEAD"])
    @app.api_route("/health", methods=["GET", "HEAD"])
    def health():
        return {"status": "ok"}

    @app.get("/turn-credentials")
    def turn_credentials(token: str = "", name: str = "anon"):
        from fastapi import HTTPException
        try:
            verify_operator_token(token)
        except AuthError:
            raise HTTPException(status_code=403, detail="invalid operator token")
        return {"iceServers": ice_servers(name=name)}

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
                if env.type == "telemetry":
                    if env.telemetry is not None:
                        mgr.set_tier(drone_id, env.telemetry.link_tier)
                    await mgr.fan_to_operators(drone_id, raw)
                elif env.type == "ack":
                    await mgr.fan_to_operators(drone_id, raw)
                elif env.type == "signal" and env.signal is not None:
                    # signaling is per-peer: route to the targeted operator only
                    await mgr.send_to_operator(drone_id, env.signal.operator_id, raw)
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
        if not operator:
            # an empty operator id could grab the control lock and block others
            await ws.close(code=status.WS_1008_POLICY_VIOLATION)
            return
        await ws.accept()
        mgr.add_operator(drone_id, ws)
        # register by operator id so the drone can target this peer for signaling
        mgr.register_operator(drone_id, operator, ws)
        pinger = asyncio.create_task(_keepalive(ws, ping_every)) if ping_every > 0 else None
        try:
            while True:
                raw = await ws.receive_text()
                env = Envelope.model_validate_json(raw)
                if env.type == "control" and env.control is not None:
                    await _handle_control(ws, lock, drone_id, env.control)
                elif env.type == "command" and env.command is not None:
                    await _handle_command(ws, mgr, lock, drone_id, operator, raw, env)
                elif env.type == "signal" and env.signal is not None:
                    # operator → drone: forward verbatim (carries operator_id)
                    await mgr.send_to_drone(drone_id, raw)
                elif env.type == "manual" and env.manual is not None:
                    ok, _reason = authorize_manual(
                        holds_lock=lock.holds(drone_id, operator),
                        tier=mgr.tier_for(drone_id),
                    )
                    if ok:
                        await mgr.send_to_drone(drone_id, raw)
                    # unauthorized manual frames are dropped silently (no ack flood)
        except WebSocketDisconnect:
            pass
        finally:
            if pinger is not None:
                # don't await: swallowing CancelledError here would also swallow
                # a cancellation aimed at this handler
                pinger.cancel()
            mgr.remove_operator(drone_id, ws)
            mgr.unregister_operator(drone_id, operator)
            # release the control lock if this operator held it, so a dropped
            # tab/crash doesn't block control for everyone else
            lock.release(drone_id, operator)

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
