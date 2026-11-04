# drone/agent/recorder.py
"""Capture recording helpers.

Pure parts (tested): write a per-frame GPS sidecar and build the capture manifest
the handoff sends to the platform. The live frame-grab loop (GStreamer/V4L2 +
thermal RAW16) is hardware glue added in main.py on the Jetson; it reuses
`build_video_pipeline`'s `tee` for the RGB track and the iTL612R SDK for thermal.
"""
from __future__ import annotations

import json
from pathlib import Path

from drone.agent.gps_inject import TelemetryFix


def write_sidecar(out_dir, frame_name: str, frame_ts: float,
                  fix: TelemetryFix | None) -> str:
    payload = {
        "frame": frame_name,
        "ts": frame_ts,
        "lat": fix.lat if fix else None,
        "lon": fix.lon if fix else None,
        "alt_rel_m": fix.alt_rel_m if fix else None,
        "gps_source": "telemetry-injected" if fix else "none",
    }
    path = Path(out_dir) / (Path(frame_name).stem + ".json")
    path.write_text(json.dumps(payload, indent=2))
    return str(path)


def build_manifest(park_id: str, frames: list[str]) -> dict:
    return {"park_id": park_id, "frame_count": len(frames), "frames": list(frames)}
