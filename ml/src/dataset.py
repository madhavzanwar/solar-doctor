"""
dataset.py — dataset scanning, class remapping, and stratified splitting.

This module is purposely framework-agnostic (no PyTorch Dataset subclass) so
it can be used from plain scripts or notebooks without importing torch.
A PyTorch Dataset wrapper is provided at the bottom for future use by the
RGB fusion model — import it only when needed to keep notebook startup fast.

Architecture note
-----------------
The function `collect_all_pairs()` returns a flat list of (image_path,
label_path, majority_class_id) tuples. Keeping this separate from the split
logic makes it easy to swap in a new dataset source (e.g. an RGB dataset)
without touching the splitting code.
"""

from __future__ import annotations

import json
import logging
import shutil
import warnings
from collections import Counter
from pathlib import Path
from typing import Sequence

import numpy as np
from sklearn.model_selection import train_test_split

from ml.src.utils import (
    CANONICAL_CLASSES,
    CLASS2ID,
    read_yolo_label,
    write_yolo_label,
    get_logger,
)

logger = get_logger(__name__)

# ── ISM class name → canonical class name ───────────────────────────────────
# InfraredSolarModules is a *classification* dataset; each image is a cropped
# module so we synthesise a whole-image YOLO box (cx=0.5, cy=0.5, w=1.0, h=1.0).
ISM_CLASSES_MAP: dict[str, str] = {
    "Cell":           "cell",
    "Cell-Multi":     "cell-multi",
    "Cracking":       "hot-spot-low",   # physical crack → thermal hot-spot
    "Hot-Spot":       "hot-spot-low",
    "Hot-Spot-Multi": "hot-spot-high",
    "Shadowing":      "vegetation-shading",
    "Diode":          "bypass-diode",
    "Diode-Multi":    "bypass-diode",
    "Vegetation":     "vegetation-shading",
    "Soiling":        "soiling",
    "Offline-Module": "offline-module",
    "No-Anomaly":     "module",          # nominal module — keep as detection target
}

# ── PV archive class name → canonical class name ────────────────────────────
# archive.zip / ImageSet uses Roboflow class names.
PV_CLASSES_MAP: dict[str, str] = {
    "MultiByPassed":         "bypass-diode",
    "MultiDiode":            "bypass-diode",
    "MultiHotSpot":          "hot-spot-high",
    "SingleByPassed":        "bypass-diode",
    "SingleDiode":           "bypass-diode",
    "SingleHotSpot":         "hot-spot-low",
    "StringOpenCircuit":     "string",
    "StringReversedPolarity":"short-circuit",
}

# ── PVMD class name → canonical class name ──────────────────────────────────
# PVMD dataset is folder-per-class classification data (Cracks/Hotspots/Shadings),
# same weak-label treatment as ISM. Mapped for consistency with ISM's existing
# conventions: cracking -> hot-spot-low (matches ISM's "Cracking" mapping),
# generic "Hotspots" (no single/multi distinction given) -> hot-spot-low as the
# conservative default, shading -> vegetation-shading.
PVMD_CLASSES_MAP: dict[str, str] = {
    "Cracks":   "hot-spot-low",
    "Hotspots": "hot-spot-low",
    "Shadings": "vegetation-shading",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _remap_class_id(
    source_id: int,
    source_names: list[str],
    classes_map: dict[str, str],
) -> int | None:
    """Map a source class integer to a canonical class integer.

    Returns None and logs a warning if the source name is unknown.
    """
    if source_id >= len(source_names):
        logger.warning("source_id %d out of range for source_names (len=%d)", source_id, len(source_names))
        return None
    source_name = source_names[source_id]
    canonical_name = classes_map.get(source_name)
    if canonical_name is None:
        logger.warning("Unknown class name %r in CLASSES_MAP — skipping", source_name)
        return None
    canonical_id = CLASS2ID.get(canonical_name)
    if canonical_id is None:
        logger.warning("Canonical name %r not in CANONICAL_CLASSES — skipping", canonical_name)
        return None
    return canonical_id


def _majority_class(boxes: list[tuple[int, float, float, float, float]]) -> int:
    """Return the most frequent class id in a label; default 0 for empty files."""
    if not boxes:
        return 0
    counts = Counter(cid for cid, *_ in boxes)
    return counts.most_common(1)[0][0]


# ── ISM dataset scanning ──────────────────────────────────────────────────────

def collect_ism_pairs(
    ism_images_dir: Path,
    metadata_json: Path,
    classes_map: dict[str, str] = ISM_CLASSES_MAP,
    generated_labels_dir: Path | None = None,
) -> list[tuple[Path, Path, int]]:
    """Scan ISM classification dataset and return (img_path, lbl_path, majority_class_id).

    Synthesises whole-image YOLO labels (cx=0.5, cy=0.5, w=1.0, h=1.0) and
    writes them to `generated_labels_dir` (defaults to labels/ sibling of images/).
    """
    if generated_labels_dir is None:
        generated_labels_dir = ism_images_dir.parent / "labels"
    generated_labels_dir.mkdir(parents=True, exist_ok=True)

    with metadata_json.open() as f:
        metadata: dict[str, dict] = json.load(f)

    pairs: list[tuple[Path, Path, int]] = []
    skipped = 0

    for entry in metadata.values():
        img_rel   = entry.get("image_filepath", "")
        anomaly   = entry.get("anomaly_class", "")
        img_path  = ism_images_dir.parent / img_rel   # e.g. InfraredSolarModules/images/63.jpg

        if not img_path.exists():
            skipped += 1
            continue

        canonical_name = classes_map.get(anomaly)
        if canonical_name is None:
            logger.warning("ISM: unknown anomaly class %r — skipping %s", anomaly, img_path.name)
            skipped += 1
            continue

        canonical_id = CLASS2ID.get(canonical_name)
        if canonical_id is None:
            logger.warning("ISM: canonical name %r not in CLASS2ID — skipping", canonical_name)
            skipped += 1
            continue

        lbl_path = generated_labels_dir / (img_path.stem + ".txt")
        write_yolo_label(lbl_path, [(canonical_id, 0.5, 0.5, 1.0, 1.0)])
        pairs.append((img_path, lbl_path, canonical_id))

    if skipped:
        logger.info("ISM: skipped %d entries (missing images or unknown classes)", skipped)
    logger.info("ISM: collected %d pairs", len(pairs))
    return pairs


# ── PVMD dataset scanning ─────────────────────────────────────────────────────

def collect_pvmd_pairs(
    pvmd_root: Path,
    classes_map: dict[str, str] = PVMD_CLASSES_MAP,
    generated_labels_dir: Path | None = None,
) -> list[tuple[Path, Path, int]]:
    """Scan PVMD folder-per-class dataset, return (img_path, lbl_path, majority_class_id).

    Same whole-image weak-label strategy as collect_ism_pairs: each crop gets
    a single synthesised YOLO box (cx=0.5, cy=0.5, w=1.0, h=1.0).
    """
    if generated_labels_dir is None:
        generated_labels_dir = pvmd_root.parent / "pvmd_labels"
    generated_labels_dir.mkdir(parents=True, exist_ok=True)

    pairs: list[tuple[Path, Path, int]] = []
    skipped = 0

    for class_name, canonical_name in classes_map.items():
        class_dir = pvmd_root / class_name
        if not class_dir.exists():
            logger.warning("PVMD: class dir %s not found — skipping", class_dir)
            continue

        canonical_id = CLASS2ID.get(canonical_name)
        if canonical_id is None:
            logger.warning("PVMD: canonical name %r not in CLASS2ID — skipping", canonical_name)
            continue

        for img_path in sorted(class_dir.iterdir()):
            if img_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
                skipped += 1
                continue
            lbl_path = generated_labels_dir / (img_path.stem + ".txt")
            write_yolo_label(lbl_path, [(canonical_id, 0.5, 0.5, 1.0, 1.0)])
            pairs.append((img_path, lbl_path, canonical_id))

    if skipped:
        logger.info("PVMD: skipped %d non-image entries", skipped)
    logger.info("PVMD: collected %d pairs", len(pairs))
    return pairs


# ── PV archive dataset scanning ───────────────────────────────────────────────

def collect_pv_pairs(
    pv_root: Path,
    pv_source_class_names: list[str],
    classes_map: dict[str, str] = PV_CLASSES_MAP,
    splits: Sequence[str] = ("train", "valid", "test"),
) -> list[tuple[Path, Path, int]]:
    """Scan PV YOLO dataset, remap class IDs, return (img_path, lbl_path, majority_class_id).

    Labels are remapped in-memory only — original files are not modified.
    The remapped label path is the *original* path; callers must re-read via
    `read_yolo_label` and remap when writing to the merged dataset (see
    `write_merged_dataset`).
    """
    pairs: list[tuple[Path, Path, int]] = []

    for split in splits:
        imgs_dir   = pv_root / split / "images"
        labels_dir = pv_root / split / "labels"
        if not imgs_dir.exists():
            continue

        for img_path in sorted(imgs_dir.iterdir()):
            if img_path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".bmp"}:
                continue
            lbl_path = labels_dir / (img_path.stem + ".txt")
            raw_boxes = read_yolo_label(lbl_path)

            remapped: list[tuple[int, float, float, float, float]] = []
            for src_id, cx, cy, w, h in raw_boxes:
                dst_id = _remap_class_id(src_id, pv_source_class_names, classes_map)
                if dst_id is not None:
                    remapped.append((dst_id, cx, cy, w, h))

            maj = _majority_class(remapped)
            # Store original lbl_path — we'll remap again during write to avoid
            # a second in-memory copy. Attach remapped boxes via a side-channel
            # tuple so collect_all_pairs doesn't need to re-remap.
            pairs.append((img_path, lbl_path, maj))

    logger.info("PV: collected %d pairs across splits %s", len(pairs), splits)
    return pairs


# ── Merged collection ─────────────────────────────────────────────────────────

def collect_all_pairs(
    ism_pairs: list[tuple[Path, Path, int]],
    pv_pairs: list[tuple[Path, Path, int]],
    pvmd_pairs: list[tuple[Path, Path, int]] | None = None,
) -> list[tuple[Path, Path, int]]:
    """Merge ISM, PV, and (optionally) PVMD pairs into a single flat list."""
    pvmd_pairs = pvmd_pairs or []
    merged = ism_pairs + pv_pairs + pvmd_pairs
    logger.info(
        "Total pairs: %d (ISM=%d, PV=%d, PVMD=%d)",
        len(merged), len(ism_pairs), len(pv_pairs), len(pvmd_pairs),
    )
    return merged


# ── Stratified split ──────────────────────────────────────────────────────────

def stratified_split(
    pairs: list[tuple[Path, Path, int]],
    train_frac: float = 0.75,
    val_frac: float = 0.15,
    seed: int = 42,
) -> tuple[
    list[tuple[Path, Path, int]],
    list[tuple[Path, Path, int]],
    list[tuple[Path, Path, int]],
]:
    """Stratified train / val / test split.

    test_frac is inferred as 1 - train_frac - val_frac.
    Stratification key = majority class id per sample.
    """
    test_frac = round(1.0 - train_frac - val_frac, 6)
    labels = [maj for _, _, maj in pairs]

    # First split: train vs (val+test)
    idx = list(range(len(pairs)))
    idx_train, idx_rest, _, labels_rest = train_test_split(
        idx, labels, test_size=(val_frac + test_frac), stratify=labels, random_state=seed
    )

    # Second split: val vs test from the remainder
    val_ratio_of_rest = val_frac / (val_frac + test_frac)
    idx_val, idx_test = train_test_split(
        idx_rest, test_size=(1.0 - val_ratio_of_rest),
        stratify=labels_rest, random_state=seed,
    )

    train = [pairs[i] for i in idx_train]
    val   = [pairs[i] for i in idx_val]
    test  = [pairs[i] for i in idx_test]

    logger.info(
        "Split → train=%d  val=%d  test=%d  (%.0f/%.0f/%.0f)",
        len(train), len(val), len(test),
        100 * train_frac, 100 * val_frac, 100 * test_frac,
    )
    return train, val, test


# ── Write final YOLO dataset structure ───────────────────────────────────────

def write_merged_dataset(
    split_name: str,
    pairs: list[tuple[Path, Path, int]],
    out_root: Path,
    pv_source_class_names: list[str],
    pv_classes_map: dict[str, str] = PV_CLASSES_MAP,
) -> None:
    """Copy images and write remapped labels for one split.

    ISM labels are already in canonical form (written by collect_ism_pairs).
    PV labels are remapped on-the-fly here to avoid storing two label copies.
    """
    imgs_out  = out_root / split_name / "images"
    lbls_out  = out_root / split_name / "labels"
    imgs_out.mkdir(parents=True, exist_ok=True)
    lbls_out.mkdir(parents=True, exist_ok=True)

    for img_path, lbl_path, _ in pairs:
        # ── Determine if this is a PV pair (needs remap) or ISM (already canonical) ──
        raw_boxes = read_yolo_label(lbl_path)

        # Detect ISM whole-image boxes: single box with (0.5, 0.5, 1.0, 1.0) exactly
        is_ism = (
            len(raw_boxes) == 1 and
            raw_boxes[0][1:] == (0.5, 0.5, 1.0, 1.0)
        )

        if is_ism:
            final_boxes = raw_boxes
        else:
            final_boxes = []
            for src_id, cx, cy, w, h in raw_boxes:
                dst_id = _remap_class_id(src_id, pv_source_class_names, pv_classes_map)
                if dst_id is not None:
                    final_boxes.append((dst_id, cx, cy, w, h))

        # Deduplicate stem collisions by appending source dataset prefix
        stem = img_path.stem
        dest_img  = imgs_out / img_path.name
        dest_lbl  = lbls_out / (stem + ".txt")

        if dest_img.exists():
            prefix = "ism_" if is_ism else "pv_"
            stem   = prefix + stem
            dest_img = imgs_out / (stem + img_path.suffix)
            dest_lbl = lbls_out / (stem + ".txt")

        shutil.copy2(img_path, dest_img)
        write_yolo_label(dest_lbl, final_boxes)


# ── PyTorch Dataset (RGB-fusion stub) ─────────────────────────────────────────
# Import this class only when building the second (RGB) model.  It is
# intentionally not imported at the top of dataset.py so that notebooks that
# only need the scanning helpers don't pull in torch at import time.

def get_torch_dataset_class():
    """Lazy-import guard.  Returns ThermalDataset class (or RGBFusionDataset later)."""
    try:
        import torch
        from torch.utils.data import Dataset
        import cv2 as _cv2
    except ImportError as exc:
        raise ImportError("PyTorch is required for the Dataset class.") from exc

    class ThermalDataset(Dataset):
        """Simple YOLO-format dataset for inference or custom training loops.

        This class is a *stub* — it returns (image_tensor, label_path) pairs.
        When adding an RGB branch, subclass or extend this to return a second
        modality tensor alongside the thermal one.
        """
        def __init__(self, images_dir: Path, labels_dir: Path, imgsz: int = 640):
            self.imgsz = imgsz
            self.samples: list[tuple[Path, Path]] = []
            for p in sorted(images_dir.iterdir()):
                if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".bmp"}:
                    lbl = labels_dir / (p.stem + ".txt")
                    self.samples.append((p, lbl))

        def __len__(self) -> int:
            return len(self.samples)

        def __getitem__(self, idx: int):
            import torch
            img_path, lbl_path = self.samples[idx]
            img = _cv2.imread(str(img_path))
            img = _cv2.resize(img, (self.imgsz, self.imgsz))
            img = _cv2.cvtColor(img, _cv2.COLOR_BGR2RGB)
            tensor = torch.from_numpy(img).permute(2, 0, 1).float() / 255.0
            return tensor, lbl_path

    return ThermalDataset
