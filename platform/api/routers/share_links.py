"""share_links router — read-only, expiring, revocable project links (users mode).

Mounted operator+ in app.py. Operators manage links only for projects they
belong to; admins for any project.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter
from axalon.api.deps import *  # noqa: F401,F403
from axalon.api.schemas import ShareLinkCreate
from axalon.api.serializers import _serialize_share_link
from axalon.api.support.principal import KIND_USER
from axalon.core.auth import AuthValidationError, create_share_link
from axalon.db.models import ShareLink

router = APIRouter(tags=["share-links"])

_NOT_FOUND = "Share link not found"


@router.get("/share-links")
def list_share_links(principal: Principal = Depends(current_principal)):
    session = get_session()
    try:
        q = session.query(ShareLink)
        if principal.is_restricted:
            q = q.filter(ShareLink.project_id.in_(sorted(principal.project_ids)))
        now = datetime.utcnow()
        return [_serialize_share_link(link, now) for link in q.order_by(ShareLink.created_at.desc()).all()]
    finally:
        session.close()


@router.post("/share-links", status_code=201)
def create_link(payload: ShareLinkCreate, principal: Principal = Depends(current_principal)):
    """Create a link; the plaintext token is in this response and nowhere else."""
    data = payload.model_dump()
    project_id = data.get("project_id")
    session = get_session()
    try:
        ensure_project_visible(principal, project_id)
        if project_id is None or session.query(Project.id).filter(Project.id == project_id).first() is None:
            raise HTTPException(status_code=404, detail="Project not found")
        try:
            link, token = create_share_link(
                session,
                project_id=project_id,
                created_by=principal.user_id if principal.kind == KIND_USER else None,
                expires_in_days=data.get("expires_in_days"),
                label=data.get("label"),
            )
        except AuthValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        return JSONResponse(content={**_serialize_share_link(link), "token": token}, status_code=201)
    finally:
        session.close()


@router.delete("/share-links/{link_id}", status_code=204)
def revoke_link(link_id: int, principal: Principal = Depends(current_principal)):
    """Revoke (idempotent). The row is kept so the audit trail survives."""
    session = get_session()
    try:
        link = session.query(ShareLink).filter(ShareLink.id == link_id).first()
        if link is None or not principal.can_see_project(link.project_id):
            raise HTTPException(status_code=404, detail=_NOT_FOUND)
        if link.revoked_at is None:
            link.revoked_at = datetime.utcnow()
            session.commit()
        return Response(status_code=204)
    finally:
        session.close()
