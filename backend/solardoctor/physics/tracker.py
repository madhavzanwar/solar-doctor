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

from fastapi import HTTPException

TRACKER_MARKER = "[single-axis tracker, fixed-tilt baseline invalid]"
BASELINE_UNSUPPORTED_STATUS = "baseline_unsupported_for_trackers"


def is_tracker_plant(plant) -> bool:
    """True when the plant is flagged as a single-axis tracker (marker at the end of ``location``)."""
    loc = getattr(plant, "location", None)
    return isinstance(loc, str) and TRACKER_MARKER in loc


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
