"""corrections router — extracted from app.py (Plan 01)."""
from __future__ import annotations

from fastapi import APIRouter
from axalon.api.deps import *  # noqa: F401,F403
from axalon.api.schemas.responses import CorrectionOut
from axalon.api.schemas import CorrectionCreate

router = APIRouter(tags=["corrections"])

@router.get("/corrections/{job_id:path}", response_model=list[CorrectionOut])
def list_corrections(job_id: str, principal: Principal = Depends(current_principal)):
    """List all user correction boxes for an inspect job."""
    job_id = _validate_job_id(job_id)
    ensure_job_visible(principal, job_id)
    session = get_session()
    try:
        rows = (
            session.query(Correction)
            .filter(Correction.job_id == job_id)
            .order_by(Correction.created_at.asc(), Correction.id.asc())
            .all()
        )
        return [_serialize_correction(r) for r in rows]
    finally:
        session.close()


@router.post("/corrections/{job_id}", status_code=201)
def create_correction(job_id: str, body: CorrectionCreate, principal: Principal = Depends(current_principal)):
    """Persist a user-drawn bounding box correction."""
    body = body.model_dump(exclude_unset=True)
    job_id = _validate_job_id(job_id)
    ensure_job_visible(principal, job_id)
    class_ = str(body.get("class_", ""))[:64]
    if not class_:
        raise HTTPException(status_code=400, detail="class_ is required")

    bbox = body.get("bbox_norm")
    if not isinstance(bbox, list) or len(bbox) != 4:
        raise HTTPException(status_code=400, detail="bbox_norm must contain four values")
    try:
        bbox = [max(0.0, min(1.0, float(v))) for v in bbox]
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="bbox_norm values must be numeric")

    raw_class_id = body.get("class_id")
    class_id = int(raw_class_id) if raw_class_id is not None else None
    severity = str(body.get("severity", "MEDIUM"))[:16]
    notes = str(body.get("notes", ""))[:500] if body.get("notes") else None
    session = get_session()
    try:
        c = Correction(
            job_id=job_id,
            image_id=str(body.get("image_id", ""))[:160] if body.get("image_id") else None,
            panel_id=str(body.get("panel_id", ""))[:64] if body.get("panel_id") else None,
            class_=class_,
            class_id=class_id,
            severity=severity,
            bbox_norm=json.dumps(bbox),
            notes=notes,
        )
        session.add(c)
        session.commit()
        session.refresh(c)
        return JSONResponse(content=_serialize_correction(c), status_code=201)
    finally:
        session.close()


@router.delete("/corrections/{job_id}/{correction_id}", status_code=204)
def delete_correction(job_id: str, correction_id: int, principal: Principal = Depends(current_principal)):
    """Delete a user correction by ID."""
    job_id = _validate_job_id(job_id)
    ensure_job_visible(principal, job_id, detail="Correction not found")
    session = get_session()
    try:
        c = session.query(Correction).filter(
            Correction.id == correction_id,
            Correction.job_id == job_id,
        ).first()
        if c is None:
            raise HTTPException(status_code=404, detail="Correction not found")
        session.delete(c)
        session.commit()
        return Response(status_code=204)
    finally:
        session.close()
