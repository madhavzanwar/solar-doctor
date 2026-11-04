"""
yolo_to_coco.py tests — run with:
    PYTHONSAFEPATH=1 python3 tests/test_yolo_to_coco.py
"""
from __future__ import annotations
import sys
import os
import tempfile

import platform
import uuid

_HERE = os.path.abspath(os.path.dirname(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, ".."))
sys.path = [_ROOT] + [p for p in sys.path if os.path.abspath(p) != _ROOT]

from pathlib import Path
import numpy as np
import cv2

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


from ml.scripts.yolo_to_coco import yolo_split_to_coco
from ml.src.utils import CANONICAL_CLASSES


def _make_fixture_split(tmpdir: Path) -> tuple[Path, Path]:
    images_dir = tmpdir / "images"
    labels_dir = tmpdir / "labels"
    images_dir.mkdir()
    labels_dir.mkdir()

    img = np.zeros((100, 200, 3), dtype=np.uint8)
    cv2.imwrite(str(images_dir / "a.jpg"), img)
    (labels_dir / "a.txt").write_text("3 0.5 0.5 0.4 0.2\n4 0.25 0.25 0.1 0.1\n")

    cv2.imwrite(str(images_dir / "b.jpg"), img)
    (labels_dir / "b.txt").write_text("")  # image with no boxes

    return images_dir, labels_dir


@test("yolo_split_to_coco produces correct top-level COCO keys")
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        images_dir, labels_dir = _make_fixture_split(Path(tmpdir))
        coco = yolo_split_to_coco(images_dir, labels_dir, CANONICAL_CLASSES)
        assert set(coco.keys()) == {"images", "annotations", "categories"}


@test("yolo_split_to_coco produces one image entry per source image")
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        images_dir, labels_dir = _make_fixture_split(Path(tmpdir))
        coco = yolo_split_to_coco(images_dir, labels_dir, CANONICAL_CLASSES)
        assert len(coco["images"]) == 2


@test("yolo_split_to_coco converts normalized YOLO box to pixel xywh")
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        images_dir, labels_dir = _make_fixture_split(Path(tmpdir))
        coco = yolo_split_to_coco(images_dir, labels_dir, CANONICAL_CLASSES)
        anns = [a for a in coco["annotations"] if a["category_id"] == 3]
        assert len(anns) == 1
        x, y, w, h = anns[0]["bbox"]
        # image is 200x100; box cx=0.5,cy=0.5,w=0.4,h=0.2 -> x1=60,y1=40,w=80,h=20
        assert abs(x - 60) < 1e-3 and abs(y - 40) < 1e-3
        assert abs(w - 80) < 1e-3 and abs(h - 20) < 1e-3


@test("yolo_split_to_coco categories match CANONICAL_CLASSES order (0-indexed)")
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        images_dir, labels_dir = _make_fixture_split(Path(tmpdir))
        coco = yolo_split_to_coco(images_dir, labels_dir, CANONICAL_CLASSES)
        ids_to_names = {c["id"]: c["name"] for c in coco["categories"]}
        for i, name in enumerate(CANONICAL_CLASSES):
            assert ids_to_names[i] == name


@test("yolo_split_to_coco handles an image with zero boxes")
def _():
    with tempfile.TemporaryDirectory() as tmpdir:
        images_dir, labels_dir = _make_fixture_split(Path(tmpdir))
        coco = yolo_split_to_coco(images_dir, labels_dir, CANONICAL_CLASSES)
        b_image_id = next(i["id"] for i in coco["images"] if i["file_name"] == "b.jpg")
        anns_for_b = [a for a in coco["annotations"] if a["image_id"] == b_image_id]
        assert anns_for_b == []


print("\n" + "═" * 65)
passed = sum(1 for _, ok, _ in _results if ok)
failed = sum(1 for _, ok, _ in _results if not ok)
print(f"  Results: {passed} passed, {failed} failed  ({len(_results)} total)")
if failed:
    for name, ok, err in _results:
        if not ok:
            print(f"    - {name}: {err}")
sys.exit(0 if failed == 0 else 1)
