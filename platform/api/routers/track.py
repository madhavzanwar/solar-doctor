"""track router — extracted from app.py (Plan 01)."""
from __future__ import annotations

from fastapi import APIRouter
from axalon.api.deps import *  # noqa: F401,F403
from axalon.api.schemas.responses import NoteOut, TrackFileOut
from axalon.api.schemas import LoginRequest, NoteBody, PasswordSetRequest

router = APIRouter(tags=["track"])

@router.post("/track/login")
def track_login(payload: LoginRequest):
    """Verify the /track workspace password. Checks the AXALON_TRACK_PASSWORD env
    override first, then the hash stored in the Supabase `app_config` table.
    The password is never shipped to the frontend bundle."""
    payload = payload.model_dump(exclude_unset=True)
    supplied = str(payload.get("password") or "")
    session = get_session()
    try:
        outcome = verify_track_password(session, supplied)
    finally:
        session.close()
    if outcome == APP_CONFIG_UNCONFIGURED:
        raise HTTPException(status_code=503, detail="Track workspace password not set up yet")
    if outcome != APP_CONFIG_OK:
        raise HTTPException(status_code=401, detail="Wrong password")
    return {"ok": True}


@router.post("/track/password")
def set_track_workspace_password(payload: PasswordSetRequest):
    """Set/rotate the /track password (stored hashed in Supabase). Requires the
    current password unless none is configured yet (first-time setup)."""
    payload = payload.model_dump(exclude_unset=True)
    new_password = str(payload.get("new_password") or "")
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters")
    session = get_session()
    try:
        current = verify_track_password(session, str(payload.get("current_password") or ""))
        if current == APP_CONFIG_WRONG:
            raise HTTPException(status_code=401, detail="Current password is wrong")
        # current == OK or UNCONFIGURED (first-time) both allowed to proceed
        set_track_password(session, new_password)
    finally:
        session.close()
    return {"ok": True}


@router.get("/track/notes", response_model=list[NoteOut])
def list_track_notes(kind: str | None = None):
    session = get_session()
    try:
        q = session.query(TrackNote)
        if kind:
            q = q.filter(TrackNote.kind == kind)
        return [_serialize_note(n) for n in q.order_by(TrackNote.created_at.desc()).all()]
    finally:
        session.close()


@router.post("/track/notes", status_code=201)
def create_track_note(payload: NoteBody):
    payload = payload.model_dump(exclude_unset=True)
    title = str(payload.get("title") or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="title is required")
    kind = str(payload.get("kind") or "other")
    if kind not in NOTE_KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of {NOTE_KINDS}")
    session = get_session()
    try:
        n = TrackNote(
            title=title[:200],
            kind=kind,
            body=payload.get("body"),
            url=payload.get("url"),
            tags=payload.get("tags"),
        )
        session.add(n)
        session.commit()
        session.refresh(n)
        return JSONResponse(content=_serialize_note(n), status_code=201)
    finally:
        session.close()


@router.patch("/track/notes/{note_id}")
def update_track_note(note_id: int, payload: NoteBody):
    payload = payload.model_dump(exclude_unset=True)
    session = get_session()
    try:
        n = session.query(TrackNote).filter_by(id=note_id).first()
        if n is None:
            raise HTTPException(status_code=404, detail="Note not found")
        if "title" in payload:
            title = str(payload.get("title") or "").strip()
            if not title:
                raise HTTPException(status_code=400, detail="title is required")
            n.title = title[:200]
        if "kind" in payload:
            kind = str(payload.get("kind") or "")
            if kind not in NOTE_KINDS:
                raise HTTPException(status_code=400, detail=f"kind must be one of {NOTE_KINDS}")
            n.kind = kind
        for field in ("body", "url", "tags"):
            if field in payload:
                setattr(n, field, payload[field])
        session.commit()
        session.refresh(n)
        return _serialize_note(n)
    finally:
        session.close()


@router.delete("/track/notes/{note_id}", status_code=204)
def delete_track_note(note_id: int):
    session = get_session()
    try:
        n = session.query(TrackNote).filter_by(id=note_id).first()
        if n is None:
            raise HTTPException(status_code=404, detail="Note not found")
        session.delete(n)
        session.commit()
        return Response(status_code=204)
    finally:
        session.close()


@router.get("/track/files", response_model=list[TrackFileOut])
def list_track_files():
    session = get_session()
    try:
        files = session.query(TrackFile).order_by(TrackFile.created_at.desc()).all()
        return [_serialize_track_file(f) for f in files]
    finally:
        session.close()


@router.post("/track/files", status_code=201)
def upload_track_file(file: UploadFile = File(...), label: str = Form(None)):
    """Store a reference file (.stl, .pdf, datasheet, …) in the track library."""
    original = _safe_filename(file.filename, fallback="upload")
    ext = Path(original).suffix.lower()
    if ext not in _TRACK_ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"File type '{ext or 'unknown'}' not allowed",
        )
    stored_name = f"{uuid.uuid4().hex[:12]}_{original}"
    dest = TRACK_FILES_DIR / stored_name

    size = 0
    try:
        with open(dest, "wb") as out:
            while True:
                chunk = file.file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > _MAX_TRACK_FILE_BYTES:
                    raise HTTPException(status_code=413, detail="File exceeds 200 MB limit")
                out.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    except OSError as exc:
        dest.unlink(missing_ok=True)
        logger.error("track file write failed: %s", exc)
        raise HTTPException(status_code=500, detail="Could not store file")

    # Durable storage: push to Supabase Storage when configured (HF disk is
    # ephemeral); the local copy is only a staging buffer in that case.
    store = get_track_store()
    if store is not None:
        try:
            with open(dest, "rb") as staged:
                store.upload(stored_name, staged, file.content_type or "application/octet-stream")
        except RuntimeError as exc:
            dest.unlink(missing_ok=True)
            logger.error("track file object-store upload failed: %s", exc)
            raise HTTPException(status_code=502, detail="Object storage upload failed")
        dest.unlink(missing_ok=True)

    session = get_session()
    try:
        rec = TrackFile(
            original_name=original,
            stored_name=stored_name,
            label=(label or "").strip() or None,
            content_type=file.content_type,
            size_bytes=size,
        )
        session.add(rec)
        session.commit()
        session.refresh(rec)
        return JSONResponse(content=_serialize_track_file(rec), status_code=201)
    finally:
        session.close()


@router.get("/track/files/{file_id}")
def download_track_file(file_id: int):
    session = get_session()
    try:
        rec = session.query(TrackFile).filter_by(id=file_id).first()
        if rec is None:
            raise HTTPException(status_code=404, detail="File not found")
        media_type = rec.content_type or mimetypes.guess_type(rec.original_name)[0] or "application/octet-stream"
        disposition = {"Content-Disposition": f'attachment; filename="{rec.original_name}"'}

        store = get_track_store()
        if store is not None:
            chunks = store.download(rec.stored_name)
            if chunks is not None:
                return StreamingResponse(chunks, media_type=media_type, headers=disposition)
            # fall through: object may predate the storage move and live on disk

        path = TRACK_FILES_DIR / rec.stored_name
        if not path.exists():
            raise HTTPException(status_code=404, detail="File missing from storage")
        return FileResponse(path, media_type=media_type, filename=rec.original_name)
    finally:
        session.close()


@router.delete("/track/files/{file_id}", status_code=204)
def delete_track_file(file_id: int):
    session = get_session()
    try:
        rec = session.query(TrackFile).filter_by(id=file_id).first()
        if rec is None:
            raise HTTPException(status_code=404, detail="File not found")
        store = get_track_store()
        if store is not None:
            try:
                store.delete(rec.stored_name)
            except RuntimeError as exc:
                logger.error("track file object-store delete failed: %s", exc)
                raise HTTPException(status_code=502, detail="Object storage delete failed")
        (TRACK_FILES_DIR / rec.stored_name).unlink(missing_ok=True)
        session.delete(rec)
        session.commit()
        return Response(status_code=204)
    finally:
        session.close()
