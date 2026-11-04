"""projects router — extracted from app.py (Plan 01)."""
from __future__ import annotations

from fastapi import APIRouter
from axalon.api.deps import *  # noqa: F401,F403
from axalon.api.schemas.responses import ProjectOut
from axalon.api.schemas import ProjectBody
from axalon.db.models import ProjectMember, ShareLink

router = APIRouter(tags=["projects"])

@router.get("/projects", response_model=list[ProjectOut])
def list_projects(principal: Principal = Depends(current_principal)):
    session = get_session()
    try:
        projects = scope_projects(session.query(Project), principal).order_by(Project.created_at.desc()).all()
        out = []
        for p in projects:
            row = _serialize_project(p)
            row["site_count"] = session.query(Park).filter(Park.project_id == p.id).count()
            out.append(row)
        return out
    finally:
        session.close()


@router.post("/projects", status_code=201)
def create_project(payload: ProjectBody):
    payload = payload.model_dump(exclude_unset=True)
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    status = str(payload.get("status") or "active")
    if status not in PROJECT_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {PROJECT_STATUSES}")
    session = get_session()
    try:
        p = Project(
            name=name[:200],
            client=payload.get("client"),
            description=payload.get("description"),
            status=status,
        )
        session.add(p)
        session.commit()
        session.refresh(p)
        return JSONResponse(content=_serialize_project(p), status_code=201)
    finally:
        session.close()


@router.get("/projects/{project_id}", response_model=ProjectOut)
def get_project(project_id: int, principal: Principal = Depends(current_principal)):
    """Project detail with its sites (parks) and per-site mission/inspection counts."""
    session = get_session()
    try:
        p = session.query(Project).filter_by(id=project_id).first()
        if p is None or not principal.can_see_project(p.id):
            raise HTTPException(status_code=404, detail="Project not found")
        detail = _serialize_project(p)
        detail["sites"] = _project_sites(session, p.id)
        return detail
    finally:
        session.close()


@router.patch("/projects/{project_id}")
def update_project(project_id: int, payload: ProjectBody):
    payload = payload.model_dump(exclude_unset=True)
    session = get_session()
    try:
        p = session.query(Project).filter_by(id=project_id).first()
        if p is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if "name" in payload:
            name = str(payload.get("name") or "").strip()
            if not name:
                raise HTTPException(status_code=400, detail="name is required")
            p.name = name[:200]
        if "status" in payload:
            status = str(payload.get("status") or "")
            if status not in PROJECT_STATUSES:
                raise HTTPException(status_code=400, detail=f"status must be one of {PROJECT_STATUSES}")
            p.status = status
        for field in ("client", "description"):
            if field in payload:
                setattr(p, field, payload[field])
        session.commit()
        session.refresh(p)
        return _serialize_project(p)
    finally:
        session.close()


@router.delete("/projects/{project_id}", status_code=204)
def delete_project(project_id: int):
    """Delete a project; its parks remain but are unassigned."""
    session = get_session()
    try:
        p = session.query(Project).filter_by(id=project_id).first()
        if p is None:
            raise HTTPException(status_code=404, detail="Project not found")
        session.query(Park).filter(Park.project_id == project_id).update(
            {Park.project_id: None}, synchronize_session=False
        )
        # Access grants and share links die with the project (explicit, since
        # SQLite only honours ON DELETE CASCADE with foreign_keys enabled).
        session.query(ProjectMember).filter(ProjectMember.project_id == project_id).delete(
            synchronize_session=False
        )
        session.query(ShareLink).filter(ShareLink.project_id == project_id).delete(
            synchronize_session=False
        )
        session.delete(p)
        session.commit()
        return Response(status_code=204)
    finally:
        session.close()
