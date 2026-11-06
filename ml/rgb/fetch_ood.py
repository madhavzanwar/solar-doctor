"""Build the held-out OOD set: 100 non-panel COCO val2017 photos (CC-licensed per image; see manifest).

Idempotent and resumable. The committed manifest is ml/rgb/data/ood_manifest.csv; images and the annotation
zip stay in the gitignored ml/rgb/data/ood/.
"""
from __future__ import annotations

import csv
import json
import random
import re
import urllib.request
import zipfile
from pathlib import Path

DATA = Path(__file__).parent / "data"
OOD = DATA / "ood"
CACHE = OOD / "_cache"
ANN_URL = "http://images.cocodataset.org/annotations/annotations_trainval2017.zip"
IMG_URL = "http://images.cocodataset.org/val2017/{}"
BAD = re.compile(r"solar|panel|photovoltaic", re.I)


def download(url: str, dest: Path) -> None:
    """Download with resume (Range) via a .part file."""
    if dest.exists():
        return
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url)
    done = part.stat().st_size if part.exists() else 0
    if done:
        req.add_header("Range", f"bytes={done}-")
    with urllib.request.urlopen(req, timeout=60) as r, open(part, "ab" if done and r.status == 206 else "wb") as f:
        while chunk := r.read(1 << 20):
            f.write(chunk)
    part.rename(dest)


def pick(captions: dict, n: int = 100, seed: int = 42) -> list[dict]:
    bad_ids = {a["image_id"] for a in captions["annotations"] if BAD.search(a["caption"])}
    lic = {l["id"]: l["name"] for l in captions["licenses"]}
    ok = sorted((i for i in captions["images"] if i["id"] not in bad_ids), key=lambda i: i["id"])
    return [{"image_id": i["id"], "file_name": i["file_name"], "license_id": i["license"],
             "license_name": lic[i["license"]], "url": IMG_URL.format(i["file_name"])}
            for i in random.Random(seed).sample(ok, n)]


def main() -> None:
    zpath = CACHE / "annotations_trainval2017.zip"
    download(ANN_URL, zpath)
    with zipfile.ZipFile(zpath) as z:
        captions = json.loads(z.read("annotations/captions_val2017.json"))
    rows = pick(captions)
    for r in rows:
        download(r["url"], OOD / "coco" / r["file_name"])
    with open(DATA / "ood_manifest.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader(); w.writerows(rows)
    print(f"{len(rows)} OOD images in {OOD / 'coco'}; manifest {DATA / 'ood_manifest.csv'}")


if __name__ == "__main__":
    main()
