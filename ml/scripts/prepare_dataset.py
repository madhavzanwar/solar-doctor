"""
prepare_dataset.py — build ml/data/combined/ from the three raw datasets in
ml/Datasets/, matching the layout ml/thermal_dataset.yaml expects
(<split>/images/, <split>/labels/).

Usage:
    python3 -m ml.scripts.prepare_dataset \
        --out ml/data/combined \
        --staging ml/data/_staging

Sources merged (see ml/src/dataset.py for class-mapping tables):
    - InfraredSolarModules (already extracted on disk, classification -> weak bbox)
    - archive.zip / ImageSet (Roboflow, real bboxes)
    - PVMD dataset (.zip containing a .rar, classification -> weak bbox)
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

from ml.src.dataset import (
    PV_CLASSES_MAP,
    collect_all_pairs,
    collect_ism_pairs,
    collect_pv_pairs,
    collect_pvmd_pairs,
    stratified_split,
    write_merged_dataset,
)
from ml.src.extract import extract_archive_zip, extract_pvmd
from ml.src.utils import CANONICAL_CLASSES, ID2CLASS, get_logger, read_yolo_label

logger = get_logger(__name__)


def _class_distribution(out_dir: Path) -> dict[str, dict[str, int]]:
    """Count canonical class occurrences per split by reading written labels."""
    report: dict[str, dict[str, int]] = {}
    for split in ("train", "val", "test"):
        counts: Counter[str] = Counter()
        labels_dir = out_dir / split / "labels"
        if not labels_dir.exists():
            report[split] = {}
            continue
        for lbl_path in labels_dir.glob("*.txt"):
            for cid, *_ in read_yolo_label(lbl_path):
                counts[ID2CLASS.get(cid, f"unknown-{cid}")] += 1
        report[split] = dict(counts)
    return report


def build_combined_dataset(
    out_dir: Path,
    ism_root: Path,
    archive_zip: Path,
    pvmd_zip: Path,
    staging_dir: Path,
    seed: int = 42,
) -> dict[str, dict[str, int]]:
    """Merge all three sources into out_dir, return + persist a class-distribution report."""
    staging_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    ism_images = ism_root / "images"
    ism_metadata = ism_root / "module_metadata.json"
    ism_pairs = collect_ism_pairs(ism_images, ism_metadata)

    archive_root = extract_archive_zip(archive_zip, staging_dir / "archive")
    pv_source_names = list(PV_CLASSES_MAP.keys())
    pv_pairs = collect_pv_pairs(archive_root, pv_source_names)

    pvmd_root = extract_pvmd(pvmd_zip, staging_dir / "pvmd")
    pvmd_pairs = collect_pvmd_pairs(pvmd_root)

    all_pairs = collect_all_pairs(ism_pairs, pv_pairs, pvmd_pairs)
    train, val, test = stratified_split(all_pairs, seed=seed)

    for split_name, pairs in (("train", train), ("val", val), ("test", test)):
        write_merged_dataset(split_name, pairs, out_dir, pv_source_class_names=pv_source_names)

    report = _class_distribution(out_dir)
    (out_dir / "class_distribution.json").write_text(json.dumps(report, indent=2))
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="ml/data/combined")
    parser.add_argument("--staging", default="ml/data/_staging")
    parser.add_argument(
        "--ism-root",
        default="ml/Datasets/InfraredSolarModules/2020-02-14_InfraredSolarModules/InfraredSolarModules",
    )
    parser.add_argument("--archive-zip", default="ml/Datasets/archive.zip")
    parser.add_argument(
        "--pvmd-zip",
        default=(
            "ml/Datasets/Photovoltaic module dataset for automated fault detection "
            "and analysis in large photovoltaic systems using photovoltaic module "
            "fault detection.zip"
        ),
    )
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    report = build_combined_dataset(
        out_dir=Path(args.out),
        ism_root=Path(args.ism_root),
        archive_zip=Path(args.archive_zip),
        pvmd_zip=Path(args.pvmd_zip),
        staging_dir=Path(args.staging),
        seed=args.seed,
    )

    print("\nClass distribution per split:")
    for split, counts in report.items():
        print(f"  {split}:")
        for cls in CANONICAL_CLASSES:
            print(f"    {cls:<20} {counts.get(cls, 0)}")


if __name__ == "__main__":
    main()
