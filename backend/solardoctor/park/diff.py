"""
diff.py — Pure comparison logic for Axalon inspection diffs.

Given two lists of detection dicts (each with at minimum panel_id, class, severity),
build_diff() returns new / resolved / changed grouped by (panel_id, class) key.
"""

from __future__ import annotations

from typing import Any


def build_diff(
    detections_a: list[dict[str, Any]],
    detections_b: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Compare two inspection detection sets by panel_id + class.

    Args:
        detections_a: Detections from inspection A. Each dict must have at minimum
                      ``panel_id``, ``class``, and ``severity`` keys.
        detections_b: Detections from inspection B (same schema).

    Returns:
        A dict with three keys:
        - ``new``:      items in B but not in A (by panel_id+class key)
        - ``resolved``: items in A but not in B
        - ``changed``:  same panel+class present in both, but with different severity

        Each item is a dict::

            {
                "panel_id":  str,
                "class":     str,
                "severity_a": str | None,   # None for new items
                "severity_b": str | None,   # None for resolved items
            }
    """
    # Build lookup: (panel_id, class) -> severity
    def _index(detections: list[dict[str, Any]]) -> dict[tuple[str, str], str]:
        idx: dict[tuple[str, str], str] = {}
        for det in detections:
            panel_id = det.get("panel_id") or "R?-C?"
            cls = det.get("class") or ""
            if not cls:
                continue
            key = (panel_id, cls)
            # Keep the highest-severity entry for duplicate (panel_id, class) pairs
            if key not in idx:
                idx[key] = det.get("severity") or ""
        return idx

    idx_a = _index(detections_a)
    idx_b = _index(detections_b)

    keys_a = set(idx_a.keys())
    keys_b = set(idx_b.keys())

    new_items: list[dict[str, Any]] = []
    for panel_id, cls in sorted(keys_b - keys_a):
        new_items.append({
            "panel_id": panel_id,
            "class": cls,
            "severity_a": None,
            "severity_b": idx_b[(panel_id, cls)],
        })

    resolved_items: list[dict[str, Any]] = []
    for panel_id, cls in sorted(keys_a - keys_b):
        resolved_items.append({
            "panel_id": panel_id,
            "class": cls,
            "severity_a": idx_a[(panel_id, cls)],
            "severity_b": None,
        })

    changed_items: list[dict[str, Any]] = []
    for panel_id, cls in sorted(keys_a & keys_b):
        sev_a = idx_a[(panel_id, cls)]
        sev_b = idx_b[(panel_id, cls)]
        if sev_a != sev_b:
            changed_items.append({
                "panel_id": panel_id,
                "class": cls,
                "severity_a": sev_a,
                "severity_b": sev_b,
            })

    return {
        "new": new_items,
        "resolved": resolved_items,
        "changed": changed_items,
    }
