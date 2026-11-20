#!/usr/bin/env python3
"""Owner-run, one-off: publish the thermal weights to the SolarDoctor HF model repo.

    export HF_TOKEN=hf_...            # a write token of the account that owns the repo; never commit it
    python scripts/fetch_weights.py   # gets + sha256-verifies ml/thermal/checkpoints/best.pt
    python scripts/publish_weights_hf.py --dry-run     # prints what would be uploaded
    python scripts/publish_weights_hf.py               # uploads README.md (model card) + best.pt

Refuses to upload unless best.pt matches the pinned sha256 (so an LFS pointer or a wrong file can't go up).
The token is read from the environment only. Nothing is uploaded without an explicit run by the owner.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
from pathlib import Path

REPO = "solar-doctor/solar-doctor-thermal-yolo11x"
SHA256 = "fabb41c88f9db29fa5e6803542a6804ee6c0b356aabd7e7c1c0ed6f2d727297d"
DEFAULT_SRC = Path(__file__).resolve().parents[1] / "ml" / "thermal" / "checkpoints" / "best.pt"

CARD = f"""---
license: agpl-3.0
library_name: ultralytics
pipeline_tag: object-detection
tags: [object-detection, thermal, infrared, solar, photovoltaic, yolo11]
---
# SolarDoctor thermal YOLO11x (unmodified upstream checkpoint)

Thermal-infrared photovoltaic anomaly detector, 11 classes: cell, cell-multi, module, string,
bypass-diode, offline-module, vegetation-shading, soiling, short-circuit, hot-spot-low, hot-spot-high.

## Provenance
- File: `best.pt`, {114395865:,} bytes, sha256 `{SHA256}`.
- Source: AxalonSystems, https://github.com/Parakh20/AxalonSystems (path `ml/checkpoints/best.pt`; also
  served from the public Space `parakh20/axalon-api`). Redistributed here unmodified.
- Trained by upstream with Ultralytics 8.4.84, `yolo11x`, 150 epochs, 640 px, checkpoint dated 2026-07-02
  (read from the checkpoint metadata).

## Licence
AGPL-3.0 (Ultralytics YOLO11 weights inherit the AGPL-3.0). If you run this model in a network service you
must offer that service's complete corresponding source to its users. See `docs/solardoctor/WEIGHTS.md` in
the SolarDoctor repository.

## Accuracy: what is and is not established
- Upstream reports mAP@0.5 = 0.792 on its own split. **Unverified by SolarDoctor**: we have not reproduced it.
- The checkpoint's embedded `train_metrics` read mAP@0.5 = 0.727 and mAP@0.5:0.95 = 0.610 (precision 0.677,
  recall 0.693) on the validation set used during training, which differs from the 0.792 claim.
- No SolarDoctor-measured accuracy exists yet. Re-evaluate on your own site and sensor before relying on it.

## Limits
Thermal IR images only; never run on RGB photos. Not validated on other cameras, altitudes or climates.
"""


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", nargs="?", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    if not a.src.is_file():
        print(f"{a.src} not found; run scripts/fetch_weights.py first.", file=sys.stderr)
        return 1
    got = sha256_file(a.src)
    if got != SHA256:
        print(f"Refusing to upload: sha256 {got[:12]} != pinned {SHA256[:12]} (LFS pointer or wrong file?).",
              file=sys.stderr)
        return 1
    if a.dry_run:
        print(f"[dry-run] would create/update model repo {a.repo} and upload README.md + {a.src.name} "
              f"({a.src.stat().st_size} bytes, sha256 {got[:12]})")
        return 0
    token = os.environ.get("HF_TOKEN")
    if not token:
        print("HF_TOKEN is not set. Export a write token for the account that owns the repo.", file=sys.stderr)
        return 2
    from huggingface_hub import HfApi

    api = HfApi(token=token)
    api.create_repo(a.repo, repo_type="model", exist_ok=True)
    api.upload_file(path_or_fileobj=CARD.encode(), path_in_repo="README.md", repo_id=a.repo,
                    commit_message="Add model card")
    api.upload_file(path_or_fileobj=str(a.src), path_in_repo="best.pt", repo_id=a.repo,
                    commit_message=f"Add best.pt (sha256 {got[:12]})")
    print(f"Uploaded to https://huggingface.co/{a.repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
