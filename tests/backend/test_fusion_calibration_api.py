"""API, CLI and pipeline wiring for the thermal↔RGB rig calibration."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import cv2
import numpy as np
import pytest

from axalon.core.fusion_calibration import CALIBRATION_FORMAT, load_calibration_file

REPO_ROOT = Path(__file__).resolve().parents[2]
_H = [[6.0, 0.1, 150.0], [-0.05, 6.0, 120.0], [0.0, 0.0, 1.0]]


def _doc(**overrides) -> dict:
    doc = {
        "format": CALIBRATION_FORMAT,
        "version": 1,
        "rig_id": "AXL-RIG-API",
        "thermal_size": [640, 512],
        "rgb_size": [4000, 3000],
        "homography": _H,
        "rms_error_px": 1.25,
        "created_at": "2026-09-02T08:30:00+00:00",
    }
    doc.update(overrides)
    return doc


def _upload(client, payload: bytes, name: str = "cal.json"):
    return client.post(
        "/settings/fusion-calibration",
        files={"file": (name, payload, "application/json")},
    )


# ── API ──────────────────────────────────────────────────────────────────────

def test_get_calibration_when_none_configured(client, monkeypatch):
    monkeypatch.delenv("AXALON_FUSION_CALIBRATION", raising=False)
    r = client.get("/settings/fusion-calibration")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is False
    assert body["calibration"] is None


def test_upload_valid_calibration_then_get_summary(client, monkeypatch):
    monkeypatch.delenv("AXALON_FUSION_CALIBRATION", raising=False)

    r = _upload(client, json.dumps(_doc()).encode())
    assert r.status_code == 201, r.text
    assert r.json()["calibration"]["rig_id"] == "AXL-RIG-API"

    body = client.get("/settings/fusion-calibration").json()
    assert body["configured"] is True
    assert body["source"] == "database"
    assert body["calibration"]["rig_id"] == "AXL-RIG-API"
    assert body["calibration"]["rms_error_px"] == pytest.approx(1.25)
    assert body["calibration"]["thermal_size"] == [640, 512]


@pytest.mark.parametrize(
    "payload",
    [
        b"not json",
        json.dumps(_doc(homography=[[1, 0], [0, 1]])).encode(),
        json.dumps(_doc(rig_id="")).encode(),
    ],
)
def test_upload_invalid_calibration_is_rejected(client, payload):
    r = _upload(client, payload)
    assert r.status_code == 400
    assert r.json()["detail"]


def test_upload_rejects_oversized_file(client):
    r = _upload(client, b" " * (300 * 1024))
    assert r.status_code == 413


def test_get_reports_env_override(client, monkeypatch, tmp_path):
    path = tmp_path / "env_cal.json"
    path.write_text(json.dumps(_doc(rig_id="ENV-RIG")))
    monkeypatch.setenv("AXALON_FUSION_CALIBRATION", str(path))

    body = client.get("/settings/fusion-calibration").json()

    assert body["source"] == "env"
    assert body["calibration"]["rig_id"] == "ENV-RIG"


# ── CLI tool ─────────────────────────────────────────────────────────────────

def _load_cli():
    spec = importlib.util.spec_from_file_location(
        "calibrate_fusion", REPO_ROOT / "scripts" / "calibrate_fusion.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _pairs() -> list[dict]:
    H = np.array(_H)
    pts = [[40, 40], [600, 40], [600, 470], [40, 470], [320, 256], [200, 380]]
    rgb = cv2.perspectiveTransform(np.array([pts], dtype=np.float64), H)[0]
    return [{"thermal": p, "rgb": r.tolist()} for p, r in zip(pts, rgb)]


def test_cli_computes_calibration_from_json_pairs(tmp_path, capsys):
    cli = _load_cli()
    src = tmp_path / "pairs.json"
    src.write_text(json.dumps({
        "rig_id": "CLI-RIG", "thermal_size": [640, 512], "rgb_size": [4000, 3000],
        "pairs": _pairs(),
    }))
    out = tmp_path / "cal.json"

    code = cli.main(["points", str(src), "-o", str(out)])

    assert code == 0
    cal = load_calibration_file(out)
    assert cal.rig_id == "CLI-RIG"
    assert cal.rms_error_px < 0.05
    assert "RMS" in capsys.readouterr().out


def test_cli_accepts_csv_pairs(tmp_path):
    cli = _load_cli()
    src = tmp_path / "pairs.csv"
    lines = ["thermal_x,thermal_y,rgb_x,rgb_y"]
    lines += [f"{p['thermal'][0]},{p['thermal'][1]},{p['rgb'][0]},{p['rgb'][1]}" for p in _pairs()]
    src.write_text("\n".join(lines) + "\n")
    out = tmp_path / "cal.json"

    code = cli.main([
        "points", str(src), "-o", str(out), "--rig-id", "CSV-RIG",
        "--thermal-size", "640x512", "--rgb-size", "4000x3000",
    ])

    assert code == 0
    assert load_calibration_file(out).rig_id == "CSV-RIG"


def test_cli_rejects_degenerate_input(tmp_path, capsys):
    cli = _load_cli()
    src = tmp_path / "pairs.json"
    src.write_text(json.dumps({
        "rig_id": "BAD", "thermal_size": [640, 512], "rgb_size": [4000, 3000],
        "pairs": _pairs()[:3],
    }))
    out = tmp_path / "cal.json"

    code = cli.main(["points", str(src), "-o", str(out)])

    assert code != 0
    assert not out.exists()
    assert "at least 4" in capsys.readouterr().err


def test_cli_refuses_rms_above_limit(tmp_path, capsys):
    cli = _load_cli()
    rng = np.random.default_rng(1)
    pairs = [  # jitter every point independently so no clean homography exists
        {"thermal": p["thermal"], "rgb": [p["rgb"][0] + rng.uniform(-9, 9), p["rgb"][1]]}
        for p in _pairs()
    ]
    src = tmp_path / "pairs.json"
    src.write_text(json.dumps({
        "rig_id": "NOISY", "thermal_size": [640, 512], "rgb_size": [4000, 3000], "pairs": pairs,
    }))
    out = tmp_path / "cal.json"

    code = cli.main(["points", str(src), "-o", str(out), "--max-rms", "0.5",
                     "--ransac-threshold", "50"])

    assert code != 0
    assert not out.exists()


# ── pipeline records which fusion tier was used ──────────────────────────────

class _FakeDetector:
    def predict(self, _path):
        return [{
            "class": "hot-spot-high", "class_id": 10, "confidence": 0.9,
            "bbox": [100, 100, 140, 140], "bbox_norm": [0.2, 0.2, 0.06, 0.08],
            "severity": "CRITICAL", "color_bgr": (0, 0, 255),
        }]

    def detection_summary(self, detections):
        return {"total": len(detections)}


def test_inspect_pair_records_calibration_fusion_mode(tmp_path):
    from axalon.core.fusion import ImageFusion
    from axalon.core.fusion_calibration import parse_calibration
    from axalon.pipeline.orchestrator import InspectionOrchestrator

    thermal = tmp_path / "t.jpg"
    rgb = tmp_path / "r.jpg"
    cv2.imwrite(str(thermal), np.zeros((512, 640, 3), dtype=np.uint8))
    cv2.imwrite(str(rgb), np.zeros((3000, 4000, 3), dtype=np.uint8))

    orch = object.__new__(InspectionOrchestrator)
    orch.detector = _FakeDetector()
    orch.fusion = ImageFusion(mode="auto", calibration=parse_calibration(_doc()))
    orch.output_dir = tmp_path / "out"

    result = orch.inspect_pair(thermal, rgb, park_id="P")

    assert result["fusion_mode"] == "calibration"
