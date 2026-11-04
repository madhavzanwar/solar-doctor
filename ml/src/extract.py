"""
extract.py — idempotent extraction helpers for the raw dataset archives in
ml/Datasets/.

InfraredSolarModules is already pre-extracted on disk (see
ml/Datasets/InfraredSolarModules/2020-02-14_InfraredSolarModules/) so it needs
no helper here. archive.zip and the PVMD dataset (a .zip containing a .rar)
still need extraction before ml.src.dataset can scan them.
"""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from pathlib import Path

from ml.src.utils import get_logger

logger = get_logger(__name__)


def extract_archive_zip(zip_path: Path, dest_dir: Path) -> Path:
    """Extract the Roboflow archive.zip (ImageSet/train|valid|test/images|labels).

    Returns the `ImageSet` root directory. Idempotent: skips extraction if
    dest_dir/ImageSet/train/images already exists and is non-empty.
    """
    out_root = dest_dir / "ImageSet"
    marker = out_root / "train" / "images"
    if marker.exists() and any(marker.iterdir()):
        logger.info("archive.zip already extracted at %s — skipping", out_root)
        return out_root

    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        zf.extractall(dest_dir)
    logger.info("Extracted archive.zip to %s", out_root)
    return out_root


def extract_pvmd(outer_zip_path: Path, dest_dir: Path) -> Path:
    """Extract the PVMD dataset: outer .zip -> inner .rar -> Cracks/Hotspots/Shadings.

    Returns the PVMD root directory (containing the three class folders).
    Idempotent: skips extraction if all three class folders (Cracks, Hotspots,
    Shadings) already exist and are non-empty. Requires the `unrar` CLI to be installed.
    """
    expected_classes = ("Cracks", "Hotspots", "Shadings")
    if all((dest_dir / name).exists() and any((dest_dir / name).iterdir()) for name in expected_classes):
        logger.info("PVMD already extracted at %s — skipping", dest_dir)
        return dest_dir

    dest_dir.mkdir(parents=True, exist_ok=True)
    staging = dest_dir / "_staging"
    staging.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(outer_zip_path) as zf:
        rar_names = [n for n in zf.namelist() if n.lower().endswith(".rar")]
        if not rar_names:
            raise FileNotFoundError(f"No .rar file found inside {outer_zip_path}")
        zf.extract(rar_names[0], staging)
        rar_path = staging / rar_names[0]

    subprocess.run(
        ["unrar", "x", "-o+", str(rar_path), str(staging)],
        check=True,
        capture_output=True,
    )

    # unrar preserves the "PVMD dataset/<Class>/*" layout inside staging.
    extracted_root = next(staging.rglob("Cracks")).parent
    for class_dir in extracted_root.iterdir():
        if class_dir.is_dir():
            target = dest_dir / class_dir.name
            if not target.exists():
                class_dir.rename(target)

    # Clean up staging directory after extraction
    shutil.rmtree(staging, ignore_errors=True)

    logger.info("Extracted PVMD to %s", dest_dir)
    return dest_dir
