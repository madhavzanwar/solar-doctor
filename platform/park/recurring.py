"""Recurring-fault aggregation helpers for panels seen in multiple inspections."""
from __future__ import annotations

from typing import Any

_RANK_TO_SEVERITY = {4: "CRITICAL", 3: "HIGH", 2: "MEDIUM", 1: "LOW"}


def build_recurring(rows: list[Any]) -> list[dict]:
    """Normalize SQL rows into recurring-panel records."""
    result = []
    for row in rows:
        raw_classes = (row.classes or "").split(",")
        classes = list(dict.fromkeys(c.strip() for c in raw_classes if c.strip()))
        result.append({
            "panel_id": row.panel_id,
            "inspection_count": int(row.inspection_count or 0),
            "worst_severity": _RANK_TO_SEVERITY.get(int(row.sev_rank or 1), "LOW"),
            "classes": classes,
            "first_seen": str(row.first_seen) if row.first_seen else None,
            "last_seen": str(row.last_seen) if row.last_seen else None,
        })
    return result
