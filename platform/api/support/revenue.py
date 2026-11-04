"""Estimated daily revenue loss per inspection, for the operator UI.

The formula lives in `axalon.reporting.report.compute_revenue_loss` (the same
number printed in the PDF/Excel reports); this module only feeds it the
persisted Detection rows and the `economics` block from settings.yaml.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

from axalon.db.models import Detection
from axalon.reporting.report import compute_revenue_loss

logger = logging.getLogger("axalon.api")

_SETTINGS_PATH = Path(__file__).resolve().parents[2] / "config" / "settings.yaml"

# compute_revenue_loss prices energy in USD (`cost_per_kwh_usd`).
REVENUE_CURRENCY = "USD"

_LOSS_SEVERITIES = ("CRITICAL", "HIGH")


def load_economics(settings_path: Path | None = None) -> dict:
    """Return the `economics` block of settings.yaml, or {} if unavailable.

    An empty dict lets compute_revenue_loss fall back to its own defaults.
    """
    path = settings_path or _SETTINGS_PATH
    try:
        with open(path) as f:
            data = yaml.safe_load(f) or {}
    except FileNotFoundError:
        return {}
    except (OSError, yaml.YAMLError):
        logger.exception("Failed to read economics from %s", path)
        return {}
    economics = data.get("economics") if isinstance(data, dict) else None
    return dict(economics) if isinstance(economics, dict) else {}


def revenue_loss_by_inspection(session, inspection_ids: list[str]) -> dict[str, float]:
    """Map each inspection id → estimated daily revenue loss (USD).

    One query for all ids; inspections without CRITICAL/HIGH faults map to 0.0.
    """
    if not inspection_ids:
        return {}
    rows = (
        session.query(Detection.inspection_id, Detection.panel_id, Detection.severity)
        .filter(
            Detection.inspection_id.in_(inspection_ids),
            Detection.severity.in_(_LOSS_SEVERITIES),
        )
        .all()
    )
    by_inspection: dict[str, list[dict]] = {i: [] for i in inspection_ids}
    for inspection_id, panel_id, severity in rows:
        by_inspection[inspection_id].append({"panel_id": panel_id, "severity": severity})
    economics = load_economics()
    return {
        inspection_id: compute_revenue_loss(dets, economics)
        for inspection_id, dets in by_inspection.items()
    }


__all__ = ["REVENUE_CURRENCY", "load_economics", "revenue_loss_by_inspection"]
