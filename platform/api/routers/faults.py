"""faults router — fault listing, repair workflow updates, comments, proof photos."""
from __future__ import annotations

import io
from datetime import date

from fastapi import APIRouter
from sqlalchemy import func

from axalon.api.deps import *  # noqa: F401,F403
from axalon.api.schemas.responses import CommentOut, FaultOut, FaultPhotoOut, FaultsListOut
from axalon.api.schemas import CommentCreate, FaultUpdate
from axalon.api.serializers import _serialize_fault_photo
from axalon.core.fault_workflow import (
    PRIORITY_LEVELS,
    WorkflowError,
    apply_status,
    check_ownership,
)

router = APIRouter(tags=["faults"])

_MAX_FAULT_PHOTO_BYTES = 15 * 1024 * 1024  # 15 MB — phone photos, not orthos
_MAX_ASSIGNEE_LEN = 200
_MAX_RESOLUTION_NOTE_LEN = 4000

# content-type → (accepted extensions, magic-byte check). The declared type,
# the filename extension and the file's leading bytes must all agree.
_PHOTO_TYPES: dict[str, tuple[set[str], callable]] = {
    "image/jpeg": ({".jpg", ".jpeg"}, lambda b: b.startswith(b"\xff\xd8\xff")),
    "image/png": ({".png"}, lambda b: b.startswith(b"\x89PNG\r\n\x1a\n")),
    "image/webp": ({".webp"}, lambda b: b[:4] == b"RIFF" and b[8:12] == b"WEBP"),
}


def _require_positive(fault_id: int) -> None:
    if fault_id <= 0:
        raise HTTPException(status_code=400, detail="fault_id must be positive")


def _get_fault_or_404(session, fault_id: int) -> PanelFault:
    fault = session.query(PanelFault).filter_by(id=fault_id).first()
    if fault is None:
        raise HTTPException(status_code=404, detail="Fault not found")
    return fault


def _counts_by_fault(session, model, fault_ids: list[int]) -> dict[int, int]:
    if not fault_ids:
        return {}
    return dict(
        session.query(model.fault_id, func.count(model.id))
        .filter(model.fault_id.in_(fault_ids))
        .group_by(model.fault_id)
        .all()
    )


def _serialize_with_counts(session, fault: PanelFault) -> dict:
    return _serialize_fault(
        fault,
        _counts_by_fault(session, FaultComment, [fault.id]).get(fault.id, 0),
        _counts_by_fault(session, FaultPhoto, [fault.id]).get(fault.id, 0),
    )


@router.get("/parks/{park_id}/faults", response_model=FaultsListOut)
def list_park_faults(
    park_id: str, status: str | None = None, principal: Principal = Depends(current_principal),
):
    """List tracked faults for a park, optionally filtered by status."""
    park_id = _validate_park_id(park_id)
    ensure_park_visible(principal, park_id)
    if status is not None and status not in _ALLOWED_FAULT_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Allowed: {', '.join(FAULT_STATUSES)}",
        )
    session = get_session()
    try:
        q = session.query(PanelFault).filter(PanelFault.park_id == park_id)
        if status:
            q = q.filter(PanelFault.status == status)
        # Worst severity first, then most-recently-seen.
        faults = q.order_by(
            PanelFault.severity.desc(), PanelFault.last_seen_date.desc()
        ).all()
        counts = {s: 0 for s in FAULT_STATUSES}
        for f in faults:
            if f.status in counts:
                counts[f.status] += 1
        ids = [f.id for f in faults]
        comment_counts = _counts_by_fault(session, FaultComment, ids)
        photo_counts = _counts_by_fault(session, FaultPhoto, ids)
        return {
            "park_id": park_id,
            "total": len(faults),
            "counts_by_status": counts,
            "faults": [
                _serialize_fault(f, comment_counts.get(f.id, 0), photo_counts.get(f.id, 0))
                for f in faults
            ],
        }
    finally:
        session.close()


def _parse_due_date(raw: str | None) -> date | None:
    if raw is None or not str(raw).strip():
        return None
    try:
        return date.fromisoformat(str(raw).strip())
    except ValueError:
        raise HTTPException(status_code=400, detail="due_date must be an ISO date (YYYY-MM-DD)")


def _parse_priority(raw: str | None) -> str | None:
    if raw is None or not str(raw).strip():
        return None
    value = str(raw).strip().lower()
    if value not in PRIORITY_LEVELS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid priority. Allowed: {', '.join(PRIORITY_LEVELS)}",
        )
    return value


def _apply_fields(fault: PanelFault, payload: dict) -> None:
    """Copy the non-status fields of a FaultUpdate onto the fault."""
    if "notes" in payload and payload["notes"] is not None:
        fault.notes = str(payload["notes"])[:2000]
    if "assignee" in payload:
        fault.assignee = (str(payload["assignee"] or "").strip()[:_MAX_ASSIGNEE_LEN]) or None
    if "due_date" in payload:
        fault.due_date = _parse_due_date(payload["due_date"])
    if "priority" in payload:
        fault.priority = _parse_priority(payload["priority"])
    if "resolution_note" in payload:
        note = str(payload["resolution_note"] or "").strip()
        fault.resolution_note = note[:_MAX_RESOLUTION_NOTE_LEN] or None


@router.patch("/faults/{fault_id}", response_model=FaultOut)
def update_fault(fault_id: int, payload: FaultUpdate, principal: Principal = Depends(current_principal)):
    """Update a fault's workflow: status, assignee, due date, priority, notes.

    Unknown values → 400; transitions or ownership rules that don't hold → 422.
    """
    payload = payload.model_dump(exclude_unset=True)
    _require_positive(fault_id)
    new_status = payload.get("status")
    if new_status is not None and new_status not in _ALLOWED_FAULT_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Allowed: {', '.join(FAULT_STATUSES)}",
        )
    session = get_session()
    try:
        fault = _get_fault_or_404(session, fault_id)
        ensure_fault_visible(principal, fault_id, session)
        _apply_fields(fault, payload)
        try:
            if new_status:
                apply_status(fault, new_status)
            check_ownership(fault)
        except WorkflowError as exc:
            session.rollback()
            raise HTTPException(status_code=422, detail=str(exc))
        session.commit()
        return _serialize_with_counts(session, fault)
    finally:
        session.close()


@router.post("/faults/{fault_id}/comments", status_code=201)
def create_fault_comment(fault_id: int, body: CommentCreate, principal: Principal = Depends(current_principal)):
    """Append a comment to a fault's thread."""
    body = body.model_dump(exclude_unset=True)
    _require_positive(fault_id)
    comment_body = str(body.get("body", "")).strip()
    if not comment_body:
        raise HTTPException(status_code=400, detail="body is required")
    author = str(body.get("author", ""))[:128] if body.get("author") else None
    session = get_session()
    try:
        _get_fault_or_404(session, fault_id)
        ensure_fault_visible(principal, fault_id, session)
        comment = FaultComment(
            fault_id=fault_id,
            author=author,
            body=comment_body[:4000],
        )
        session.add(comment)
        session.commit()
        session.refresh(comment)
        return JSONResponse(content=_serialize_comment(comment), status_code=201)
    finally:
        session.close()


@router.get("/faults/{fault_id}/comments", response_model=list[CommentOut])
def list_fault_comments(fault_id: int, principal: Principal = Depends(current_principal)):
    """List all comments on a fault in chronological order."""
    _require_positive(fault_id)
    session = get_session()
    try:
        ensure_fault_visible(principal, fault_id, session)
        comments = (
            session.query(FaultComment)
            .filter(FaultComment.fault_id == fault_id)
            .order_by(FaultComment.created_at.asc(), FaultComment.id.asc())
            .all()
        )
        return [_serialize_comment(c) for c in comments]
    finally:
        session.close()


# ── Repair proof photos ───────────────────────────────────────────────────────

def _read_validated_photo(file: UploadFile) -> tuple[bytes, str, str]:
    """Return (content, sanitized filename, content type) or raise 413/415."""
    content_type = (file.content_type or "").split(";")[0].strip().lower()
    spec = _PHOTO_TYPES.get(content_type)
    if spec is None:
        raise HTTPException(
            status_code=415,
            detail=f"Photo must be one of: {', '.join(_PHOTO_TYPES)}",
        )
    extensions, looks_valid = spec
    # Basename only, then header-safe characters (it is echoed in Content-Disposition).
    original = re.sub(r"[^A-Za-z0-9._ -]", "_", _safe_filename(file.filename, fallback="photo"))[:160]
    if Path(original).suffix.lower() not in extensions:
        original = f"{Path(original).stem or 'photo'}{sorted(extensions)[0]}"

    content = file.file.read(_MAX_FAULT_PHOTO_BYTES + 1)
    if len(content) > _MAX_FAULT_PHOTO_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"Photo exceeds {_MAX_FAULT_PHOTO_BYTES // (1024 * 1024)} MB limit",
        )
    if not content or not looks_valid(content):
        raise HTTPException(status_code=415, detail="File content is not a valid image")
    return content, original, content_type


def _local_photo_path(stored_name: str) -> Path:
    # stored_name is server-generated ("fault-photos/<id>/<uuid>_<safe name>"),
    # but resolve and confine it anyway.
    root = Path(FAULT_PHOTOS_DIR).resolve()
    path = (root / stored_name.removeprefix("fault-photos/")).resolve()
    path.relative_to(root)
    return path


@router.post("/faults/{fault_id}/photos", status_code=201, response_model=FaultPhotoOut)
def upload_fault_photo(
    fault_id: int, file: UploadFile = File(...), principal: Principal = Depends(current_principal),
):
    """Attach a repair proof photo (JPEG/PNG/WebP, ≤ 15 MB) to a fault."""
    _require_positive(fault_id)
    session = get_session()
    try:
        _get_fault_or_404(session, fault_id)
        ensure_fault_visible(principal, fault_id, session)
        content, original, content_type = _read_validated_photo(file)
        stored_name = f"fault-photos/{fault_id}/{uuid.uuid4().hex[:12]}_{original}"

        store = get_track_store()
        try:
            if store is not None:
                store.upload(stored_name, io.BytesIO(content), content_type)
            else:
                dest = _local_photo_path(stored_name)
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(content)
        except (RuntimeError, OSError) as exc:
            logger.error("fault photo storage failed: %s", exc)
            raise HTTPException(status_code=502, detail="Photo storage failed")

        photo = FaultPhoto(
            fault_id=fault_id,
            original_name=original,
            stored_name=stored_name,
            content_type=content_type,
            size_bytes=len(content),
        )
        session.add(photo)
        session.commit()
        session.refresh(photo)
        return JSONResponse(content=_serialize_fault_photo(photo), status_code=201)
    finally:
        session.close()


@router.get("/faults/{fault_id}/photos", response_model=list[FaultPhotoOut])
def list_fault_photos(fault_id: int, principal: Principal = Depends(current_principal)):
    _require_positive(fault_id)
    session = get_session()
    try:
        _get_fault_or_404(session, fault_id)
        ensure_fault_visible(principal, fault_id, session)
        photos = (
            session.query(FaultPhoto)
            .filter(FaultPhoto.fault_id == fault_id)
            .order_by(FaultPhoto.created_at.asc(), FaultPhoto.id.asc())
            .all()
        )
        return [_serialize_fault_photo(p) for p in photos]
    finally:
        session.close()


def _get_photo_or_404(session, fault_id: int, photo_id: int) -> FaultPhoto:
    photo = session.query(FaultPhoto).filter_by(id=photo_id, fault_id=fault_id).first()
    if photo is None:
        raise HTTPException(status_code=404, detail="Photo not found")
    return photo


@router.get("/faults/{fault_id}/photos/{photo_id}")
def get_fault_photo(fault_id: int, photo_id: int, principal: Principal = Depends(current_principal)):
    """Serve a proof photo inline (only types validated at upload are ever served)."""
    session = get_session()
    try:
        ensure_fault_visible(principal, fault_id, session)
        photo = _get_photo_or_404(session, fault_id, photo_id)
        headers = {
            "Content-Disposition": f'inline; filename="{photo.original_name}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=3600",
        }
        store = get_track_store()
        if store is not None:
            chunks = store.download(photo.stored_name)
            if chunks is None:
                raise HTTPException(status_code=404, detail="Photo missing from storage")
            return StreamingResponse(chunks, media_type=photo.content_type, headers=headers)
        path = _local_photo_path(photo.stored_name)
        if not path.exists():
            raise HTTPException(status_code=404, detail="Photo missing from storage")
        return FileResponse(path, media_type=photo.content_type, headers=headers)
    finally:
        session.close()


@router.delete("/faults/{fault_id}/photos/{photo_id}", status_code=204)
def delete_fault_photo(fault_id: int, photo_id: int, principal: Principal = Depends(current_principal)):
    session = get_session()
    try:
        ensure_fault_visible(principal, fault_id, session)
        photo = _get_photo_or_404(session, fault_id, photo_id)
        store = get_track_store()
        try:
            if store is not None:
                store.delete(photo.stored_name)
            else:
                _local_photo_path(photo.stored_name).unlink(missing_ok=True)
        except RuntimeError as exc:
            logger.error("fault photo delete failed: %s", exc)
            raise HTTPException(status_code=502, detail="Photo storage delete failed")
        session.delete(photo)
        session.commit()
        return Response(status_code=204)
    finally:
        session.close()
