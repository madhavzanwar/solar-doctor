"""
ingest.py — Image pair ingestion, validation, and metadata extraction.

Finds matching thermal+RGB pairs from a folder, validates them,
and extracts GPS/EXIF metadata for the pipeline.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import cv2

from axalon.core.geo import extract_gps_exif
from axalon.core.temp_extractor import find_temp_companion

# Supported naming conventions: thermal_001/rgb_001, ir_001/vis_001, 001_T/001_V
_THERMAL_SUFFIXES = {"thermal", "ir", "t", "therm"}
_RGB_SUFFIXES = {"rgb", "vis", "v", "visual"}
_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}


def find_image_pairs(
    folder: str | Path,
    thermal_subdir: str = "thermal",
    rgb_subdir: str = "rgb",
) -> list[dict]:
    """Scan a flight folder for thermal+RGB image pairs.

    Expects structure:
        folder/
            thermal/  ← thermal IR images
            rgb/      ← RGB images (optional)

    Falls back to single-folder pairing by filename stem if subdirs not found.

    Returns:
        List of pair dicts:
        {
            "id": "thermal_001",
            "thermal": Path,
            "rgb": Path | None,
            "thermal_gps": dict | None,
            "rgb_gps": dict | None,
            "thermal_size": (width, height),
        }
    """
    folder = Path(folder)
    thermal_dir = folder / thermal_subdir
    rgb_dir = folder / rgb_subdir

    if thermal_dir.exists():
        thermal_images = sorted(p for p in thermal_dir.iterdir() if p.suffix.lower() in _IMAGE_EXTENSIONS)
    else:
        # Flat folder — find images with thermal-like names
        thermal_images = sorted(
            p for p in folder.iterdir()
            if p.suffix.lower() in _IMAGE_EXTENSIONS and _is_thermal_name(p.stem)
        )

    pairs = []
    for thermal_path in thermal_images:
        rgb_path = _find_rgb_match(thermal_path, rgb_dir if rgb_dir.exists() else folder)

        img = cv2.imread(str(thermal_path))
        if img is None:
            continue
        h, w = img.shape[:2]

        pairs.append({
            "id": thermal_path.stem,
            "thermal": thermal_path,
            "rgb": rgb_path,
            "temp_raw": find_temp_companion(thermal_path),
            "thermal_gps": extract_gps_exif(thermal_path),
            "rgb_gps": extract_gps_exif(rgb_path) if rgb_path else None,
            "thermal_size": (w, h),
        })

    return pairs


def load_mission_metadata(folder: str | Path) -> dict:
    """Load optional mission_metadata.json from the flight folder."""
    meta_path = Path(folder) / "mission_metadata.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text())
    return {}


def validate_pair(pair: dict) -> list[str]:
    """Validate an image pair. Returns list of warning strings (empty = OK)."""
    warnings = []
    if not pair["thermal"].exists():
        warnings.append(f"Thermal image missing: {pair['thermal']}")
    if pair["rgb"] is None:
        warnings.append("No RGB image found — fusion and OCR disabled for this pair")
    if pair["thermal_gps"] is None:
        warnings.append("No GPS EXIF in thermal image — geospatial features will be limited")
    return warnings


def _is_thermal_name(stem: str) -> bool:
    parts = re.split(r"[_\-\.]", stem.lower())
    return any(p in _THERMAL_SUFFIXES for p in parts)


def _find_rgb_match(thermal_path: Path, rgb_dir: Path) -> Path | None:
    """Find the RGB image that corresponds to a thermal image by stem matching."""
    thermal_stem = thermal_path.stem

    # Try direct substitution of thermal suffix with RGB suffix
    for tsuf in _THERMAL_SUFFIXES:
        pattern = re.compile(re.escape(tsuf), re.IGNORECASE)
        if re.search(pattern, thermal_stem):
            for rsuf in _RGB_SUFFIXES:
                candidate_stem = re.sub(pattern, rsuf, thermal_stem, count=1)
                for ext in _IMAGE_EXTENSIONS:
                    candidate = rgb_dir / (candidate_stem + ext)
                    if candidate.exists():
                        return candidate

    # Fallback: same stem name in rgb_dir
    for ext in _IMAGE_EXTENSIONS:
        candidate = rgb_dir / (thermal_stem + ext)
        if candidate.exists():
            return candidate

    return None
