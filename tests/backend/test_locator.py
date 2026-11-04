"""Unit tests for platform/park/locator.py — GPS → panel mapping.

Uses the REAL data shapes:
  - park_layout: {"mode", "total_panels", "rows", "panel_map"}
  - panel_map:   {panel_id: {"bbox_image", "center", "gps"}}
  - gps dicts:   {"lat": float, "lon": float}
"""
from __future__ import annotations

import pytest

from axalon.park.locator import (
    PANEL_ID_UNKNOWN,
    LocatedFault,
    locate_faults,
)

# A small 2x2 auto-grid park anchored near a real-ish latitude. Panels are
# spaced ~2 m apart so nearest-GPS matching is unambiguous.
_ORIGIN_LAT = 28.4000
_ORIGIN_LON = 77.1000
# ~2 m in degrees at this latitude.
_DLAT = 2.0 / 6_371_000.0 * (180.0 / 3.141592653589793)
_DLON = _DLAT  # close enough for cos(28°) ≈ 0.88; spacing stays unambiguous


def _gps(lat: float, lon: float) -> dict:
    return {"lat": lat, "lon": lon}


def _grid_layout() -> dict:
    panel_map = {
        "R1-C1": {"bbox_image": [0, 0, 10, 10], "center": [5, 5],
                  "gps": _gps(_ORIGIN_LAT, _ORIGIN_LON)},
        "R1-C2": {"bbox_image": [10, 0, 20, 10], "center": [15, 5],
                  "gps": _gps(_ORIGIN_LAT, _ORIGIN_LON + _DLON)},
        "R2-C1": {"bbox_image": [0, 10, 10, 20], "center": [5, 15],
                  "gps": _gps(_ORIGIN_LAT - _DLAT, _ORIGIN_LON)},
        "R2-C2": {"bbox_image": [10, 10, 20, 20], "center": [15, 15],
                  "gps": _gps(_ORIGIN_LAT - _DLAT, _ORIGIN_LON + _DLON)},
    }
    return {"mode": "auto-grid", "total_panels": 4, "rows": 2, "panel_map": panel_map}


def _det(gps: dict | None) -> dict:
    d = {"class": "hot-spot-high", "class_id": 10, "confidence": 0.9,
         "bbox": [0, 0, 5, 5], "severity": "CRITICAL"}
    if gps is not None:
        d["gps"] = gps
    return d


def test_grid_locate_origin():
    """Detection exactly at the origin panel GPS → R1-C1 with high confidence."""
    layout = _grid_layout()
    detection = _det(_gps(_ORIGIN_LAT, _ORIGIN_LON))

    [result] = locate_faults([detection], layout, mode="grid")

    assert result.panel_id == "R1-C1"
    assert result.panel_index == (0, 0)
    assert result.confidence == pytest.approx(1.0)


def test_grid_locate_far_corner():
    """Detection at the far-corner panel GPS → R2-C2."""
    layout = _grid_layout()
    detection = _det(_gps(_ORIGIN_LAT - _DLAT, _ORIGIN_LON + _DLON))

    [result] = locate_faults([detection], layout, mode="grid")

    assert result.panel_id == "R2-C2"
    assert result.panel_index == (1, 1)
    assert result.confidence > 0.0


def test_numbered_locate_nearest():
    """Detection GPS closest to panel A-042 → panel_id == 'A-042'."""
    panel_map = {
        "A-041": {"bbox_image": [0, 0, 1, 1], "center": [0, 0],
                  "gps": _gps(_ORIGIN_LAT, _ORIGIN_LON)},
        "A-042": {"bbox_image": [0, 0, 1, 1], "center": [0, 0],
                  "gps": _gps(_ORIGIN_LAT + 5 * _DLAT, _ORIGIN_LON)},
        "A-043": {"bbox_image": [0, 0, 1, 1], "center": [0, 0],
                  "gps": _gps(_ORIGIN_LAT + 10 * _DLAT, _ORIGIN_LON)},
    }
    layout = {"mode": "numbered", "total_panels": 3, "rows": 1, "panel_map": panel_map}
    # Place the detection right on A-042.
    detection = _det(_gps(_ORIGIN_LAT + 5 * _DLAT, _ORIGIN_LON))

    [result] = locate_faults([detection], layout, mode="numbered")

    assert result.panel_id == "A-042"
    # A-042 is not an R{r}-C{c} grid id → no panel_index.
    assert result.panel_index is None


def test_no_gps_returns_unknown():
    """Detection without GPS → panel_id == 'UNKNOWN', confidence == 0.0."""
    layout = _grid_layout()
    detection = _det(None)

    [result] = locate_faults([detection], layout, mode="grid")

    assert isinstance(result, LocatedFault)
    assert result.panel_id == PANEL_ID_UNKNOWN
    assert result.panel_index is None
    assert result.confidence == 0.0


def test_locate_faults_returns_one_per_detection():
    """Output list length equals input detections length, order preserved."""
    layout = _grid_layout()
    detections = [
        _det(_gps(_ORIGIN_LAT, _ORIGIN_LON)),            # R1-C1
        _det(None),                                       # UNKNOWN
        _det(_gps(_ORIGIN_LAT - _DLAT, _ORIGIN_LON + _DLON)),  # R2-C2
    ]

    results = locate_faults(detections, layout, mode="grid")

    assert len(results) == len(detections)
    assert [r.detection for r in results] == detections
    assert results[0].panel_id == "R1-C1"
    assert results[1].panel_id == PANEL_ID_UNKNOWN
    assert results[2].panel_id == "R2-C2"


def test_empty_panel_map_all_unknown():
    """An empty panel_map yields UNKNOWN for every detection (no crash)."""
    layout = {"mode": "auto-grid", "total_panels": 0, "rows": 0, "panel_map": {}}
    detections = [_det(_gps(_ORIGIN_LAT, _ORIGIN_LON)), _det(None)]

    results = locate_faults(detections, layout, mode="grid")

    assert all(r.panel_id == PANEL_ID_UNKNOWN for r in results)
    assert len(results) == 2
