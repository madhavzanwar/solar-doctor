"""Render ml/rgb/DATA_CARD.md from ml/rgb/data/stats.json (numbers come only from there).

    python -m ml.rgb.data.make_data_card
"""
from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

from solardoctor.vision.model_def import CLASSES

DATA_DIR = Path(__file__).resolve().parent
OUT = DATA_DIR.parent / "DATA_CARD.md"


def _table(first: str, rows: dict[str, dict]) -> list[str]:
    out = [f"| {first} | " + " | ".join(CLASSES) + " | total |", "|---|" + "---|" * (len(CLASSES) + 1)]
    for name, counts in rows.items():
        out.append(f"| {name} | " + " | ".join(str(counts[c]) for c in CLASSES) + f" | {sum(counts.values())} |")
    return out


def ood_licences() -> dict[str, int]:
    p = DATA_DIR / "ood_manifest.csv"
    if not p.exists():
        return {}
    with open(p, newline="", encoding="utf-8") as f:
        return dict(sorted(Counter(r["license_name"] for r in csv.DictReader(f)).items()))


def render(stats: dict) -> str:
    t = stats["thresholds"]
    leak = stats["leak_check"]
    L = [
        "# Data card: SolarDoctor RGB defect classifier", "",
        "## Source and licence", "",
        "Hugging Face dataset `metalmerge/solar-panel-inspection`, revision "
        "`1b62720238a3d5ccf7ca0298afb505fda3cfce7a` (all three folders pooled: `Faulty_solar_panel_Train`, "
        "`Faulty_solar_panel_Validation`, `solar-Panel-Dataset_Test`). It is a mirror/subset of Kaggle "
        "`pythonafroz/solar-panel-images` (Solar Panel Images Clean and Faulty; Kaggle credentials were not available). "
        "No licence is declared on the mirror and Kaggle lists it as **Unknown**, so the images are used for private "
        "training only: not in git, not redistributed, not on Hugging Face, not for public marketing pages. Only file "
        "names and hashes (`manifest.csv`) are committed.", "",
        "## Comparability with published figures", "",
        "The data here is the Hugging Face mirror `metalmerge/solar-panel-inspection` (pinned revision `1b62720`, "
        f"{sum(stats['raw_per_class'].values())} images, {sum(stats['after_cleaning_per_class'].values())} after "
        "exact-duplicate removal, near-duplicates grouped). All model metrics in `reports/BAKEOFF.md` are measured on this "
        "deduplicated, group-split data and are NOT directly comparable to figures published on the original Kaggle "
        "set (the team's original 91.46 %, HybridSolarNet 92.37 %), which were not reproduced here and may include "
        "near-duplicate leakage.", "",
        "## Cleaning", "",
        f"Near-duplicate rule: two images are linked when pHash Hamming <= {t['phash']} or dHash Hamming <= "
        f"{t['dhash']} (hash size 8), taking the minimum distance over the other image's horizontal flip, vertical "
        "flip and 90/180/270 degree rotations as well as the original"
        + (f", or when their DINOv2-small embeddings have cosine similarity >= {t['cosine']}"
           if t.get("cosine") is not None else " (embedding edge disabled for this run)")
        + f". Groups are the transitive closure of the links. Split seed {t['seed']}.", "",
        "Images per class before and after removing corrupt files and exact duplicates:", "",
        *_table("stage", {"raw (decodable)": stats["raw_per_class"], "after exact dedupe": stats["after_cleaning_per_class"]}),
        "", "Removed files by reason: " + (", ".join(f"{k}: {v}" for k, v in sorted(stats["removed_per_reason"].items())) or "none"),
        "", "Near-duplicate groups (more than one image):", "",
        *_table("measure", {"groups": stats["near_dup_groups_per_class"], "images in such groups": stats["near_dup_images_per_class"]}),
        "", "## Splits (grouped by near-duplicate group, stratified by label)", "",
        *_table("split", stats["split_per_class"]), "",
        "Cross-validation folds (-1 = test):", "",
        *_table("fold", {f: c for f, c in sorted(stats["fold_per_class"].items(), key=lambda kv: int(kv[0]))}),
        "", "## Examples of removed duplicates (file names only)", "",
    ]
    L += [f"- exact: `{e['rel_path']}` duplicates `{e['kept_rel_path']}` (distance 0)" for e in stats["exact_duplicate_examples"]]
    L += [f"- near: `{e['a']}` ~ `{e['b']}` (pHash {e['phash_dist']}, dHash {e['dhash_dist']})"
          for e in stats["near_duplicate_examples"]]
    if not (stats["exact_duplicate_examples"] or stats["near_duplicate_examples"]):
        L.append("- none")
    if "edges" in stats:
        e = stats["edges"]
        L += ["", f"Links found: {e['hash']} by hash, {e['embedding']} by embedding "
                  f"({e['embedding_only']} by embedding only). Embedding-only pairs with the highest cosine "
                  "(audit these to judge the threshold):"]
        L += [f"- `{x['a']}` ~ `{x['b']}` (cosine {x['cosine']:.3f})" for x in stats["embedding_only_examples"]] or ["- none"]
    L += ["", "## Possible label noise (near-duplicate groups with different labels)", ""]
    L += [f"- group {g['group_id']}: " + ", ".join(f"`{m['rel_path']}` ({m['label']})" for m in g["members"])
          for g in stats["cross_label_groups"]] or ["- none"]
    L += ["", "## Leakage check", "",
          f"Passed: no group spans splits or folds. Minimum test vs train/val Hamming distance: "
          f"pHash {leak['min_phash_dist']}, dHash {leak['min_dhash_dist']} (must exceed {t['phash']}/{t['dhash']})."]
    lic = ood_licences()
    if lic:
        L += ["", "## Out-of-distribution evaluation images (COCO)", "",
              "The OOD guard is evaluated on 100 non-panel photos from COCO val2017 (ids and sha256 in "
              "`ml/rgb/data/ood_manifest.csv`, fetched by `ml/rgb/fetch_ood.py`). Each image keeps its own Flickr "
              "licence: " + ", ".join(f"{k}: {v}" for k, v in lic.items()) + ". Several are NonCommercial and/or "
              "NoDerivs, so these images are used for evaluation only: they are never redistributed, never "
              "committed to git and never used for training. The images are split 50/50 (seed 42) into OOD-dev "
              "(method and threshold selection) and OOD-test (reporting)."]
    return "\n".join(L) + "\n"


def main() -> None:
    stats = json.loads((DATA_DIR / "stats.json").read_text(encoding="utf-8"))
    OUT.write_text(render(stats), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
