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


def _ws_authorised(websocket: WebSocket) -> bool:
    mode = auth_mode()
    if mode not in (MODE_APIKEY, MODE_USERS):
        return True
    bearer = websocket.headers.get("authorization", "")
    token = (bearer.split(" ", 1)[1].strip() if bearer.lower().startswith("bearer ") else "") \
        or websocket.query_params.get("api_key", "") or websocket.query_params.get("token", "")
    if mode == MODE_APIKEY:
        expected = os.environ.get("SOLARDOCTOR_API_KEY", "").strip()
        return bool(expected) and hmac.compare_digest(token.encode(), expected.encode())
    from solardoctor.api.support.principal import resolve_users_principal
    return resolve_users_principal(token, "") is not None


@ws_router.websocket("/ws/scada/{plant_id}")
async def scada_websocket(websocket: WebSocket, plant_id: int) -> None:
    """Real-time telemetry stream (DB poll every few seconds) for one plant."""
    if not await run_in_threadpool(_ws_authorised, websocket):
        await websocket.close(code=4401, reason="Not authenticated")
        return
    await scada_ws_handler(websocket, plant_id)
