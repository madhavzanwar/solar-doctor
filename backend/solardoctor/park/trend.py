"""Trend aggregation helpers for per-inspection severity charts."""
from __future__ import annotations

from typing import Any


def build_trend(rows: list[Any]) -> list[dict]:
    """Normalize SQL rows into oldest-first severity-count trend points."""
    result = []
    for row in rows:
        result.append({
            "inspection_id": row.id,
            "date": str(row.flight_date) if row.flight_date else None,
            "CRITICAL": int(row.critical_count or 0),
            "HIGH": int(row.high_count or 0),
            "MEDIUM": int(row.medium_count or 0),
            "LOW": int(row.low_count or 0),
        })
    return sorted(result, key=lambda item: item["date"] or "")
