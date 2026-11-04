"""
yolo_to_coco.py — convert ml/data/combined (YOLO format) to COCO JSON for
Co-DETR/MMDetection training.

Usage:
    python3 -m ml.scripts.yolo_to_coco --combined-root ml/data/combined --out ml/data/combined_coco
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2

from ml.src.utils import CANONICAL_CLASSES, get_logger, read_yolo_label, yolo_to_pixel

logger = get_logger(__name__)

_IMAGE_EXTS = {".jpg", ".jpeg", ".png"}


def yolo_split_to_coco(images_dir: Path, labels_dir: Path, class_names: list[str]) -> dict:
    """Convert one YOLO-format split (images_dir/labels_dir) to a COCO dict."""
    categories = [{"id": i, "name": name} for i, name in enumerate(class_names)]
    images: list[dict] = []
    annotations: list[dict] = []
    ann_id = 1

    for image_id, img_path in enumerate(sorted(images_dir.iterdir()), start=1):
        if img_path.suffix.lower() not in _IMAGE_EXTS:
            continue
        img = cv2.imread(str(img_path))
        if img is None:
            logger.warning("Could not read image %s — skipping", img_path)
            continue
        h, w = img.shape[:2]
        images.append({"id": image_id, "file_name": img_path.name, "width": w, "height": h})

        lbl_path = labels_dir / (img_path.stem + ".txt")
        for cid, cx, cy, bw, bh in read_yolo_label(lbl_path):
            x1, y1, x2, y2 = yolo_to_pixel(cx, cy, bw, bh, w, h)
            annotations.append({
                "id": ann_id,
                "image_id": image_id,
                "category_id": cid,
                "bbox": [float(x1), float(y1), float(x2 - x1), float(y2 - y1)],
                "area": float((x2 - x1) * (y2 - y1)),
                "iscrowd": 0,
            })
            ann_id += 1

    return {"images": images, "annotations": annotations, "categories": categories}


def convert_all_splits(combined_root: Path, out_root: Path) -> None:
    """Convert train/val/test splits under combined_root to COCO JSONs under out_root."""
    out_root.mkdir(parents=True, exist_ok=True)
    for split in ("train", "val", "test"):
        images_dir = combined_root / split / "images"
        labels_dir = combined_root / split / "labels"
        if not images_dir.exists():
            logger.warning("Split %s not found under %s — skipping", split, combined_root)
            continue
        coco = yolo_split_to_coco(images_dir, labels_dir, CANONICAL_CLASSES)
        out_path = out_root / f"{split}.json"
        out_path.write_text(json.dumps(coco))
        logger.info("Wrote %s (%d images, %d annotations)", out_path, len(coco["images"]), len(coco["annotations"]))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--combined-root", default="ml/data/combined")
    parser.add_argument("--out", default="ml/data/combined_coco")
    args = parser.parse_args()
    convert_all_splits(Path(args.combined_root), Path(args.out))


if __name__ == "__main__":
    main()
