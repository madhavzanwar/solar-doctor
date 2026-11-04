"""Response (`*Out`) schemas for GET endpoints (Plan 02).

Every model sets `extra="allow"`, so any key the serializers return that is not
explicitly declared still passes through untouched — response_model documents the
shape in OpenAPI without ever dropping a field the frontend relies on.

Note: serializer dicts use the JSON key "class" (a Python keyword). It is left
undeclared and flows through via extra="allow", keeping the output identical.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict


class _Out(BaseModel):
    """Base: allow and preserve undeclared keys."""
    model_config = ConfigDict(extra="allow")


# ── Inventory ────────────────────────────────────────────────────────────────

class ComponentOut(_Out):
    id: int
    name: str | None = None
    category: str | None = None
    part_number: str | None = None
    vendor: str | None = None
    link: str | None = None
    unit_cost: float | None = None
    currency: str | None = None
    qty_total: int | None = None
    qty_assigned: int | None = None
    qty_available: int | None = None
    specs: Any | None = None
    notes: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class AssignmentOut(_Out):
    id: int
    component_id: int | None = None
    prototype_id: int | None = None
    component_name: str | None = None
    component_category: str | None = None
    qty: int | None = None
    notes: str | None = None
    created_at: str | None = None


class PrototypeOut(_Out):
    id: int
    name: str | None = None
    status: str | None = None
    description: str | None = None
    notes: str | None = None
    assignments: list[AssignmentOut] = []
    created_at: str | None = None
    updated_at: str | None = None


class OrderOut(_Out):
    id: int
    component_id: int | None = None
    name: str | None = None
    qty: int | None = None
    est_unit_cost: float | None = None
    vendor: str | None = None
    link: str | None = None
    status: str | None = None
    needed_by: str | None = None
    notes: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class InventorySummaryOut(_Out):
    component_count: int
    prototype_count: int
    open_order_count: int
    stock_value: float
    low_stock: list[ComponentOut] = []


# ── Projects ─────────────────────────────────────────────────────────────────

class ProjectOut(_Out):
    id: int
    name: str | None = None
    client: str | None = None
    description: str | None = None
    status: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    sites: list[dict] | None = None  # attached by the endpoint, shape varies


# ── Track ────────────────────────────────────────────────────────────────────

class NoteOut(_Out):
    id: int
    title: str | None = None
    kind: str | None = None
    body: str | None = None
    url: str | None = None
    tags: Any | None = None
    created_at: str | None = None
    updated_at: str | None = None


class TrackFileOut(_Out):
    id: int
    original_name: str | None = None
    stored_name: str | None = None
    label: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    created_at: str | None = None


# ── Faults ───────────────────────────────────────────────────────────────────

class FaultOut(_Out):
    id: int
    park_id: str | None = None
    panel_id: str | None = None
    class_id: int | None = None
    severity: str | None = None
    status: str | None = None
    occurrences: int | None = None
    max_confidence: float | None = None
    notes: str | None = None
    comment_count: int | None = None
    assignee: str | None = None
    due_date: str | None = None
    priority: str | None = None
    priority_override: str | None = None
    resolved_at: str | None = None
    resolution_note: str | None = None
    photo_count: int | None = None
    # "class", first/last_seen_*, last_bbox, last_gps flow via extra="allow"


class FaultPhotoOut(_Out):
    id: int
    fault_id: int | None = None
    original_name: str | None = None
    content_type: str | None = None
    size_bytes: int | None = None
    created_at: str | None = None


class CommentOut(_Out):
    id: int
    fault_id: int | None = None
    author: str | None = None
    body: str | None = None
    created_at: str | None = None


# ── Missions ─────────────────────────────────────────────────────────────────

class MissionSummaryOut(_Out):
    id: int
    name: str | None = None
    park_id: str | None = None
    mission_type: str | None = None
    camera_id: str | None = None
    area_ha: float | None = None
    image_count: int | None = None
    created_at: str | None = None


class MissionFullOut(MissionSummaryOut):
    params: Any | None = None
    polygon: Any | None = None
    waypoints: Any | None = None
    updated_at: str | None = None


# ── Corrections ──────────────────────────────────────────────────────────────

class CorrectionOut(_Out):
    id: int
    job_id: str | None = None
    image_id: str | None = None
    panel_id: str | None = None
    class_id: int | None = None
    severity: str | None = None
    bbox_norm: Any | None = None
    notes: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    # "class" flows via extra="allow"


# ── Parks ────────────────────────────────────────────────────────────────────

class ParkListItemOut(_Out):
    id: str
    name: str | None = None


class ParksOut(_Out):
    """Envelope: {"parks": [...]}."""
    parks: list[dict] | None = None


class FaultsListOut(_Out):
    park_id: str | None = None
    total: int | None = None
    counts_by_status: dict | None = None
    faults: list[FaultOut] = []


class ParkSummaryOut(_Out):
    """Park inspection-history summary (shape owned by the endpoint)."""


class GridOut(_Out):
    """Park panel grid (shape owned by the endpoint)."""


class TrendOut(_Out):
    """Park severity trend over inspections."""


class RecurringOut(_Out):
    """Recurring-fault report."""


class ParkDiffOut(_Out):
    park_id: str | None = None
    inspection_a: str | None = None
    inspection_b: str | None = None
    summary: dict | None = None
    panels: list[dict] | None = None


# ── Misc aggregates (permissive passthrough; shape owned by the endpoint) ─────

class OverviewOut(_Out):
    """Analytics overview."""


class InspectionDiffOut(_Out):
    """Cross-inspection diff."""


class OrthoListOut(_Out):
    park_id: str | None = None
    orthos: list[dict] | None = None


class OrthoMetaOut(_Out):
    """Single ortho metadata."""


class JobMapOut(_Out):
    """Job map GeoJSON-ish payload."""


class JobStatusOut(_Out):
    job_id: str | None = None
    state: str | None = None
    status: str | None = None
    progress: float | None = None


class ModelInfoOut(_Out):
    """Facts read from the served weights file (see axalon.core.model_info)."""
    name: str = "unknown"
    architecture: str = "unknown"
    task: str = "unknown"
    num_classes: int | None = None
    ultralytics_version: str = "unknown"
    trained_at: str = "unknown"
    weights_path: str | None = None
    exists: bool = False
    size_bytes: int | None = None
    size_mb: float | None = None
    sha256: str | None = None


class HealthOut(_Out):
    status: str | None = None
    model: str | None = None
    weights: str | None = None
    model_info: ModelInfoOut | None = None
    version: str | None = None
    db: str | None = None
    parks_in_db: int | None = None


class SettingsOut(_Out):
    settings: Any | None = None
    path: str | None = None


class AlertChannelOut(_Out):
    status: str
    detail: str = ""


class AlertTestOut(_Out):
    configured: bool
    min_severity: str
    channels: dict[str, AlertChannelOut]
