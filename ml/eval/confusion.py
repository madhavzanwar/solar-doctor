#!/usr/bin/env python3
"""Locate the per-class confusion matrix produced by a YOLO val run.

ultralytics already renders `confusion_matrix.png` (and a normalized variant)
into the val run directory when `model.val(plots=True)` is used — which
ml.eval.evaluate does. Rather than recompute it, this helper finds the most
recent one under a results/run directory and optionally copies it to a target.

Usage:
    python3 -m ml.eval.confusion --search ml/eval/results --out ml/eval/confusion_matrix.png
"""
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

_CONFUSION_NAMES = ("confusion_matrix.png", "confusion_matrix_normalized.png")


def find_confusion_matrix(search_dir: str) -> Path | None:
    """Return the most recently modified confusion matrix PNG under search_dir."""
    root = Path(search_dir)
    if not root.exists():
        return None
    candidates = [
        p for name in _CONFUSION_NAMES for p in root.rglob(name)
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--search", default="ml/eval/results")
    parser.add_argument("--out", default=None, help="optional path to copy the PNG to")
    args = parser.parse_args()

    found = find_confusion_matrix(args.search)
    if found is None:
        print(f"No confusion matrix found under {args.search}. "
              "Run `python3 -m ml.eval.evaluate` first (needs the dataset).")
        return 1

    print(f"Confusion matrix: {found}")
    if args.out:
        shutil.copy2(found, args.out)
        print(f"Copied to: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
