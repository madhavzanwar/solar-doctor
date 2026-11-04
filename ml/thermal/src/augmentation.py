"""
augmentation.py — Albumentations offline 2× augmentation pipeline for thermal IR images.

Call `run_offline_augmentation()` from Notebook 02 to double the training set
before handing it off to YOLO training.

Design notes
------------
* `hsv_h` and `hsv_s` are set to 0 in the YOLO config because thermal images
  carry no meaningful hue or saturation signal.  The Albumentations pipeline
  mirrors this: no HueSaturationValue transform is included.
* CoarseDropout simulates sensor read-out noise / partial occlusion — a realistic
  degradation mode in uncooled microbolometer arrays.
* Bounding boxes are passed through the pipeline using Albumentations'
  built-in `bboxes` support (format='yolo') so they stay consistent with image crops.
"""

from __future__ import annotations

import random
import shutil
from pathlib import Path

import albumentations as A
import cv2
import numpy as np
from tqdm import tqdm

from src.utils import read_yolo_label, write_yolo_label, get_logger

logger = get_logger(__name__)


# ── Pipeline definition ─────────────────────────────────────────────────────

def build_thermal_augmentation_pipeline(target_size: int = 640) -> A.Compose:
    """Return the Albumentations pipeline for thermal IR images.

    bbox_params uses 'yolo' format so normalised (cx, cy, w, h) annotations
    survive geometric transforms without manual coordinate recalculation.
    """
    return A.Compose(
        [
            A.HorizontalFlip(p=0.5),
            A.VerticalFlip(p=0.5),
            A.RandomRotate90(p=0.5),
            A.ShiftScaleRotate(
                shift_limit=0.05,
                scale_limit=0.1,
                rotate_limit=15,
                border_mode=cv2.BORDER_REFLECT_101,
                p=0.6,
            ),
            A.Perspective(scale=(0.04, 0.08), p=0.3),
            A.RandomBrightnessContrast(
                brightness_limit=0.2, contrast_limit=0.2, p=0.6
            ),
            A.GaussNoise(var_limit=(10.0, 50.0), p=0.4),
            A.GaussianBlur(blur_limit=(3, 5), p=0.3),
            A.RandomGamma(gamma_limit=(80, 120), p=0.4),
            A.CLAHE(clip_limit=4.0, tile_grid_size=(8, 8), p=0.3),
            A.CoarseDropout(
                num_holes_range=(4, 8),
                hole_height_range=(8, 32),
                hole_width_range=(8, 32),
                fill=0,
                p=0.3,
            ),
            A.Resize(target_size, target_size),
        ],
        bbox_params=A.BboxParams(
            format="yolo",
            label_fields=["class_labels"],
            min_visibility=0.3,       # drop boxes that become < 30 % visible
            clip=True,
        ),
    )


# ── Offline augmentation runner ─────────────────────────────────────────────

def run_offline_augmentation(
    images_dir: Path,
    labels_dir: Path,
    out_images_dir: Path,
    out_labels_dir: Path,
    multiplier: int = 2,
    target_size: int = 640,
    seed: int = 42,
) -> int:
    """Generate `multiplier - 1` augmented copies per image and write alongside originals.

    Parameters
    ----------
    images_dir:     source images directory
    labels_dir:     source labels directory (YOLO .txt files)
    out_images_dir: destination for images (originals copied + augmented)
    out_labels_dir: destination for labels
    multiplier:     total copies per original (2 → 1 original + 1 augmented)
    target_size:    resize target (pixels)
    seed:           random seed

    Returns the total number of image files written (originals + augmented).
    """
    random.seed(seed)
    np.random.seed(seed)

    pipeline = build_thermal_augmentation_pipeline(target_size)
    out_images_dir.mkdir(parents=True, exist_ok=True)
    out_labels_dir.mkdir(parents=True, exist_ok=True)

    img_paths = sorted(
        p for p in images_dir.iterdir()
        if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}
    )

    written = 0
    for img_path in tqdm(img_paths, desc="Augmenting", unit="img"):
        label_path = labels_dir / (img_path.stem + ".txt")
        boxes = read_yolo_label(label_path)

        img = cv2.imread(str(img_path))
        if img is None:
            logger.warning("Skipping unreadable image: %s", img_path)
            continue

        # ── Copy original ────────────────────────────────────────────────
        dest_img = out_images_dir / img_path.name
        dest_lbl = out_labels_dir / (img_path.stem + ".txt")
        shutil.copy2(img_path, dest_img)
        write_yolo_label(dest_lbl, boxes)
        written += 1

        # ── Augmented copies ─────────────────────────────────────────────
        for aug_idx in range(1, multiplier):
            bboxes   = [(cx, cy, w, h) for _, cx, cy, w, h in boxes]
            cl_ids   = [cid for cid, *_ in boxes]

            result = pipeline(
                image=img,
                bboxes=bboxes,
                class_labels=cl_ids,
            )

            aug_boxes = [
                (cid, cx, cy, w, h)
                for cid, (cx, cy, w, h) in zip(
                    result["class_labels"], result["bboxes"]
                )
            ]

            stem = f"{img_path.stem}_aug{aug_idx}"
            aug_img_path = out_images_dir / f"{stem}{img_path.suffix}"
            aug_lbl_path = out_labels_dir / f"{stem}.txt"

            cv2.imwrite(str(aug_img_path), result["image"])
            write_yolo_label(aug_lbl_path, aug_boxes)
            written += 1

    logger.info("Augmentation complete: %d images written to %s", written, out_images_dir)
    return written
