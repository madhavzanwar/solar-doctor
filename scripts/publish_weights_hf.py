#!/usr/bin/env python3
"""One-off: upload best.pt (from AxalonSystems' LFS) to the SolarDoctor HF model repo. Needs HF_TOKEN."""
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO = "madhavzanwar/solar-doctor-thermal-yolo11x"
CARD = """---
license: agpl-3.0
library_name: ultralytics
tags: [object-detection, thermal, solar, yolo11]
---
# SolarDoctor thermal YOLO11x

Thermal-IR solar panel anomaly detector (11 classes). Trained with Ultralytics (AGPL-3.0) by
AxalonSystems (https://github.com/Parakh20/AxalonSystems). Reported mAP@0.5 = 0.792 on their split.
Re-evaluate before relying on it for a new site.
"""


def main() -> int:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "ml/thermal/checkpoints/best.pt")
    if not src.exists() or src.stat().st_size < 1_000_000:
        print(f"{src} is missing or still an LFS pointer; fetch the real file first.", file=sys.stderr)
        return 1
    from huggingface_hub import HfApi
    api = HfApi(token=os.environ["HF_TOKEN"])
    api.create_repo(REPO, repo_type="model", exist_ok=True)
    api.upload_file(path_or_fileobj=CARD.encode(), path_in_repo="README.md", repo_id=REPO)
    api.upload_file(path_or_fileobj=str(src), path_in_repo="best.pt", repo_id=REPO)
    print(f"Uploaded to https://huggingface.co/{REPO}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
