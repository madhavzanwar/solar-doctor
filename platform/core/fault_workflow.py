"""Fault repair workflow rules — status transitions and priority derivation.

Pure domain logic (no FastAPI, no session) so the API, the tracking pipeline
and the tests all share one definition of what an O&M team may do to a fault.
"""
from __future__ import annotations

from datetime import datetime

from ml.src.utils import SEVERITY_MAP

from axalon.db.models import (
    FAULT_ASSIGNED,
    FAULT_IN_PROGRESS,
    FAULT_OPEN,
    FAULT_RESOLVED,
    FAULT_STALE,
    FAULT_STATUSES,
    PanelFault,
)

# Priority scale, most urgent first. Stored lowercase in PanelFault.priority.
PRIORITY_LEVELS = ("urgent", "high", "medium", "low")
PRIORITY_RANK = {p: i for i, p in enumerate(PRIORITY_LEVELS)}

# Severity *level* → default priority. Class → severity comes from SEVERITY_MAP.
_SEVERITY_TO_PRIORITY = {
    "CRITICAL": "urgent",
    "HIGH": "high",
    "MEDIUM": "medium",
    "LOW": "low",
}

# Statuses in which someone must own the repair.
OWNED_STATUSES = frozenset({FAULT_ASSIGNED, FAULT_IN_PROGRESS})

# Statuses a work order is raised for by default.
ACTIONABLE_STATUSES = (FAULT_OPEN, FAULT_ASSIGNED, FAULT_IN_PROGRESS)

# from-status → statuses an operator may move the fault to.
# `stale` is set by the tracking pipeline; operators may only set it on an
# undispatched open fault. A resolved fault must be reopened before new work.
ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    FAULT_OPEN: frozenset({FAULT_STALE, FAULT_ASSIGNED, FAULT_IN_PROGRESS, FAULT_RESOLVED}),
    FAULT_STALE: frozenset({FAULT_OPEN, FAULT_ASSIGNED, FAULT_IN_PROGRESS, FAULT_RESOLVED}),
    FAULT_ASSIGNED: frozenset({FAULT_OPEN, FAULT_IN_PROGRESS, FAULT_RESOLVED}),
    FAULT_IN_PROGRESS: frozenset({FAULT_OPEN, FAULT_ASSIGNED, FAULT_RESOLVED}),
    FAULT_RESOLVED: frozenset({FAULT_OPEN}),
}


class WorkflowError(ValueError):
    """A request that is well-formed but breaks a workflow rule (→ HTTP 422)."""


def derived_priority(fault: PanelFault) -> str | None:
    """Default priority from the canonical class severity (falls back to the
    fault's recorded severity for classes outside SEVERITY_MAP)."""
    severity = SEVERITY_MAP.get(fault.class_ or "") or fault.severity
    return _SEVERITY_TO_PRIORITY.get((severity or "").upper())


def effective_priority(fault: PanelFault) -> str | None:
    return fault.priority or derived_priority(fault)


def check_transition(current: str | None, target: str) -> None:
    """Raise WorkflowError unless current → target is allowed (same → same is a no-op)."""
    if target not in FAULT_STATUSES:
        raise ValueError(f"Invalid status. Allowed: {', '.join(FAULT_STATUSES)}")
    current = current or FAULT_OPEN
    if current == target:
        return
    allowed = ALLOWED_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        options = ", ".join(sorted(allowed)) or "none"
        raise WorkflowError(
            f"Cannot move fault from '{current}' to '{target}'. Allowed from '{current}': {options}"
        )


def apply_status(fault: PanelFault, target: str, now: datetime | None = None) -> None:
    """Validate and apply a status change, maintaining resolved_at."""
    check_transition(fault.status, target)
    if target == fault.status:
        return
    if target == FAULT_RESOLVED:
        fault.resolved_at = now or datetime.utcnow()
    else:
        fault.resolved_at = None
    fault.status = target


def check_ownership(fault: PanelFault) -> None:
    """Assigned / in-progress work must name who is doing it."""
    if fault.status in OWNED_STATUSES and not (fault.assignee or "").strip():
        raise WorkflowError(f"An assignee is required while a fault is '{fault.status}'")


__all__ = [
    "ACTIONABLE_STATUSES",
    "ALLOWED_TRANSITIONS",
    "OWNED_STATUSES",
    "PRIORITY_LEVELS",
    "PRIORITY_RANK",
    "WorkflowError",
    "apply_status",
    "check_ownership",
    "check_transition",
    "derived_priority",
    "effective_priority",
]
