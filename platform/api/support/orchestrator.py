"""Lazily-constructed singleton InspectionOrchestrator.

Kept in its own module so job execution can depend on it without importing
the whole deps barrel (which would be circular).
"""
from __future__ import annotations

from axalon.pipeline.orchestrator import InspectionOrchestrator

from axalon.api.support.paths import OUTPUT_DIR

_detector: InspectionOrchestrator | None = None


def get_orchestrator() -> InspectionOrchestrator:
    global _detector
    if _detector is None:
        _detector = InspectionOrchestrator(output_dir=OUTPUT_DIR)
    return _detector


__all__ = ["get_orchestrator"]
