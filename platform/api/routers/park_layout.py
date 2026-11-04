"""park layout router — manual panel layouts for parks auto-grid cannot fit.

Storage lives in axalon.park.manual_layout (app_config key/value row), so the
same code path works on SQLite locally and PostgreSQL in production.
"""
from __future__ import annotations

from fastapi import APIRouter
from axalon.api.deps import *  # noqa: F401,F403
from axalon.park.manual_layout import (
    LayoutError,
    delete_park_layout,
    load_park_layout_doc,
    parse_layout,
    parse_layout_upload,
    save_park_layout,
)

router = APIRouter(tags=["park"])

_MAX_LAYOUT_BYTES = 20 * 1024 * 1024  # ~100k polygon panels as GeoJSON


@router.get("/park/{park_id}/layout")
def get_park_layout(park_id: str, full: bool = False, principal: Principal = Depends(current_principal)):
    """Whether the park uses a manual layout (and its summary) or auto-grid."""
    park_id = _validate_park_id(park_id)
    ensure_park_visible(principal, park_id)
    session = get_session()
    try:
        doc = load_park_layout_doc(session, park_id)
    finally:
        session.close()
    if doc is None:
        return {"park_id": park_id, "mode": "auto", "summary": None, "layout": None, "error": None}
    try:
        summary = parse_layout(doc, park_id).summary()
        error = None
    except LayoutError as exc:
        # Stored layout no longer validates: surface it, batches will refuse it.
        summary, error = None, str(exc)
    return {
        "park_id": park_id,
        "mode": "manual",
        "summary": summary,
        "layout": doc if full else None,
        "error": error,
    }


@router.post("/park/{park_id}/layout", status_code=201)
async def upload_park_layout(
    park_id: str,
    file: UploadFile = File(..., description="Layout JSON (axalon-park-layout) or GeoJSON FeatureCollection"),
    principal: Principal = Depends(current_principal),
):
    """Validate and store a manual layout; replaces any existing one."""
    park_id = _validate_park_id(park_id)
    ensure_park_visible(principal, park_id)
    payload = await file.read(_MAX_LAYOUT_BYTES + 1)
    if len(payload) > _MAX_LAYOUT_BYTES:
        raise HTTPException(413, "Layout file exceeds 20 MB")
    try:
        doc, _ = parse_layout_upload(payload, park_id)
    except LayoutError as exc:
        raise HTTPException(400, f"Invalid layout: {exc}")

    session = get_session()
    try:
        layout = save_park_layout(session, park_id, doc)
    finally:
        session.close()
    return {"park_id": park_id, "mode": "manual", "summary": layout.summary()}


@router.delete("/park/{park_id}/layout")
def remove_park_layout(park_id: str, principal: Principal = Depends(current_principal)):
    """Drop the manual layout so the park falls back to auto-grid."""
    park_id = _validate_park_id(park_id)
    ensure_park_visible(principal, park_id)
    session = get_session()
    try:
        deleted = delete_park_layout(session, park_id)
    finally:
        session.close()
    if not deleted:
        raise HTTPException(404, f"No manual layout stored for park {park_id!r}")
    return {"park_id": park_id, "mode": "auto", "deleted": True}
