"""deps.py — the shared import barrel for the API routers.

Every router does `from axalon.api.deps import *`, so this module's job is to
re-export one flat namespace. The actual implementations live in focused
modules under `axalon.api.support` — edit those, not this file:

    support/paths.py         output/ortho/track directory layout
    support/security.py      bearer auth + park/job/filename validation
    support/archives.py      hardened ZIP extraction
    support/orchestrator.py  lazily-built InspectionOrchestrator singleton
    support/jobs.py          job lifecycle, batch worker, result cleanup
    support/geo.py           synthetic GPS for EXIF-less imagery
    support/orthos.py        GeoTIFF name/path validation + metadata

Only wiring that is genuinely API-wide belongs here directly.
"""
from __future__ import annotations

# ── Re-exported stdlib (routers rely on these arriving via the star import) ──
import json
import logging
import mimetypes
import os
import re
import shutil
import stat
import tempfile
import uuid
import zipfile
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

# ── Re-exported FastAPI surface ──────────────────────────────────────────────
from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    Security,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# ── Domain layer ─────────────────────────────────────────────────────────────
from axalon.core.app_config import (
    OK as APP_CONFIG_OK,
    UNCONFIGURED as APP_CONFIG_UNCONFIGURED,
    WRONG as APP_CONFIG_WRONG,
    set_track_password,
    verify_track_password,
)
from axalon.core.object_store import get_track_store
from axalon.db.models import (
    COMPONENT_CATEGORIES,
    FAULT_ASSIGNED,
    FAULT_IN_PROGRESS,
    FAULT_OPEN,
    FAULT_RESOLVED,
    FAULT_STALE,
    FAULT_STATUSES,
    NOTE_KINDS,
    ORDER_STATUSES,
    PROJECT_STATUSES,
    PROTOTYPE_STATUSES,
    ComponentAssignment,
    ComponentOrder,
    Correction,
    Detection as DbDetection,
    FaultComment,
    FaultPhoto,
    Inspection,
    InventoryComponent,
    Job as DbJob,
    Mission,
    PanelFault,
    Park,
    Project,
    Prototype,
    TrackFile,
    TrackNote,
)
from axalon.db.session import get_session
from axalon.park.diff import build_diff
from axalon.pipeline.orchestrator import InspectionOrchestrator
from axalon.reporting.geojson_writer import write_geojson
from axalon.reporting.report import (
    generate_excel_report,
    generate_json_report,
    generate_pdf_report,
)

from axalon.api.agents_router import router as agents_router
from axalon.api.serializers import *  # noqa: F401,F403

# ── Extracted helper modules ─────────────────────────────────────────────────
from axalon.api.support.archives import (
    _MAX_ZIP_BYTES,
    _MAX_ZIP_MEMBERS,
    _MAX_ZIP_RATIO,
    _MAX_ZIP_UNCOMPRESSED_BYTES,
    _ZIP_EXTRACT_TIMEOUT_S,
    _is_unsafe_member,
    _safe_extract_zip,
    _safe_extract_zip_with_timeout,
)
from axalon.api.support.geo import (
    _DEMO_ORIGIN_LAT,
    _DEMO_ORIGIN_LON,
    _synthetic_detection_gps,
    _synthetic_image_gps,
)
from axalon.api.support.jobs import (
    _REPORT_FORMAT_MAP,
    _cleanup_old_results,
    _corrections_for_job,
    _create_job,
    _get_job,
    _read_inspection_report,
    _run_batch_job,
    _state_from_status,
    _update_job,
)
from axalon.api.support.orchestrator import get_orchestrator
from axalon.api.support.orthos import (
    _EMPTY_TILE_CACHE,
    _MAX_ORTHO_BYTES,
    _ORTHO_NAME_RE,
    _empty_tile_png,
    _ortho_metadata,
    _ortho_path,
    _register_ortho,
    _validate_ortho_name,
)
from axalon.api.support.paths import FAULT_PHOTOS_DIR, ORTHO_DIR, OUTPUT_DIR, TRACK_FILES_DIR
from axalon.api.support.principal import Principal, current_principal
from axalon.api.support.scope import (
    ensure_fault_visible,
    ensure_job_visible,
    ensure_park_visible,
    ensure_project_visible,
    park_is_visible,
    scope_missions,
    scope_parks,
    scope_projects,
    visible_park_ids,
)
from axalon.api.support.security import (
    _ALLOWED_IMAGE_EXTS,
    _FILENAME_RE,
    _JOB_ID_RE,
    _MAX_IMAGE_BYTES,
    _MAX_PARK_ID_LEN,
    _bearer,
    _safe_filename,
    _validate_job_id,
    _validate_park_id,
    require_auth,
)

logger = logging.getLogger("axalon.api")


# ── API-wide wiring that has no better home ──────────────────────────────────
# Outcome of the startup migration run, surfaced on /health. The API keeps
# serving when migrations fail, so without this a schema stuck at an old revision
# is invisible. State only — /health is public and error text can carry DB details.
MIGRATION_STATUS: dict = {"state": "not_run"}


def _run_alembic_migrations() -> None:
    """Run Alembic migrations for persistent DBs; tests still use create_all()."""
    from axalon.db.url import resolve_db_url

    db_url = resolve_db_url()
    if ":memory:" in db_url or os.environ.get("PYTEST_CURRENT_TEST"):
        return
    try:
        from alembic.config import Config as AlembicConfig
        from alembic import command as alembic_cmd

        repo_root = Path(__file__).resolve().parents[2]
        cfg = AlembicConfig(str(repo_root / "alembic.ini"))
        cfg.set_main_option("script_location", str(repo_root / "alembic"))
        # Alembic's config is a ConfigParser: a bare "%" (a percent-encoded
        # password in the URL) is interpolation syntax and raises. Escape it.
        cfg.set_main_option("sqlalchemy.url", db_url.replace("%", "%%"))
        alembic_cmd.upgrade(cfg, "head")
        MIGRATION_STATUS["state"] = "ok"
        logger.info("Alembic migrations: up to date")
    except Exception:
        MIGRATION_STATUS["state"] = "failed"
        logger.exception("Alembic migrations FAILED — schema may be behind head")


def _check_iec_warnings(site_meta: dict) -> list[str]:
    """Return IEC compliance warnings for the given site metadata."""
    warnings = []
    try:
        irr = float(site_meta.get("irradiance_wm2") or 0)
        if 0 < irr < 600:
            warnings.append(
                f"Irradiance {irr:.0f} W/m² is below the IEC 62446-3 "
                "minimum of 600 W/m². Results may not meet standard requirements."
            )
    except (TypeError, ValueError):
        pass
    return warnings


_SETTINGS_PATH = Path(__file__).resolve().parents[1] / "config" / "settings.yaml"

_ALLOWED_FAULT_STATUSES = set(FAULT_STATUSES)

_IMAGE_SUFFIXES = ("_annotated.jpg", "_rgb_annotated.jpg")

_SEVERITY_COLOR = {
    "CRITICAL": "#dc2626",
    "HIGH":     "#ea580c",
    "MEDIUM":   "#d97706",
    "LOW":      "#0284c7",
}

_TRACK_ALLOWED_EXTENSIONS = {
    ".stl", ".step", ".stp", ".obj", ".3mf", ".dxf", ".f3d", ".fcstd",
    ".pdf", ".md", ".txt", ".csv", ".xlsx", ".docx",
    ".png", ".jpg", ".jpeg", ".webp", ".svg",
    ".zip", ".json", ".yaml", ".yml",
}

_MAX_TRACK_FILE_BYTES = 200 * 1024 * 1024  # 200 MB — STL meshes can be large


# Re-export everything for `from axalon.api.deps import *`
__all__ = [
    "APP_CONFIG_OK",
    "APP_CONFIG_UNCONFIGURED",
    "APP_CONFIG_WRONG",
    "BackgroundTasks",
    "COMPONENT_CATEGORIES",
    "CORSMiddleware",
    "ComponentAssignment",
    "ComponentOrder",
    "Correction",
    "DbDetection",
    "DbJob",
    "FAULT_ASSIGNED",
    "FAULT_IN_PROGRESS",
    "Depends",
    "FAULT_OPEN",
    "FAULT_PHOTOS_DIR",
    "FAULT_RESOLVED",
    "FAULT_STALE",
    "FAULT_STATUSES",
    "FastAPI",
    "FaultComment",
    "FaultPhoto",
    "File",
    "FileResponse",
    "Form",
    "HTTPAuthorizationCredentials",
    "HTTPBearer",
    "HTTPException",
    "Inspection",
    "InspectionOrchestrator",
    "InventoryComponent",
    "JSONResponse",
    "Mission",
    "NOTE_KINDS",
    "ORDER_STATUSES",
    "ORTHO_DIR",
    "OUTPUT_DIR",
    "PROJECT_STATUSES",
    "PROTOTYPE_STATUSES",
    "PanelFault",
    "Principal",
    "Park",
    "Path",
    "Project",
    "Prototype",
    "Request",
    "Response",
    "Security",
    "StreamingResponse",
    "TRACK_FILES_DIR",
    "TrackFile",
    "TrackNote",
    "UploadFile",
    "_ALLOWED_FAULT_STATUSES",
    "_ALLOWED_IMAGE_EXTS",
    "_DEMO_ORIGIN_LAT",
    "_DEMO_ORIGIN_LON",
    "_EMPTY_TILE_CACHE",
    "_FILENAME_RE",
    "_IMAGE_SUFFIXES",
    "_JOB_ID_RE",
    "_MAX_IMAGE_BYTES",
    "_MAX_ORTHO_BYTES",
    "_MAX_PARK_ID_LEN",
    "_MAX_TRACK_FILE_BYTES",
    "_MAX_ZIP_BYTES",
    "_MAX_ZIP_MEMBERS",
    "_MAX_ZIP_RATIO",
    "_MAX_ZIP_UNCOMPRESSED_BYTES",
    "_ORTHO_NAME_RE",
    "_REPORT_FORMAT_MAP",
    "_SETTINGS_PATH",
    "_SEVERITY_COLOR",
    "_TRACK_ALLOWED_EXTENSIONS",
    "_ZIP_EXTRACT_TIMEOUT_S",
    "_assigned_qty",
    "_bearer",
    "_check_iec_warnings",
    "_clean_name",
    "_cleanup_old_results",
    "_corrections_for_job",
    "_create_job",
    "_empty_tile_png",
    "_get_job",
    "_is_unsafe_member",
    "_non_negative_int",
    "_ortho_metadata",
    "_ortho_path",
    "_register_ortho",
    "_project_sites",
    "_read_inspection_report",
    "MIGRATION_STATUS",
    "_run_alembic_migrations",
    "_run_batch_job",
    "_safe_extract_zip",
    "_safe_extract_zip_with_timeout",
    "_safe_filename",
    "_serialize_assignment",
    "_serialize_comment",
    "_serialize_component",
    "_serialize_correction",
    "_serialize_detection_temps",
    "_serialize_fault",
    "_serialize_mission_full",
    "_serialize_mission_summary",
    "_serialize_note",
    "_serialize_order",
    "_serialize_project",
    "_serialize_prototype",
    "_serialize_track_file",
    "_state_from_status",
    "_synthetic_detection_gps",
    "_synthetic_image_gps",
    "_update_job",
    "_validate_job_id",
    "_validate_ortho_name",
    "_validate_park_id",
    "agents_router",
    "asynccontextmanager",
    "build_diff",
    "current_principal",
    "datetime",
    "ensure_fault_visible",
    "ensure_job_visible",
    "ensure_park_visible",
    "ensure_project_visible",
    "generate_excel_report",
    "generate_json_report",
    "generate_pdf_report",
    "get_orchestrator",
    "get_session",
    "get_track_store",
    "json",
    "logger",
    "logging",
    "mimetypes",
    "os",
    "park_is_visible",
    "re",
    "require_auth",
    "scope_missions",
    "scope_parks",
    "scope_projects",
    "set_track_password",
    "shutil",
    "stat",
    "tempfile",
    "timedelta",
    "uuid",
    "visible_park_ids",
    "verify_track_password",
    "write_geojson",
    "zipfile",
]
