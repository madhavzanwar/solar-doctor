"""Panel-grid aggregator — turns a flat list of detections into a per-panel grid summary.

Pure function. Used by the FastAPI /park/{id}/grid endpoint and exercised
directly by pytest.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

from axalon.core.temp_extractor import TEMP_FIELDS

_SEVERITY_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
_PANEL_ID_RE = re.compile(r"R(\d+)-C(\d+)")


def _worst(severities: Iterable[str | None]) -> str | None:
    valid = [s for s in severities if s in _SEVERITY_RANK]
    if not valid:
        return None
    return max(valid, key=lambda s: _SEVERITY_RANK[s])


def _first_non_null(values: Iterable[Any]) -> Any:
    for v in values:
        if v is not None:
            return v
    return None


def _derive_dims_from_panel_ids(detections: list[dict]) -> tuple[int, int]:
    max_r = max_c = 0
    for d in detections:
        pid = d.get("panel_id")
        if not pid:
            continue
        m = _PANEL_ID_RE.match(pid)
        if not m:
            continue
        r, c = int(m.group(1)), int(m.group(2))
        max_r = max(max_r, r)
        max_c = max(max_c, c)
    return max_r, max_c


def build_grid(
    *,
    detections: list[dict],
    park: Any,
    inspection_id: str | None,
) -> dict:
    """Aggregate detections into a per-panel grid summary.

    detections: list of dicts with keys panel_id, severity, class, confidence,
                image_id, thermal_filename, bbox, gps.
    park: object with .id, .rows, .cols (SQLAlchemy Park or SimpleNamespace).
    inspection_id: the inspection these detections belong to, or None if no inspection.
    """
    rows = int(getattr(park, "rows", 0) or 0)
    cols = int(getattr(park, "cols", 0) or 0)
    if rows == 0 or cols == 0:
        rows, cols = _derive_dims_from_panel_ids(detections)

    by_panel: dict[str, list[dict]] = {}
    for d in detections:
        pid = d.get("panel_id")
        if not pid:
            continue
        by_panel.setdefault(pid, []).append(d)

    panels: list[dict] = []
    for pid, dets in by_panel.items():
        m = _PANEL_ID_RE.match(pid)
        row, col = (int(m.group(1)) - 1, int(m.group(2)) - 1) if m else (0, 0)
        panels.append({
            "panel_id": pid,
            "row": row,
            "col": col,
            "worst_severity": _worst(d.get("severity") for d in dets),
            "detection_count": len(dets),
            "detections": [
                {
                    "class": d.get("class"),
                    "confidence": d.get("confidence"),
                    "severity": d.get("severity"),
                    "thermal_filename": d.get("thermal_filename") or (
                        f"{d['image_id']}.jpg" if d.get("image_id") else None
                    ),
                    "bbox": d.get("bbox"),
                    # Radiometric fields (°C) — None when no _temp.raw companion.
                    **{field: d.get(field) for field in TEMP_FIELDS},
                }
                for d in dets
            ],
            "gps": _first_non_null(d.get("gps") for d in dets),
        })

    return {
        "park_id": getattr(park, "id", None),
        "inspection_id": inspection_id,
        "rows": rows,
        "cols": cols,
        "panels": panels,
    }
