"""scada router: telemetry ingestion + retrieval, and the /ws/scada/{plant_id} WebSocket.

HTTP endpoints go through ``router`` (role policy applied in app.py). The WebSocket lives on
``ws_router`` because the HTTP middleware/policies do not run for websocket scopes; the handler
authenticates itself (``?api_key=`` / ``?token=`` / Authorization header) per SOLARDOCTOR_AUTH_MODE.
"""
from __future__ import annotations

import hmac
import os
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, Query, WebSocket, status
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from solardoctor.core.auth import MODE_APIKEY, MODE_USERS, auth_mode
from solardoctor.physics import scada_service
from solardoctor.physics.deps import get_db
from solardoctor.physics.scada_ws import scada_ws_handler
from solardoctor.physics.schemas.scada import ScadaBatchCreate, ScadaReadingCreate, ScadaReadingResponse

router = APIRouter(prefix="/scada", tags=["SCADA"])
ws_router = APIRouter(tags=["SCADA"])


@router.post("/readings", response_model=ScadaReadingResponse, status_code=status.HTTP_201_CREATED,
             summary="Ingest one telemetry reading")
def ingest_reading(data: ScadaReadingCreate, db: Session = Depends(get_db)):
    return scada_service.to_response(scada_service.insert_reading(db, data))


@router.post("/readings/batch", response_model=List[ScadaReadingResponse], status_code=status.HTTP_201_CREATED,
             summary="Ingest a batch of telemetry readings")
def ingest_batch(data: ScadaBatchCreate, db: Session = Depends(get_db)):
    return [scada_service.to_response(r) for r in scada_service.batch_insert_readings(db, data.readings)]


@router.get("/{plant_id}/readings", response_model=List[ScadaReadingResponse],
            summary="Recent telemetry (newest first) or a time range")
def get_readings(plant_id: int, start: Optional[datetime] = None, end: Optional[datetime] = None,
                 limit: int = Query(default=100, ge=1, le=5000), db: Session = Depends(get_db)):
    if start is not None and end is not None:
        rows = scada_service.get_readings_by_range(db, plant_id, start, end, limit=limit)
    else:
        rows = scada_service.get_recent_readings(db, plant_id, limit=limit)
    return [scada_service.to_response(r) for r in rows]


@router.get("/{plant_id}/stats", summary="Basic telemetry statistics for a plant")
def get_stats(plant_id: int, db: Session = Depends(get_db)) -> Dict[str, Optional[float]]:
    return scada_service.get_scada_statistics(db, plant_id)


WS_SUBPROTOCOL_BEARER = "solardoctor.bearer"      # client offers: ["solardoctor.bearer", "<token>"]
WS_SUBPROTOCOL_AUTH_FIRST = "solardoctor.auth-first"  # client sends {"type":"auth","token":...} first
_AUTH_FIRST_TIMEOUT_S = 5.0


def _check_token(token: str) -> bool:
    mode = auth_mode()
    if mode == MODE_APIKEY:
        expected = os.environ.get("SOLARDOCTOR_API_KEY", "").strip()
        return bool(expected) and hmac.compare_digest(token.encode(), expected.encode())
    from solardoctor.api.support.principal import resolve_users_principal
    return bool(token) and resolve_users_principal(token, "") is not None


def _ws_credentials(websocket: WebSocket) -> str:
    """Token from (in order) Authorization header, Sec-WebSocket-Protocol, then the query string.

    Prefer the header or subprotocol: query-string credentials end up in server and proxy access logs.
    """
    bearer = websocket.headers.get("authorization", "")
    if bearer.lower().startswith("bearer "):
        return bearer.split(" ", 1)[1].strip()
    protos = [p.strip() for p in websocket.headers.get("sec-websocket-protocol", "").split(",") if p.strip()]
    if WS_SUBPROTOCOL_BEARER in protos:
        i = protos.index(WS_SUBPROTOCOL_BEARER)
        if i + 1 < len(protos):
            return protos[i + 1]
    return websocket.query_params.get("api_key", "") or websocket.query_params.get("token", "")


@ws_router.websocket("/ws/scada/{plant_id}")
async def scada_websocket(websocket: WebSocket, plant_id: int) -> None:
    """Real-time telemetry stream (DB poll every few seconds) for one plant.

    Auth (when SOLARDOCTOR_AUTH_MODE is apikey/users): Authorization header, subprotocol
    ``solardoctor.bearer, <token>``, a first ``{"type":"auth","token":...}`` message (offer subprotocol
    ``solardoctor.auth-first``), or ``?token=`` / ``?api_key=`` (logged by proxies: avoid).
    """
    import asyncio
    import json as _json

    subprotocol = None
    accepted = False
    if auth_mode() in (MODE_APIKEY, MODE_USERS):
        token = _ws_credentials(websocket)
        offered = [p.strip() for p in websocket.headers.get("sec-websocket-protocol", "").split(",")]
        if token:
            if not await run_in_threadpool(_check_token, token):
                await websocket.close(code=4401, reason="Not authenticated")
                return
            if WS_SUBPROTOCOL_BEARER in offered:
                subprotocol = WS_SUBPROTOCOL_BEARER
        elif WS_SUBPROTOCOL_AUTH_FIRST in offered:
            await websocket.accept(subprotocol=WS_SUBPROTOCOL_AUTH_FIRST)
            accepted = True
            try:
                msg = _json.loads(await asyncio.wait_for(websocket.receive_text(), _AUTH_FIRST_TIMEOUT_S))
                ok = msg.get("type") == "auth" and await run_in_threadpool(_check_token, str(msg.get("token", "")))
            except Exception:
                ok = False
            if not ok:
                await websocket.close(code=4401, reason="Not authenticated")
                return
        else:
            await websocket.close(code=4401, reason="Not authenticated")
            return
    await scada_ws_handler(websocket, plant_id, accepted=accepted, subprotocol=subprotocol)
