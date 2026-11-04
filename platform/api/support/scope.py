"""Project scoping for restricted principals (non-admin users, share links).

Visibility follows the asset hierarchy: a principal sees a park when they may
see its project; inspections, jobs, faults and missions inherit their park's
visibility. Parks with no project are admin-only.

Everything out of scope is reported as 404 with the same message as a missing
record, so ids belonging to other customers cannot be probed. For an
unrestricted principal every helper returns immediately without touching the
database, keeping off/apikey behaviour byte-for-byte unchanged.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from fastapi import HTTPException

from axalon.api.support.principal import Principal
from axalon.db.models import Inspection, Job, Mission, PanelFault, Park, Project
from axalon.db.session import get_session


@contextmanager
def _borrowed(session) -> Iterator:
    if session is not None:
        yield session
        return
    own = get_session()
    try:
        yield own
    finally:
        own.close()


def _not_found(detail: str) -> HTTPException:
    return HTTPException(status_code=404, detail=detail)


def scope_parks(query, principal: Principal):
    """Filter a query that selects from Park down to visible parks."""
    if not principal.is_restricted:
        return query
    return query.filter(Park.project_id.in_(sorted(principal.project_ids)))


def scope_projects(query, principal: Principal):
    if not principal.is_restricted:
        return query
    return query.filter(Project.id.in_(sorted(principal.project_ids)))


def visible_park_ids(session, principal: Principal) -> set[str] | None:
    """Ids of visible parks, or None when the principal is unrestricted."""
    if not principal.is_restricted:
        return None
    return {pid for (pid,) in scope_parks(session.query(Park.id), principal)}


def park_is_visible(session, principal: Principal, park_id: str | None) -> bool:
    if not principal.is_restricted:
        return True
    if not park_id:
        return False
    row = session.query(Park.project_id).filter(Park.id == park_id).first()
    return row is not None and principal.can_see_project(row[0])


def ensure_park_visible(
    principal: Principal, park_id: str | None, session=None, detail: str = "Park not found",
) -> None:
    if not principal.is_restricted:
        return
    with _borrowed(session) as s:
        if not park_is_visible(s, principal, park_id):
            raise _not_found(detail)


def ensure_project_visible(principal: Principal, project_id: int | None, detail: str = "Project not found") -> None:
    if not principal.can_see_project(project_id):
        raise _not_found(detail)


def ensure_job_visible(principal: Principal, job_id: str, session=None, detail: str = "Job not found") -> None:
    """A job/inspection is visible when the park it ran against is."""
    if not principal.is_restricted:
        return
    with _borrowed(session) as s:
        row = s.query(Job.park_id).filter(Job.id == job_id).first()
        if row is None:
            row = s.query(Inspection.park_id).filter(Inspection.id == job_id).first()
        if row is None or not park_is_visible(s, principal, row[0]):
            raise _not_found(detail)


def ensure_fault_visible(principal: Principal, fault_id: int, session=None, detail: str = "Fault not found") -> None:
    if not principal.is_restricted:
        return
    with _borrowed(session) as s:
        row = s.query(PanelFault.park_id).filter(PanelFault.id == fault_id).first()
        if row is None or not park_is_visible(s, principal, row[0]):
            raise _not_found(detail)


def scope_missions(session, query, principal: Principal):
    """Missions reference parks by plain string; unknown/empty parks are admin-only."""
    park_ids = visible_park_ids(session, principal)
    if park_ids is None:
        return query
    return query.filter(Mission.park_id.in_(sorted(park_ids)))


__all__ = [
    "ensure_fault_visible", "ensure_job_visible", "ensure_park_visible",
    "ensure_project_visible", "park_is_visible", "scope_missions", "scope_parks",
    "scope_projects", "visible_park_ids",
]
