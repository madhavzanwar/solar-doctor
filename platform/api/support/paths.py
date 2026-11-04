"""Filesystem locations used across the API.

Kept in one place so the directory layout is discoverable and the mkdir
side-effects happen exactly once, at first import.
"""
from __future__ import annotations

import os
from pathlib import Path

OUTPUT_DIR = Path(os.getenv("AXALON_OUTPUT_DIR", "output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ORTHO_DIR = OUTPUT_DIR / "ortho"
ORTHO_DIR.mkdir(parents=True, exist_ok=True)

TRACK_FILES_DIR = OUTPUT_DIR / "track_files"
TRACK_FILES_DIR.mkdir(parents=True, exist_ok=True)

# Local fallback for repair proof photos when no object store is configured.
FAULT_PHOTOS_DIR = OUTPUT_DIR / "fault_photos"
FAULT_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)

__all__ = ["OUTPUT_DIR", "ORTHO_DIR", "TRACK_FILES_DIR", "FAULT_PHOTOS_DIR"]
