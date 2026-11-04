"""
train_ultralytics.py tests — run with:
    PYTHONSAFEPATH=1 python3 tests/test_train_ultralytics.py
"""
from __future__ import annotations
import sys
import os
from unittest.mock import patch, MagicMock

import platform
import uuid

_HERE = os.path.abspath(os.path.dirname(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
sys.path = [_ROOT] + [p for p in sys.path if os.path.abspath(p) != _ROOT]

from pathlib import Path
import yaml

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"
_results: list[tuple[str, bool, str]] = []


def test(name: str):
    def decorator(fn):
        try:
            fn()
            _results.append((name, True, ""))
            print(f"  [{PASS}] {name}")
        except Exception as exc:
            _results.append((name, False, str(exc)))
            print(f"  [{FAIL}] {name}: {exc}")
        return fn
    return decorator


from ml.scripts.train_ultralytics import load_training_config, build_model, run_training

ROOT = Path(_ROOT)


@test("load_training_config reads yolo11x config")
def _():
    cfg = load_training_config(ROOT / "ml/configs/thermal_yolo11x.yaml")
    assert cfg["model"] == "yolo11x.pt"
    assert cfg["dataset_yaml"] == "ml/thermal_dataset.yaml"


@test("load_training_config reads rtdetr config")
def _():
    cfg = load_training_config(ROOT / "ml/configs/thermal_rtdetr_x.yaml")
    assert cfg["model"] == "rtdetr-x.pt"


@test("build_model('yolo11x.pt') lazily imports ultralytics.YOLO")
def _():
    with patch("ultralytics.YOLO") as mock_yolo:
        mock_yolo.return_value = MagicMock()
        build_model("yolo11x.pt")
        mock_yolo.assert_called_once_with("yolo11x.pt")


@test("build_model('rtdetr-x.pt') lazily imports ultralytics.RTDETR")
def _():
    with patch("ultralytics.RTDETR") as mock_rtdetr:
        mock_rtdetr.return_value = MagicMock()
        build_model("rtdetr-x.pt")
        mock_rtdetr.assert_called_once_with("rtdetr-x.pt")


@test("run_training calls model.train() with config's hyperparameters")
def _():
    cfg_path = ROOT / "ml/configs/thermal_yolo11x.yaml"
    cfg = yaml.safe_load(cfg_path.read_text())
    with patch("ml.scripts.train_ultralytics.build_model") as mock_build:
        mock_model = MagicMock()
        mock_build.return_value = mock_model
        run_training(cfg_path)
        mock_model.train.assert_called_once()
        kwargs = mock_model.train.call_args.kwargs
        assert kwargs["data"] == cfg["dataset_yaml"]
        assert kwargs["epochs"] == cfg["epochs"]
        assert kwargs["imgsz"] == cfg["imgsz"]
        assert "resume" not in kwargs


@test("build_model(resume_from=...) loads the checkpoint instead of the config's weights")
def _():
    with patch("ultralytics.YOLO") as mock_yolo:
        mock_yolo.return_value = MagicMock()
        build_model("yolo11x.pt", resume_from="/mnt/dataset/runs/yolo11x/weights/last.pt")
        mock_yolo.assert_called_once_with("/mnt/dataset/runs/yolo11x/weights/last.pt")


@test("run_training(resume_from=...) passes resume=True to model.train()")
def _():
    cfg_path = ROOT / "ml/configs/thermal_yolo11x.yaml"
    with patch("ml.scripts.train_ultralytics.build_model") as mock_build:
        mock_model = MagicMock()
        mock_build.return_value = mock_model
        run_training(cfg_path, resume_from="/mnt/dataset/runs/yolo11x/weights/last.pt")
        mock_build.assert_called_once_with("yolo11x.pt", resume_from="/mnt/dataset/runs/yolo11x/weights/last.pt")
        kwargs = mock_model.train.call_args.kwargs
        assert kwargs["resume"] is True


print("\n" + "═" * 65)
passed = sum(1 for _, ok, _ in _results if ok)
failed = sum(1 for _, ok, _ in _results if not ok)
print(f"  Results: {passed} passed, {failed} failed  ({len(_results)} total)")
if failed:
    for name, ok, err in _results:
        if not ok:
            print(f"    - {name}: {err}")
sys.exit(0 if failed == 0 else 1)
