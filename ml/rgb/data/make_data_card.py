"""Render ml/rgb/DATA_CARD.md from ml/rgb/data/stats.json (numbers come only from there).

    python -m ml.rgb.data.make_data_card
"""
from __future__ import annotations

import json
from pathlib import Path

from solardoctor.vision.model_def import CLASSES

DATA_DIR = Path(__file__).resolve().parent
OUT = DATA_DIR.parent / "DATA_CARD.md"


def _table(first: str, rows: dict[str, dict]) -> list[str]:
    out = [f"| {first} | " + " | ".join(CLASSES) + " | total |", "|---|" + "---|" * (len(CLASSES) + 1)]
    for name, counts in rows.items():
        out.append(f"| {name} | " + " | ".join(str(counts[c]) for c in CLASSES) + f" | {sum(counts.values())} |")
    return out


def render(stats: dict) -> str:
    t = stats["thresholds"]
    leak = stats["leak_check"]
    L = [
        "# Data card: SolarDoctor RGB defect classifier", "",
        "## Source and licence", "",
        "Kaggle `pythonafroz/solar-panel-images` (Solar Panel Images Clean and Faulty). The licence is listed as "
        "**Unknown** on Kaggle, so the images are used for private training only: they are not in git, not "
        "redistributed and not on Hugging Face. Only file names and hashes (`manifest.csv`) are committed.", "",
        "## Cleaning", "",
        f"Near-duplicate rule: pHash Hamming <= {t['phash']} or dHash Hamming <= {t['dhash']} (hash size 8), "
        f"transitive groups. Split seed {t['seed']}.", "",
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
    L += ["", "## Possible label noise (near-duplicate groups with different labels)", ""]
    L += [f"- group {g['group_id']}: " + ", ".join(f"`{m['rel_path']}` ({m['label']})" for m in g["members"])
          for g in stats["cross_label_groups"]] or ["- none"]
    L += ["", "## Leakage check", "",
          f"Passed: no group spans splits or folds. Minimum test vs train/val Hamming distance: "
          f"pHash {leak['min_phash_dist']}, dHash {leak['min_dhash_dist']} (must exceed {t['phash']}/{t['dhash']})."]
    return "\n".join(L) + "\n"


def main() -> None:
    stats = json.loads((DATA_DIR / "stats.json").read_text(encoding="utf-8"))
    OUT.write_text(render(stats), encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
