"""Tests for axalon.core.model_info and the /health model payload.

/health used to return the literal "YOLO11m" while production ran different
weights. These tests pin that the reported model comes from the checkpoint
on disk and that /health degrades to "unknown" instead of failing.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
REAL_WEIGHTS = REPO_ROOT / "ml" / "checkpoints" / "best.pt"


class FakeDetectionModel:
    """Stand-in for ultralytics.nn.tasks.DetectionModel — only `yaml` matters."""

    def __init__(self, yaml: dict) -> None:
        self.yaml = yaml
        self.names = {0: "cell"}


def _write_fake_checkpoint(path: Path, yaml: dict) -> Path:
    torch = pytest.importorskip("torch")
    ckpt = {
        "date": "2026-07-02T06:24:03",
        "version": "8.4.84",
        "model": FakeDetectionModel(yaml),
        "train_args": {"task": "detect", "model": "last.pt"},
    }
    torch.save(ckpt, path)
    return path


# ── model_display_name ────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "yaml_file,scale,expected",
    [
        ("yolo11x.yaml", "x", "YOLO11x"),
        ("yolo11.yaml", "m", "YOLO11m"),
        ("yolov8s.yaml", "s", "YOLOv8s"),
        ("rtdetr-x.yaml", None, "RT-DETR-x"),
        (None, None, None),
        ("", "x", None),
    ],
)
def test_model_display_name(yaml_file, scale, expected):
    from axalon.core.model_info import model_display_name

    assert model_display_name(yaml_file, scale) == expected


# ── describe_weights ──────────────────────────────────────────────────────────

def test_describe_weights_missing_file_returns_unknown_fields(tmp_path):
    from axalon.core.model_info import UNKNOWN, describe_weights

    info = describe_weights(tmp_path / "nope.pt")

    assert info["name"] == UNKNOWN
    assert info["exists"] is False
    assert info["size_bytes"] is None
    assert info["sha256"] is None


def test_describe_weights_reads_checkpoint_metadata(tmp_path):
    from axalon.core.model_info import describe_weights

    ckpt = _write_fake_checkpoint(
        tmp_path / "fake.pt",
        {"nc": 11, "scale": "x", "yaml_file": "yolo11x.yaml"},
    )

    info = describe_weights(ckpt)

    assert info["exists"] is True
    assert info["name"] == "YOLO11x"
    assert info["architecture"] == "yolo11x.yaml"
    assert info["task"] == "detect"
    assert info["num_classes"] == 11
    assert info["ultralytics_version"] == "8.4.84"
    assert info["trained_at"] == "2026-07-02T06:24:03"
    assert info["size_bytes"] == ckpt.stat().st_size
    expected_sha = hashlib.sha256(ckpt.read_bytes()).hexdigest()
    assert info["sha256"] == expected_sha[: len(info["sha256"])]
    assert len(info["sha256"]) == 12


def test_describe_weights_non_checkpoint_keeps_file_facts(tmp_path):
    from axalon.core.model_info import UNKNOWN, describe_weights

    junk = tmp_path / "model.engine"
    junk.write_bytes(b"not a zip checkpoint")

    info = describe_weights(junk)

    assert info["name"] == UNKNOWN
    assert info["exists"] is True
    assert info["size_bytes"] == len(b"not a zip checkpoint")
    assert info["sha256"] == hashlib.sha256(b"not a zip checkpoint").hexdigest()[:12]


@pytest.mark.skipif(not REAL_WEIGHTS.exists(), reason="checked-in weights absent")
def test_describe_weights_real_checkpoint_is_yolo11():
    from axalon.core.model_info import describe_weights

    info = describe_weights(REAL_WEIGHTS)

    assert info["name"].startswith("YOLO11")
    assert info["num_classes"] == 11


# ── get_model_info caching ────────────────────────────────────────────────────

def test_get_model_info_caches_until_file_changes(tmp_path, monkeypatch):
    from axalon.core import model_info

    ckpt = _write_fake_checkpoint(tmp_path / "c.pt", {"scale": "m", "yaml_file": "yolo11m.yaml"})
    model_info.clear_cache()
    calls = []
    real = model_info.describe_weights
    monkeypatch.setattr(model_info, "describe_weights", lambda p: calls.append(p) or real(p))

    first = model_info.get_model_info(ckpt)
    second = model_info.get_model_info(ckpt)
    assert first == second
    assert len(calls) == 1

    _write_fake_checkpoint(ckpt, {"scale": "x", "yaml_file": "yolo11x.yaml"})
    third = model_info.get_model_info(ckpt)
    assert len(calls) == 2
    assert third["name"] == "YOLO11x"


# ── /health ───────────────────────────────────────────────────────────────────

def test_health_reports_model_info_fields(client):
    r = client.get("/health")

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    info = body["model_info"]
    for key in (
        "name", "architecture", "task", "num_classes", "ultralytics_version",
        "trained_at", "weights_path", "exists", "size_bytes", "size_mb", "sha256",
    ):
        assert key in info
    assert body["model"] == info["name"]
    assert body["weights"] == info["weights_path"]
    if REAL_WEIGHTS.exists():
        assert info["exists"] is True
        assert info["size_bytes"] == REAL_WEIGHTS.stat().st_size
        assert len(info["sha256"]) == 12


def test_health_falls_back_when_weights_missing(client, monkeypatch, tmp_path):
    from axalon.api.routers import health

    monkeypatch.setattr(health, "MODEL_WEIGHTS", tmp_path / "missing.pt")

    r = client.get("/health")

    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["model"] == "unknown"
    assert body["model_info"]["exists"] is False
    assert body["model_info"]["sha256"] is None


def test_health_never_fails_when_model_info_raises(client, monkeypatch):
    from axalon.api.routers import health

    def boom(_path):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(health, "get_model_info", boom)

    r = client.get("/health")

    assert r.status_code == 200
    assert r.json()["model"] == "unknown"
