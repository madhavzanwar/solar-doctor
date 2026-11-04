# drone/tests/test_recorder.py
import json
from pathlib import Path
from drone.agent.gps_inject import TelemetryFix
from drone.agent.recorder import write_sidecar, build_manifest


def test_write_sidecar_embeds_gps(tmp_path):
    fix = TelemetryFix(ts=100.5, lat=28.41, lon=77.10, alt_rel_m=40.0)
    p = write_sidecar(tmp_path, frame_name="img_001.jpg", frame_ts=100.6, fix=fix)
    data = json.loads(Path(p).read_text())
    assert data["frame"] == "img_001.jpg"
    assert data["lat"] == 28.41
    assert data["alt_rel_m"] == 40.0
    assert data["gps_source"] == "telemetry-injected"


def test_write_sidecar_marks_missing_gps(tmp_path):
    p = write_sidecar(tmp_path, frame_name="img_002.jpg", frame_ts=999.0, fix=None)
    data = json.loads(Path(p).read_text())
    assert data["gps_source"] == "none"
    assert data["lat"] is None


def test_build_manifest_lists_frames():
    m = build_manifest(park_id="park-7", frames=["img_001.jpg", "img_002.jpg"])
    assert m["park_id"] == "park-7"
    assert m["frame_count"] == 2
    assert "img_001.jpg" in m["frames"]
