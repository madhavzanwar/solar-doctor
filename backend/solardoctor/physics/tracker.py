"""Single-axis tracker plants: the fixed-tilt PVWatts baseline does not apply to them.

``plants`` has no mount/tracking column (and no migration was added), so the PVDAQ importer
(``solardoctor.seed.pvdaq``) appends ``TRACKER_MARKER`` to ``plants.location``. ``is_tracker_plant`` reads
that marker. If a mount column is ever added, only this function needs to change.

Policy (one rule, every endpoint): wherever the API is asked for a physics baseline that would be computed
from the plant's tilt/azimuth (forecast generate, probabilistic forecast, diagnosis from telemetry whose
expected power is that baseline), a tracker plant gets **HTTP 422** with
``detail = {"status": "baseline_unsupported_for_trackers", "message": ...}``. No deficit alert is ever raised
from the fixed-tilt baseline for such a plant. Values the caller supplies itself are not baseline output and
are used as given. A pvlib single-axis model was evaluated against real PVDAQ 9068 data and NOT enabled
(see docs/solardoctor/DECISIONS.md, row E13).
"""
from __future__ import annotations

import re
from typing import Optional

from fastapi import HTTPException

TRACKER_MARKER = "[single-axis tracker, fixed-tilt baseline invalid]"
BASELINE_UNSUPPORTED_STATUS = "baseline_unsupported_for_trackers"


# Tolerant to case, whitespace and punctuation variants ("Single Axis Tracker - fixed tilt baseline invalid").
_MARKER_RE = re.compile(
    r"\[?\s*single[\W_]*axis[\W_]+tracker[\W_]+fixed[\W_]*tilt[\W_]+baseline[\W_]+invalid\s*\]?", re.IGNORECASE)
_LOCATION_MAX = 512  # plants.location length


def has_tracker_marker(location: object) -> bool:
    return isinstance(location, str) and _MARKER_RE.search(location) is not None


def is_tracker_plant(plant) -> bool:
    """True when the plant is flagged as a single-axis tracker (marker in ``location``, variants tolerated)."""
    return has_tracker_marker(getattr(plant, "location", None))


def with_marker(location: Optional[str]) -> str:
    """``location`` with any marker variant removed and the canonical marker appended (fits 512 chars)."""
    base = _MARKER_RE.sub("", location or "").strip()
    base = base[: _LOCATION_MAX - len(TRACKER_MARKER) - 1].rstrip()
    return f"{base} {TRACKER_MARKER}".strip()


class BaselineUnsupportedForTrackers(HTTPException):
    """422 for any request that needs the fixed-tilt expected-power baseline of a tracker plant."""

    def __init__(self, plant=None) -> None:
        name = getattr(plant, "name", None)
        super().__init__(
            422,
            detail={
                "status": BASELINE_UNSUPPORTED_STATUS,
                "message": (
                    f"Plant {name!r} is a single-axis tracker; the fixed-tilt expected-power baseline is not "
                    "valid for it, so no baseline, forecast or baseline-derived alert is produced."
                ),
            },
        )


def require_fixed_tilt_baseline(plant) -> None:
    """Raise ``BaselineUnsupportedForTrackers`` for tracker plants."""
    if is_tracker_plant(plant):
        raise BaselineUnsupportedForTrackers(plant)
