"""Bearer auth and user-input validation for path/filename parameters.

Every helper here exists to stop untrusted strings from reaching the
filesystem or the database as-is.
"""
from __future__ import annotations

import os
import re

from fastapi import HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_MAX_PARK_ID_LEN = 64
_ALLOWED_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tiff", ".tif"}
_MAX_IMAGE_BYTES = 50 * 1024 * 1024   # 50 MB per image
_JOB_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,80}$")
_FILENAME_RE = re.compile(r"^[a-zA-Z0-9_\-.]{1,160}$")
_PARK_ID_RE = re.compile(r"^[a-zA-Z0-9_\-]+$")

_bearer = HTTPBearer(auto_error=False)


def require_auth(creds: HTTPAuthorizationCredentials | None = Security(_bearer)) -> None:
    """No-op when AXALON_API_KEY is unset; otherwise require Bearer auth."""
    api_key = os.environ.get("AXALON_API_KEY", "").strip()
    if not api_key:
        return
    if creds is None or creds.credentials != api_key:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def _safe_filename(raw: str | None, fallback: str = "upload") -> str:
    """Strip to basename only — prevents path traversal via uploaded filenames."""
    if not raw:
        return fallback
    from pathlib import Path

    name = Path(raw).name  # discards any directory components
    # Remove any remaining path separators or null bytes
    name = re.sub(r"[/\\:\x00]", "_", name)
    return name or fallback


def _validate_park_id(park_id: str) -> str:
    """Validate park_id is safe to use as a directory/DB key."""
    park_id = park_id.strip()
    if not park_id or len(park_id) > _MAX_PARK_ID_LEN:
        raise HTTPException(status_code=400, detail="park_id must be 1–64 characters")
    if not _PARK_ID_RE.match(park_id):
        raise HTTPException(
            status_code=400,
            detail="park_id may only contain letters, digits, hyphens, and underscores",
        )
    return park_id


def _validate_job_id(job_id: str) -> str:
    """Validate job_id path parameter — prevents directory traversal."""
    if not _JOB_ID_RE.match(job_id):
        raise HTTPException(status_code=400, detail="Invalid job ID format")
    return job_id


__all__ = [
    "_ALLOWED_IMAGE_EXTS",
    "_FILENAME_RE",
    "_JOB_ID_RE",
    "_MAX_IMAGE_BYTES",
    "_MAX_PARK_ID_LEN",
    "_bearer",
    "_safe_filename",
    "_validate_job_id",
    "_validate_park_id",
    "require_auth",
]
