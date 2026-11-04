"""serializers.py — ORM-object → dict serializers and small request helpers.

Extracted from deps.py (Plan 01 size split). Self-contained: imports models
directly so there is no circular dependency with deps.py.
"""
from __future__ import annotations

import json

from fastapi import HTTPException

from axalon.core.fault_workflow import effective_priority
from axalon.core.temp_extractor import TEMP_FIELDS
from axalon.db.models import *  # noqa: F401,F403

__all__ = [
    "_serialize_correction", "_serialize_fault", "_serialize_comment", "_serialize_fault_photo",
    "_serialize_mission_summary", "_serialize_mission_full", "_assigned_qty",
    "_serialize_component", "_serialize_assignment", "_serialize_prototype",
    "_serialize_order", "_clean_name", "_non_negative_int", "_serialize_project",
    "_project_sites", "_serialize_note", "_serialize_track_file",
    "_serialize_detection_temps",
    "_serialize_user", "_serialize_share_link",
]


def _serialize_detection_temps(d) -> dict:
    """Temperature fields of a Detection row (or detection dict), all nullable.

    Every key is always present so the UI can distinguish "no radiometric data"
    (None) from a missing field.
    """
    get = d.get if isinstance(d, dict) else (lambda k: getattr(d, k, None))
    return {field: get(field) for field in TEMP_FIELDS}


def _serialize_correction(c: Correction) -> dict:
    return {
        "id": c.id,
        "job_id": c.job_id,
        "image_id": c.image_id,
        "panel_id": c.panel_id,
        "class": c.class_,
        "class_id": c.class_id,
        "severity": c.severity,
        "bbox_norm": json.loads(c.bbox_norm) if c.bbox_norm else [],
        "notes": c.notes,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _serialize_fault(f: PanelFault, comment_count: int = 0, photo_count: int = 0) -> dict:
    return {
        "id": f.id,
        "park_id": f.park_id,
        "panel_id": f.panel_id,
        "class": f.class_,
        "class_id": f.class_id,
        "severity": f.severity,
        "status": f.status,
        "occurrences": f.occurrences,
        "max_confidence": f.max_confidence,
        "first_seen_inspection_id": f.first_seen_inspection_id,
        "last_seen_inspection_id": f.last_seen_inspection_id,
        "first_seen_date": f.first_seen_date,
        "last_seen_date": f.last_seen_date,
        "last_bbox": json.loads(f.last_bbox) if f.last_bbox else None,
        "last_gps": json.loads(f.last_gps) if f.last_gps else None,
        "notes": f.notes,
        "comment_count": comment_count,
        "assignee": f.assignee,
        "due_date": f.due_date.isoformat() if f.due_date else None,
        "priority": effective_priority(f),
        "priority_override": f.priority,
        "resolved_at": f.resolved_at.isoformat() if f.resolved_at else None,
        "resolution_note": f.resolution_note,
        "photo_count": photo_count,
        "updated_at": f.updated_at.isoformat() if f.updated_at else None,
    }


def _serialize_fault_photo(p: FaultPhoto) -> dict:
    return {
        "id": p.id,
        "fault_id": p.fault_id,
        "original_name": p.original_name,
        "content_type": p.content_type,
        "size_bytes": p.size_bytes,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _serialize_comment(c: FaultComment) -> dict:
    return {
        "id": c.id,
        "fault_id": c.fault_id,
        "author": c.author,
        "body": c.body,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _serialize_mission_summary(m: Mission) -> dict:
    return {
        "id": m.id,
        "name": m.name,
        "park_id": m.park_id,
        "mission_type": m.mission_type,
        "camera_id": m.camera_id,
        "area_ha": m.area_ha,
        "image_count": m.image_count,
        "created_at": m.created_at.isoformat() if m.created_at else None,
    }


def _serialize_mission_full(m: Mission) -> dict:
    return {
        **_serialize_mission_summary(m),
        "params": json.loads(m.params) if m.params else {},
        "polygon": json.loads(m.polygon) if m.polygon else [],
        "waypoints": json.loads(m.waypoints) if m.waypoints else [],
        "updated_at": m.updated_at.isoformat() if m.updated_at else None,
    }


def _assigned_qty(session, component_id: int, exclude_assignment_id: int | None = None) -> int:
    q = session.query(ComponentAssignment).filter(
        ComponentAssignment.component_id == component_id
    )
    if exclude_assignment_id is not None:
        q = q.filter(ComponentAssignment.id != exclude_assignment_id)
    return sum(a.qty or 0 for a in q.all())


def _serialize_component(c: InventoryComponent, assigned: int) -> dict:
    return {
        "id": c.id,
        "name": c.name,
        "category": c.category,
        "part_number": c.part_number,
        "vendor": c.vendor,
        "link": c.link,
        "unit_cost": c.unit_cost,
        "currency": c.currency,
        "qty_total": c.qty_total or 0,
        "qty_assigned": assigned,
        "qty_available": (c.qty_total or 0) - assigned,
        "specs": c.specs,
        "notes": c.notes,
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _serialize_assignment(a: ComponentAssignment, component: InventoryComponent | None = None) -> dict:
    return {
        "id": a.id,
        "component_id": a.component_id,
        "prototype_id": a.prototype_id,
        "component_name": component.name if component else None,
        "component_category": component.category if component else None,
        "qty": a.qty or 0,
        "notes": a.notes,
        "created_at": a.created_at.isoformat() if a.created_at else None,
    }


def _serialize_prototype(p: Prototype, assignments: list[dict]) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "status": p.status,
        "description": p.description,
        "notes": p.notes,
        "assignments": assignments,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _serialize_order(o: ComponentOrder) -> dict:
    return {
        "id": o.id,
        "component_id": o.component_id,
        "name": o.name,
        "qty": o.qty or 0,
        "est_unit_cost": o.est_unit_cost,
        "vendor": o.vendor,
        "link": o.link,
        "status": o.status,
        "needed_by": o.needed_by,
        "notes": o.notes,
        "created_at": o.created_at.isoformat() if o.created_at else None,
        "updated_at": o.updated_at.isoformat() if o.updated_at else None,
    }


def _clean_name(payload: dict, required: bool = True) -> str | None:
    name = str(payload.get("name") or "").strip()
    if not name and required:
        raise HTTPException(status_code=400, detail="name is required")
    return name[:200] or None


def _non_negative_int(payload: dict, key: str, default: int, minimum: int = 0) -> int:
    raw = payload.get(key, default)
    try:
        value = int(raw)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{key} must be an integer")
    if value < minimum:
        raise HTTPException(status_code=400, detail=f"{key} must be >= {minimum}")
    return value


def _serialize_project(p: Project) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "client": p.client,
        "description": p.description,
        "status": p.status,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _project_sites(session, project_id: int) -> list[dict]:
    sites = []
    parks = session.query(Park).filter(Park.project_id == project_id).order_by(Park.id.asc()).all()
    for park in parks:
        inspections = (
            session.query(Inspection)
            .filter(Inspection.park_id == park.id)
            .order_by(Inspection.flight_date.desc())
            .all()
        )
        mission_count = session.query(Mission).filter(Mission.park_id == park.id).count()
        sites.append({
            "id": park.id,
            "name": park.name,
            "total_panels": park.total_panels,
            "inspection_count": len(inspections),
            "mission_count": mission_count,
            "last_inspection_date": inspections[0].flight_date if inspections else None,
        })
    return sites


def _serialize_note(n: TrackNote) -> dict:
    return {
        "id": n.id,
        "title": n.title,
        "kind": n.kind,
        "body": n.body,
        "url": n.url,
        "tags": n.tags,
        "created_at": n.created_at.isoformat() if n.created_at else None,
        "updated_at": n.updated_at.isoformat() if n.updated_at else None,
    }


def _serialize_track_file(f: TrackFile) -> dict:
    return {
        "id": f.id,
        "original_name": f.original_name,
        "stored_name": f.stored_name,
        "label": f.label,
        "content_type": f.content_type,
        "size_bytes": f.size_bytes,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


def _serialize_user(u: User, project_ids: list[int]) -> dict:
    """Public shape of an account — deliberately has no credential fields."""
    return {
        "id": u.id,
        "email": u.email,
        "role": u.role,
        "disabled": bool(u.disabled),
        "project_ids": list(project_ids),
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


def _serialize_share_link(link: ShareLink, now=None) -> dict:
    """Share link metadata. The token is only ever returned once, at creation."""
    from datetime import datetime

    now = now or datetime.utcnow()
    return {
        "id": link.id,
        "project_id": link.project_id,
        "label": link.label,
        "created_by": link.created_by,
        "created_at": link.created_at.isoformat() if link.created_at else None,
        "expires_at": link.expires_at.isoformat() if link.expires_at else None,
        "revoked_at": link.revoked_at.isoformat() if link.revoked_at else None,
        "revoked": link.revoked_at is not None,
        "expired": bool(link.expires_at and link.expires_at <= now),
    }
