# drone/agent/gps_inject.py
"""Match a saved frame's capture timestamp to the nearest telemetry GPS sample.

The thermal core has no EXIF GPS (see drone-camera-specs), so the agent keeps a
rolling telemetry log during flight and, post-flight, stamps each frame with the
closest-in-time fix. Pure + tested; the file IO that uses it lives in recorder.py.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TelemetryFix:
    ts: float
    lat: float
    lon: float
    alt_rel_m: float


def nearest_fix(log: list[TelemetryFix], frame_ts: float,
                tolerance_s: float) -> TelemetryFix | None:
    if not log:
        return None
    best = min(log, key=lambda f: abs(f.ts - frame_ts))
    return best if abs(best.ts - frame_ts) <= tolerance_s else None
