"""Owner-run: publish a model bundle to a PRIVATE Hugging Face model repo. Weights only, never dataset images.

    HF_TOKEN=hf_... python -m ml.rgb.publish_hf --bundle ml/rgb/checkpoints/<version> --dry-run
    HF_TOKEN=hf_... python -m ml.rgb.publish_hf --bundle ml/rgb/checkpoints/<version>

Only whitelisted bundle files plus a generated README.md (model card = reports/BAKEOFF.md) are uploaded; the repo
is created private and the script refuses a bundle containing anything else (e.g. images). The model's training data
has an unknown licence, so no public release until that is resolved.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO = "solar-doctor/solar-doctor-rgb-defect"
ALLOWED = {"config.json", "model.safetensors", "model.onnx", "ood_stats.npz", "autoencoder.safetensors"}
HERE = Path(__file__).parent
LIBRARY = {"timm": "timm", "hf_dinov2": "transformers", "hf_clip": "transformers", "torchvision": "pytorch"}

HEADER = """---
license: other
license_name: unknown-training-data
library_name: timm
pipeline_tag: image-classification
tags: [solar, photovoltaic, defect-classification]
---
# SolarDoctor RGB defect classifier (PRIVATE)

Six classes: clean, dusty, bird_drop, snow_covered, electrical_damage, physical_damage. Training data is the
`metalmerge/solar-panel-inspection` mirror, whose licence is unknown: this repo stays private and the dataset images
are not included. RGB cannot see hot-spots or diode faults; use thermal / IV data for those.

"""


def files_to_upload(bundle: Path) -> list[Path]:
    present = [p for p in sorted(bundle.rglob("*")) if p.is_file()]
    bad = [p.name for p in present if p.name not in ALLOWED]
    if bad:
        raise SystemExit(f"Refusing to upload: unexpected files in bundle: {bad}")
    if not {"config.json", "model.safetensors"} <= {p.name for p in present}:
        raise SystemExit("Refusing to upload: bundle lacks config.json or model.safetensors")
    return present


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bundle", required=True, type=Path)
    ap.add_argument("--repo", default=REPO)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    files = files_to_upload(a.bundle)
    arch = json.loads((a.bundle / "config.json").read_text())["arch"]
    report = HERE / "reports" / "BAKEOFF.md"
    card = HEADER.replace("library_name: timm", f"library_name: {LIBRARY.get(arch, 'pytorch')}") + (report.read_text(encoding="utf-8") if report.exists() else "Metrics report not generated.\n")
    print(f"{'[dry-run] ' if a.dry_run else ''}private model repo {a.repo}: README.md + "
          + ", ".join(f"{p.name} ({p.stat().st_size} bytes)" for p in files))
    if a.dry_run:
        return 0
    if not os.environ.get("HF_TOKEN"):
        print("HF_TOKEN is not set.", file=sys.stderr)
        return 2
    from huggingface_hub import HfApi

    api = HfApi(token=os.environ["HF_TOKEN"])
    if api.repo_exists(a.repo) and not api.repo_info(a.repo).private:
        print(f"Refusing: {a.repo} exists and is PUBLIC; training-data licence is unknown.", file=sys.stderr)
        return 3
    api.create_repo(a.repo, repo_type="model", private=True, exist_ok=True)
    api.upload_file(path_or_fileobj=card.encode(), path_in_repo="README.md", repo_id=a.repo)
    for p in files:
        api.upload_file(path_or_fileobj=str(p), path_in_repo=p.name, repo_id=a.repo)
    print(f"Uploaded (private) to https://huggingface.co/{a.repo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
