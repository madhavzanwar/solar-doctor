"""SQLAlchemy ORM models for the Axalon solar inspection platform."""
from sqlalchemy import (
    Boolean, Column, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text,
    UniqueConstraint,
)
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

# Status values for PanelFault.status
FAULT_OPEN = "open"          # seen in the most recent inspection
FAULT_STALE = "stale"        # was open, not seen in the most recent inspection (awaiting confirmation)
FAULT_RESOLVED = "resolved"  # user-confirmed fix or auto-resolved after N missed inspections
# Repair workflow states (O&M dispatch) — layered on top of the detection states.
FAULT_ASSIGNED = "assigned"        # a named person/crew owns the repair
FAULT_IN_PROGRESS = "in_progress"  # repair work has started on site

FAULT_STATUSES = (FAULT_OPEN, FAULT_STALE, FAULT_ASSIGNED, FAULT_IN_PROGRESS, FAULT_RESOLVED)


# Allowed values for Project.status
PROJECT_STATUSES = ("active", "archived")


class Project(Base):
    """Top of the asset hierarchy: Project → Sites (parks) → Missions/Inspections."""
    __tablename__ = "projects"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    client = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    status = Column(String, default="active")       # one of PROJECT_STATUSES
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Park(Base):
    __tablename__ = "parks"
    id = Column(String, primary_key=True)          # e.g. "PARK_01"
    name = Column(String, nullable=False)
    mode = Column(String, default="auto")           # "auto" | "numbered"
    total_panels = Column(Integer, default=0)
    rows = Column(Integer, default=0)
    cols = Column(Integer, default=0)
    project_id = Column(Integer, ForeignKey("projects.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Inspection(Base):
    __tablename__ = "inspections"
    id = Column(String, primary_key=True)           # "BATCH-PARK_01-20260411-143022"
    park_id = Column(String, ForeignKey("parks.id"), nullable=False)
    flight_date = Column(String, nullable=True)     # store as ISO date string
    total_images = Column(Integer, default=0)
    total_detections = Column(Integer, default=0)
    summary = Column(Text, nullable=True)           # JSON string: {"CRITICAL":3,...}
    # Site metadata — written at job creation from API form params
    client = Column(String, nullable=True)
    location = Column(String, nullable=True)
    capacity_mw = Column(Float, nullable=True)
    inspection_type = Column(String, default="maintenance")  # commissioning | maintenance | rapid
    inspection_level = Column(String, default="simplified")  # simplified | standard | detailed
    irradiance_wm2 = Column(Float, nullable=True)
    wind_speed_bft = Column(Float, nullable=True)
    cloud_coverage_okta = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Detection(Base):
    __tablename__ = "detections"
    id = Column(Integer, primary_key=True, autoincrement=True)
    inspection_id = Column(String, ForeignKey("inspections.id"), nullable=False)
    fault_id = Column(Integer, ForeignKey("panel_faults.id"), nullable=True, index=True)
    image_id = Column(String, nullable=True)        # filename stem
    panel_id = Column(String, nullable=True)        # "R3-C7" or "R?-C?"
    class_ = Column("class", String, nullable=True) # 'class' is a Python keyword
    class_id = Column(Integer, nullable=True)
    severity = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    bbox = Column(Text, nullable=True)              # JSON "[x1,y1,x2,y2]"
    gps = Column(Text, nullable=True)               # JSON '{"lat":28.4,"lon":77.1}' or null
    # Radiometric temperatures (°C) — only set when the thermal image had a
    # `_temp.raw` companion (iTL612R Pro MATRIX-TEMP). ΔT drives IEC 62446-3 CoA.
    min_temp = Column(Float, nullable=True)
    max_temp = Column(Float, nullable=True)
    avg_temp = Column(Float, nullable=True)
    reference_temp = Column(Float, nullable=True)      # frame median ≈ healthy module
    delta_t_measured = Column(Float, nullable=True)    # max_temp − reference_temp
    delta_t_normalized = Column(Float, nullable=True)  # ΔT scaled to 1000 W/m²
    created_at = Column(DateTime, default=datetime.utcnow)


class PanelFault(Base):
    """
    A persistent fault on a (park, panel, class) triple — tracks the SAME
    issue across multiple inspections so we can flag new / recurring / resolved.

    Identity is (park_id, panel_id, class_). Confidence values are aggregates
    across all detections that have ever been linked to this fault.
    """
    __tablename__ = "panel_faults"
    id = Column(Integer, primary_key=True, autoincrement=True)
    park_id = Column(String, ForeignKey("parks.id"), nullable=False, index=True)
    panel_id = Column(String, nullable=False)               # "R3-C7" or "R?-C?"
    class_ = Column("class", String, nullable=False)         # canonical class name
    class_id = Column(Integer, nullable=True)
    severity = Column(String, nullable=True)                # worst severity ever seen
    status = Column(String, default=FAULT_OPEN, index=True) # one of FAULT_STATUSES
    occurrences = Column(Integer, default=1)                # number of inspections this fault appeared in
    max_confidence = Column(Float, default=0.0)
    first_seen_inspection_id = Column(String, ForeignKey("inspections.id"), nullable=True)
    last_seen_inspection_id = Column(String, ForeignKey("inspections.id"), nullable=True)
    first_seen_date = Column(String, nullable=True)         # ISO date string
    last_seen_date = Column(String, nullable=True)
    last_bbox = Column(Text, nullable=True)                 # JSON last bbox (for UI preview)
    last_gps = Column(Text, nullable=True)                  # JSON last GPS
    notes = Column(Text, nullable=True)                     # operator notes
    # ── Repair workflow ──
    assignee = Column(String(200), nullable=True)           # free-text name or email
    due_date = Column(Date, nullable=True)
    priority = Column(String(16), nullable=True)            # override; NULL → derived from severity
    resolved_at = Column(DateTime, nullable=True)           # set on → resolved, cleared on reopen
    resolution_note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FaultPhoto(Base):
    """Repair proof photo attached to a PanelFault, stored in the object store
    (or on local disk when none is configured)."""
    __tablename__ = "fault_photos"
    id = Column(Integer, primary_key=True, autoincrement=True)
    fault_id = Column(Integer, ForeignKey("panel_faults.id"), nullable=False, index=True)
    original_name = Column(String(200), nullable=False)     # sanitized upload filename
    stored_name = Column(String(400), nullable=False)       # object key, e.g. fault-photos/12/<uuid>_x.jpg
    content_type = Column(String(64), nullable=False)
    size_bytes = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


class Correction(Base):
    """User-drawn annotation box on a single-image inspect result."""
    __tablename__ = "corrections"
    id = Column(Integer, primary_key=True, autoincrement=True)
    job_id = Column(String, nullable=False, index=True)
    image_id = Column(String, nullable=True)
    panel_id = Column(String, nullable=True)
    class_ = Column("class", String, nullable=False)
    class_id = Column(Integer, nullable=True)
    severity = Column(String, nullable=True)
    bbox_norm = Column(Text, nullable=False)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class FaultComment(Base):
    """Append-only comment thread on a PanelFault — supports multi-actor workflow."""
    __tablename__ = "fault_comments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    fault_id = Column(Integer, ForeignKey("panel_faults.id"), nullable=False, index=True)
    author = Column(String(128), nullable=True)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Job(Base):
    """Persisted state for an inspection job."""
    __tablename__ = "jobs"
    id = Column(String, primary_key=True)
    park_id = Column(String, nullable=True, index=True)
    state = Column(String, nullable=False, default="queued")
    total = Column(Integer, nullable=True)
    processed = Column(Integer, nullable=True, default=0)
    message = Column(Text, nullable=True)
    result_path = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Mission(Base):
    """A planned drone survey mission — drawn area, flight params, computed waypoints."""
    __tablename__ = "missions"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    name         = Column(String, nullable=False)
    # Plain indexed string, not a FK — a mission may be planned before its park
    # exists in the DB (parks are created on first inspection).
    park_id      = Column(String, nullable=True, index=True)
    mission_type = Column(String, default="grid")   # grid | perimeter | corridor
    camera_id    = Column(String, nullable=True)
    params       = Column(Text, nullable=True)       # JSON MissionParams
    polygon      = Column(Text, nullable=True)       # JSON LatLon[] — drawn shape
    waypoints    = Column(Text, nullable=True)       # JSON Waypoint[]
    area_ha      = Column(Float, nullable=True)
    image_count  = Column(Integer, nullable=True)
    created_at   = Column(DateTime, default=datetime.utcnow)
    updated_at   = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# ── Inventory & prototype tracking (spec: 2026-06-12-inventory-page-design) ──

# Allowed values for InventoryComponent.category
COMPONENT_CATEGORIES = (
    "flight-controller", "motor", "esc", "battery", "propeller", "frame",
    "camera", "sensor", "companion-computer", "radio", "gps", "wiring", "other",
)

# Allowed values for Prototype.status
PROTOTYPE_STATUSES = ("planning", "building", "active", "retired")

# Allowed values for ComponentOrder.status
ORDER_STATUSES = ("planned", "ordered", "received", "cancelled")


class InventoryComponent(Base):
    """A hardware part type we own — qty_total counts every unit (in stock + installed)."""
    __tablename__ = "inventory_components"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    category = Column(String, default="other")       # one of COMPONENT_CATEGORIES
    part_number = Column(String, nullable=True)
    vendor = Column(String, nullable=True)
    link = Column(String, nullable=True)              # product URL
    unit_cost = Column(Float, nullable=True)
    currency = Column(String, default="INR")
    qty_total = Column(Integer, default=0)            # >= 0
    specs = Column(Text, nullable=True)               # free JSON/text
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class Prototype(Base):
    """A drone build (or any hardware prototype) that components get installed into."""
    __tablename__ = "prototypes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    status = Column(String, default="planning")       # one of PROTOTYPE_STATUSES
    description = Column(Text, nullable=True)
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class ComponentAssignment(Base):
    """BOM line: qty units of a component installed in a prototype."""
    __tablename__ = "component_assignments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    component_id = Column(Integer, ForeignKey("inventory_components.id"), nullable=False, index=True)
    prototype_id = Column(Integer, ForeignKey("prototypes.id"), nullable=False, index=True)
    qty = Column(Integer, default=1)                  # >= 1, <= component availability
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ComponentOrder(Base):
    """A planned/placed purchase — receiving a linked order stocks-in qty_total."""
    __tablename__ = "component_orders"
    id = Column(Integer, primary_key=True, autoincrement=True)
    component_id = Column(Integer, ForeignKey("inventory_components.id"), nullable=True, index=True)
    name = Column(String, nullable=False)             # item name (defaults from component)
    qty = Column(Integer, default=1)                  # >= 1
    est_unit_cost = Column(Float, nullable=True)
    vendor = Column(String, nullable=True)
    link = Column(String, nullable=True)
    status = Column(String, default="planned")        # one of ORDER_STATUSES
    needed_by = Column(String, nullable=True)         # ISO date string
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AppConfig(Base):
    """Key/value app settings stored in the DB (Supabase) — e.g. the /track
    workspace password hash. Lets config live in the database instead of
    per-host environment variables."""
    __tablename__ = "app_config"
    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


# Allowed values for TrackNote.kind
NOTE_KINDS = ("research", "log", "doc", "link", "idea", "other")


class TrackNote(Base):
    """Research note / hardware log / reference link on the /track workspace."""
    __tablename__ = "track_notes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String, nullable=False)
    kind = Column(String, default="other")            # one of NOTE_KINDS
    body = Column(Text, nullable=True)
    url = Column(String, nullable=True)
    tags = Column(String, nullable=True)              # comma-separated
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TrackFile(Base):
    """Uploaded reference file (.stl, .pdf, datasheets, …) stored on disk."""
    __tablename__ = "track_files"
    id = Column(Integer, primary_key=True, autoincrement=True)
    original_name = Column(String, nullable=False)    # sanitized upload filename
    stored_name = Column(String, nullable=False)      # uuid-prefixed name on disk
    label = Column(String, nullable=True)             # human description
    content_type = Column(String, nullable=True)
    size_bytes = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


# ── Users, sessions, project membership, share links (AXALON_AUTH_MODE=users) ──

ROLE_ADMIN = "admin"        # everything, including user management
ROLE_OPERATOR = "operator"  # run inspections, edit faults/missions/inventory
ROLE_VIEWER = "viewer"      # read-only
USER_ROLES = (ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER)


class User(Base):
    """A console account. Only consulted when AXALON_AUTH_MODE=users."""
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String(254), nullable=False, unique=True)   # stored lower-cased
    password_hash = Column(String(255), nullable=False)        # pbkdf2_sha256$iters$salt$hash
    role = Column(String(16), nullable=False, default=ROLE_VIEWER)
    disabled = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class UserSession(Base):
    """Server-side login session. Only the SHA-256 of the bearer token is kept,
    so a leaked database cannot be replayed as live sessions."""
    __tablename__ = "user_sessions"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash = Column(String(64), nullable=False, unique=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)


class ProjectMember(Base):
    """Grants a non-admin user visibility of one project's parks and their data."""
    __tablename__ = "project_members"
    __table_args__ = (UniqueConstraint("user_id", "project_id", name="uq_project_members_user_project"),)
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ShareLink(Base):
    """Revocable, expiring read-only link to one project (`?share=<token>`)."""
    __tablename__ = "share_links"
    id = Column(Integer, primary_key=True, autoincrement=True)
    token_hash = Column(String(64), nullable=False, unique=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True)
    label = Column(String(200), nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    revoked_at = Column(DateTime, nullable=True)


# Composite index to make upsert lookups fast.
Index(
    "ix_panel_faults_identity",
    PanelFault.park_id, PanelFault.panel_id, PanelFault.class_,
    unique=True,
)
