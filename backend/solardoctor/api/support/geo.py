"""Synthetic GPS placement for imagery that carries no EXIF location.

Purely deterministic: the same index always maps to the same coordinate, so
demo and GPS-less missions still render a plausible map footprint.
"""
from __future__ import annotations

import math

_DEMO_ORIGIN_LAT = 27.5396
_DEMO_ORIGIN_LON = 71.9070

_EARTH_RADIUS_M = 6_371_000.0

# Serpentine survey grid spacing
_GRID_COLS = 8
_COL_SPACING_M = 20.0
_ROW_SPACING_M = 25.0

# Approximate ground footprint of one frame at ~40 m altitude
_FOOTPRINT_W_M = 18.0
_FOOTPRINT_H_M = 14.0

_DEFAULT_IMG_SIZE = [640, 512]


def _synthetic_image_gps(index: int, altitude_m: float) -> dict:
    """Generate a deterministic lat/lon for an image when EXIF GPS is absent.

    Lays images out on a 20m × 25m serpentine grid so the resulting map
    matches a realistic drone-mission footprint.
    """
    row, col = divmod(index, _GRID_COLS)
    if row % 2 == 1:
        col = _GRID_COLS - 1 - col  # serpentine
    dx_m = (col - _GRID_COLS / 2) * _COL_SPACING_M
    dy_m = -row * _ROW_SPACING_M  # north
    lat0 = math.radians(_DEMO_ORIGIN_LAT)
    return {
        "lat": _DEMO_ORIGIN_LAT + math.degrees(dy_m / _EARTH_RADIUS_M),
        "lon": _DEMO_ORIGIN_LON + math.degrees(dx_m / (_EARTH_RADIUS_M * math.cos(lat0))),
        "alt": float(altitude_m),
        "synthetic": True,
    }


def _synthetic_detection_gps(image_gps: dict, bbox: list[int], img_size: list[int]) -> dict:
    """Offset a detection inside an image footprint when GPS is absent."""
    w, h = (img_size or _DEFAULT_IMG_SIZE)[:2]
    cx = (bbox[0] + bbox[2]) / 2.0
    cy = (bbox[1] + bbox[3]) / 2.0
    dx_m = (cx / max(w, 1) - 0.5) * _FOOTPRINT_W_M
    dy_m = -(cy / max(h, 1) - 0.5) * _FOOTPRINT_H_M
    lat0 = math.radians(image_gps["lat"])
    return {
        "lat": image_gps["lat"] + math.degrees(dy_m / _EARTH_RADIUS_M),
        "lon": image_gps["lon"] + math.degrees(dx_m / (_EARTH_RADIUS_M * math.cos(lat0))),
        "synthetic": True,
    }


__all__ = [
    "_DEMO_ORIGIN_LAT",
    "_DEMO_ORIGIN_LON",
    "_synthetic_detection_gps",
    "_synthetic_image_gps",
]
