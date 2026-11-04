#!/usr/bin/env python3
"""Download the thermal YOLO11x weights from Hugging Face Hub (replaces the old Git LFS object).

    python scripts/fetch_weights.py            # -> ml/thermal/checkpoints/best.pt
    python scripts/fetch_weights.py --repo ORG/NAME --revision main

Weights: trained with Ultralytics (AGPL-3.0) by AxalonSystems, mAP@0.5 0.792 on their split.
Set ENABLE_THERMAL=true afterwards. Private repos need HF_TOKEN in the environment.
"""
from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path

DEFAULT_REPO = os.environ.get("SOLARDOCTOR_THERMAL_REPO", "madhavzanwar/solar-doctor-thermal-yolo11x")
DEST = Path(__file__).resolve().parents[1] / "ml" / "thermal" / "checkpoints" / "best.pt"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=DEFAULT_REPO)
    ap.add_argument("--filename", default="best.pt")
    ap.add_argument("--revision", default=None)
    ap.add_argument("--dest", type=Path, default=DEST)
    a = ap.parse_args()
    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("huggingface_hub is required: pip install huggingface_hub", file=sys.stderr)
        return 2
    try:
        cached = hf_hub_download(a.repo, a.filename, revision=a.revision, token=os.environ.get("HF_TOKEN"))
    except Exception as exc:  # noqa: BLE001 - surface any hub error plainly
        print(f"Could not download {a.filename} from {a.repo}: {exc}", file=sys.stderr)
        print("Thermal detection stays off: keep ENABLE_THERMAL=false until the weights exist.", file=sys.stderr)
        return 1
    a.dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cached, a.dest)
    print(f"Saved {a.dest} ({a.dest.stat().st_size / 1e6:.1f} MB). Set ENABLE_THERMAL=true.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
