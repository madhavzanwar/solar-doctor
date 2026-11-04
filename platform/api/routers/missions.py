"""missions router — extracted from app.py (Plan 01)."""
from __future__ import annotations

from fastapi import APIRouter
from axalon.api.deps import *  # noqa: F401,F403
from axalon.api.schemas.responses import MissionFullOut, MissionSummaryOut
from axalon.api.schemas import MissionCreate

router = APIRouter(tags=["missions"])

@router.post("/missions", status_code=201)
def create_mission(payload: MissionCreate, principal: Principal = Depends(current_principal)):
    """Save a planned mission."""
    payload = payload.model_dump(exclude_unset=True)
    name = str(payload.get("name", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    session = get_session()
    try:
        # Scoped users must attach missions to a park they can see, otherwise
        # the saved mission would immediately be invisible to them.
        ensure_park_visible(principal, payload.get("park_id") or None, session)
        m = Mission(
            name=name[:200],
            park_id=(payload.get("park_id") or None),
            mission_type=payload.get("mission_type", "grid"),
            camera_id=payload.get("camera_id"),
            params=json.dumps(payload.get("params") or {}),
            polygon=json.dumps(payload.get("polygon") or []),
            waypoints=json.dumps(payload.get("waypoints") or []),
            area_ha=payload.get("area_ha"),
            image_count=payload.get("image_count"),
        )
        session.add(m)
        session.commit()
        session.refresh(m)
        return JSONResponse(content=_serialize_mission_summary(m), status_code=201)
    finally:
        session.close()


@router.get("/missions", response_model=list[MissionSummaryOut])
def list_missions(park_id: str | None = None, principal: Principal = Depends(current_principal)):
    """List saved missions, optionally filtered by park_id. Excludes heavy waypoint payloads."""
    session = get_session()
    try:
        q = scope_missions(session, session.query(Mission), principal)
        if park_id:
            q = q.filter(Mission.park_id == park_id)
        missions = q.order_by(Mission.created_at.desc()).all()
        return [_serialize_mission_summary(m) for m in missions]
    finally:
        session.close()


@router.get("/missions/{mission_id}", response_model=MissionFullOut)
def get_mission(mission_id: int, principal: Principal = Depends(current_principal)):
    """Return one mission including its full waypoint path."""
    session = get_session()
    try:
        m = session.query(Mission).filter_by(id=mission_id).first()
        if m is None or not park_is_visible(session, principal, m.park_id):
            raise HTTPException(status_code=404, detail="Mission not found")
        return _serialize_mission_full(m)
    finally:
        session.close()


@router.delete("/missions/{mission_id}", status_code=204)
def delete_mission(mission_id: int, principal: Principal = Depends(current_principal)):
    """Delete a saved mission."""
    session = get_session()
    try:
        m = session.query(Mission).filter_by(id=mission_id).first()
        if m is None or not park_is_visible(session, principal, m.park_id):
            raise HTTPException(status_code=404, detail="Mission not found")
        session.delete(m)
        session.commit()
        return Response(status_code=204)
    finally:
        session.close()
