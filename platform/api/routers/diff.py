"""diff router — extracted from app.py (Plan 01)."""
from __future__ import annotations

from fastapi import APIRouter
from axalon.api.deps import *  # noqa: F401,F403
from axalon.api.schemas.responses import InspectionDiffOut

router = APIRouter(tags=["diff"])

@router.get("/parks/{park_id}/inspections/{a}/diff/{b}", response_model=InspectionDiffOut)
def diff_inspections(park_id: str, a: str, b: str, principal: Principal = Depends(current_principal)):
    """Compare two inspections of the same park.

    Returns three lists keyed by (panel_id, class):
      - new:        present in B, absent in A
      - recurring:  present in both
      - resolved:   present in A, absent in B
    """
    park_id = _validate_park_id(park_id)
    a = _validate_job_id(a)
    b = _validate_job_id(b)
    session = get_session()
    try:
        ensure_park_visible(principal, park_id, session)
        for insp_id in (a, b):
            if session.query(Inspection).filter_by(id=insp_id, park_id=park_id).first() is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Inspection {insp_id} not found for park {park_id}",
                )

        def _keys(insp_id: str) -> set[tuple[str, str]]:
            rows = (
                session.query(DbDetection.panel_id, DbDetection.class_)
                .filter(DbDetection.inspection_id == insp_id)
                .distinct()
                .all()
            )
            return {(r[0] or "R?-C?", r[1] or "") for r in rows if r[1]}

        keys_a, keys_b = _keys(a), _keys(b)

        def _shape(keys: set[tuple[str, str]]) -> list[dict]:
            return [{"panel_id": p, "class": c} for p, c in sorted(keys)]

        return {
            "park_id": park_id,
            "from": a,
            "to": b,
            "new": _shape(keys_b - keys_a),
            "recurring": _shape(keys_a & keys_b),
            "resolved": _shape(keys_a - keys_b),
            "counts": {
                "new": len(keys_b - keys_a),
                "recurring": len(keys_a & keys_b),
                "resolved": len(keys_a - keys_b),
            },
        }
    finally:
        session.close()
