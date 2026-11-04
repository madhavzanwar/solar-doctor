"""
temp_extractor.py — RAW16 temperature matrix extraction for iTL612R Pro.

The iTL612R Pro saves a companion _temp.raw file alongside each thermal JPEG
when operating in MATRIX-TEMP mode. The file is a flat 640×512 uint16 array.

Conversion: temp_celsius = (raw_value * scale) - offset
iTL612R Pro defaults: scale=0.04, offset=273.15

Calibrate scale/offset in settings.yaml:
  camera:
    temp_scale: 0.04
    temp_offset: 273.15
"""
from __future__ import annotations

import numpy as np
from pathlib import Path

_DEFAULT_SCALE = 0.04
_DEFAULT_OFFSET = 273.15

# Per-detection temperature keys produced by the pipeline and persisted on
# Detection rows. All are nullable (no `_temp.raw` companion → no temperatures).
TEMP_FIELDS = (
    "min_temp",
    "max_temp",
    "avg_temp",
    "reference_temp",
    "delta_t_measured",
    "delta_t_normalized",
)


def load_temp_matrix(
    raw_path: str | Path,
    width: int = 640,
    height: int = 512,
    scale: float = _DEFAULT_SCALE,
    offset: float = _DEFAULT_OFFSET,
) -> np.ndarray:
    """Load a RAW16 temperature matrix and return float32 array in °C."""
    raw_path = Path(raw_path)
    if not raw_path.exists():
        raise FileNotFoundError(f"Temperature matrix not found: {raw_path}")
    raw = np.frombuffer(raw_path.read_bytes(), dtype=np.uint16)
    if raw.size != width * height:
        raise ValueError(
            f"Expected {width * height} pixels, got {raw.size} in {raw_path.name}"
        )
    return (raw.reshape(height, width).astype(np.float32) * scale) - offset


def extract_bbox_temps(
    temp_matrix: np.ndarray,
    bbox: list[int],
) -> dict:
    """Return min/max/avg temperature (°C) inside a detection bounding box."""
    x1, y1, x2, y2 = bbox
    h, w = temp_matrix.shape
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    region = temp_matrix[y1:y2, x1:x2]
    if region.size == 0:
        return {"min_temp": None, "max_temp": None, "avg_temp": None}
    return {
        "min_temp": round(float(np.min(region)), 2),
        "max_temp": round(float(np.max(region)), 2),
        "avg_temp": round(float(np.mean(region)), 2),
    }


def compute_delta_t(
    temp_matrix: np.ndarray,
    bbox: list[int],
) -> dict:
    """Compute delta_T = max bbox temp minus median frame temp.

    The median of the whole frame approximates the healthy-panel background.
    Returns all bbox_temps fields plus delta_t_measured and reference_temp.
    """
    bbox_temps = extract_bbox_temps(temp_matrix, bbox)
    if bbox_temps["max_temp"] is None:
        return {**bbox_temps, "delta_t_measured": None, "reference_temp": None}
    reference_temp = round(float(np.median(temp_matrix)), 2)
    return {
        **bbox_temps,
        "reference_temp": reference_temp,
        "delta_t_measured": round(bbox_temps["max_temp"] - reference_temp, 2),
    }


def normalize_delta_t(delta_t: float, irradiance_wm2: float) -> float | None:
    """Normalise delta_T to 1000 W/m² per IEC 62446-3 Annex C.

    Formula: ΔT_norm = ΔT_measured × (1000 / G)
    """
    if irradiance_wm2 is not None and irradiance_wm2 < 0:
        raise ValueError(f"irradiance_wm2 must be non-negative, got {irradiance_wm2}")
    if not irradiance_wm2 or irradiance_wm2 <= 0:
        return None
    return round(delta_t * (1000.0 / irradiance_wm2), 2)


def find_temp_companion(image_path: Path) -> Path | None:
    """Return the _temp.raw companion for a thermal image, or None if absent."""
    candidate = image_path.with_name(image_path.stem + "_temp.raw")
    return candidate if candidate.exists() else None
