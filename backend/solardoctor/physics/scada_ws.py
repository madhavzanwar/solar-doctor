# Adapted from SolarPulseAI app/api/websockets/scada_ws.py
# (https://github.com/anugrahpatil-creator/SolarPulseAI), MIT License,
# Copyright (c) 2026 anugrahpatil-creator. See THIRD_PARTY_NOTICES.md.
# Modified for SolarDoctor: sync SQLAlchemy via threadpool; telemetry table; honest frame labels.
"""WebSocket ``/api/v1/ws/scada/{plant_id}``: streams the latest telemetry row every few seconds.

The stream is a DB poll (not a push from a field gateway); frames carry ``_source``:
``stream_init`` (handshake), ``database_poll`` (latest stored telemetry), ``no_data``.
"""
from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone

from fastapi import WebSocket, WebSocketDisconnect
from sqlalchemy import select
from starlette.concurrency import run_in_threadpool

from solardoctor.db.session import get_session
from solardoctor.physics.models import Plant, Telemetry

logger = logging.getLogger("solardoctor.physics.scada_ws")

POLL_INTERVAL_SECONDS = 5.0


def _plant_exists(plant_id: int) -> bool:
    session = get_session()
    try:
        return session.execute(select(Plant.id).where(Plant.id == plant_id)).scalar_one_or_none() is not None
    finally:
        session.close()


def _latest_frame(plant_id: int) -> dict | None:
    session = get_session()
    try:
        t = session.execute(
            select(Telemetry).where(Telemetry.plant_id == plant_id).order_by(Telemetry.ts.desc()).limit(1)
        ).scalar_one_or_none()
        if t is None:
            return None
        return {
            "plant_id": t.plant_id,
            "timestamp": t.ts.isoformat(),
            "power_kw": t.p_ac_kw,
            "irradiance_w_m2": t.ghi_wm2,
            "temperature_c": t.t_amb,
            "wind_speed_m_s": t.wind_ms,
            "module_temperature_c": t.t_mod,
            "inverter_power_kw": t.p_ac_kw,
            "expected_power_kw": t.p_expected_kw,
            "data_source": t.source,
            "_source": "database_poll",
        }
    finally:
        session.close()


async def scada_ws_handler(websocket: WebSocket, plant_id: int, poll_interval: float | None = None) -> None:
    interval = POLL_INTERVAL_SECONDS if poll_interval is None else poll_interval
    if not await run_in_threadpool(_plant_exists, plant_id):
        await websocket.close(code=4004, reason=f"Plant {plant_id} not found")
        return
    await websocket.accept()
    await websocket.send_text(json.dumps({
        "plant_id": plant_id, "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "status": "connected", "power_kw": 0.0, "_source": "stream_init",
    }))
    try:
        while True:
            await asyncio.sleep(interval)
            data = await run_in_threadpool(_latest_frame, plant_id)
            if data is None:
                data = {"plant_id": plant_id, "timestamp": datetime.now(tz=timezone.utc).isoformat(),
                        "message": "No SCADA data available yet", "_source": "no_data"}
            await websocket.send_text(json.dumps(data))
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: plant_id=%s", plant_id)
    except Exception as exc:
        logger.warning("WebSocket error: plant_id=%s error=%s", plant_id, exc)
