#!/usr/bin/env python3
"""Fetch the thermal YOLO11x weights (ml/thermal/checkpoints/best.pt) and verify them by sha256.

    python scripts/fetch_weights.py                 # try each source in order
    python scripts/fetch_weights.py --force         # re-download even if a good file exists
    python scripts/fetch_weights.py --dest PATH

Sources, tried in order until one passes the sha256 check:
  1. SolarDoctor's own HF model repo (after the owner publishes it; see docs/solardoctor/WEIGHTS.md)
  2. Upstream's public HF Space parakh20/axalon-api (file ml/checkpoints/best.pt, no token needed)
Override with --url (repeatable) or SOLARDOCTOR_THERMAL_URL.

Behaviour: an existing file whose sha256 matches is never touched; a wrong or partial file is never
left at the destination (download goes to <dest>.part, resumes via HTTP Range, and is renamed only
after the hash matches). HF_TOKEN, if set, is sent only to huggingface.co hosts.

Weights: Ultralytics YOLO11x (AGPL-3.0) trained by AxalonSystems; upstream-reported mAP@0.5 0.792
on their split (not verified by us). Exit codes: 0 ok, 1 no source worked, 2 bad arguments.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

EXPECTED_SHA256 = "fabb41c88f9db29fa5e6803542a6804ee6c0b356aabd7e7c1c0ed6f2d727297d"
EXPECTED_SIZE = 114395865
DEST = Path(__file__).resolve().parents[1] / "ml" / "thermal" / "checkpoints" / "best.pt"
DEFAULT_URLS = (
    "https://huggingface.co/madhavzanwar/solar-doctor-thermal-yolo11x/resolve/main/best.pt",
    "https://huggingface.co/spaces/parakh20/axalon-api/resolve/main/ml/checkpoints/best.pt",
)
CHUNK = 1 << 20


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(CHUNK), b""):
            h.update(block)
    return h.hexdigest()


def is_good(path: Path, expected: str = EXPECTED_SHA256) -> bool:
    return path.is_file() and sha256_file(path) == expected


def _headers(url: str, offset: int) -> dict[str, str]:
    headers = {"User-Agent": "solardoctor-fetch-weights"}
    host = urlparse(url).hostname or ""
    token = os.environ.get("HF_TOKEN")
    if token and (host == "huggingface.co" or host.endswith(".huggingface.co") or host.endswith(".hf.co")):
        headers["Authorization"] = f"Bearer {token}"
    if offset:
        headers["Range"] = f"bytes={offset}-"
    return headers


def download(url: str, part: Path, opener=urllib.request.urlopen) -> None:
    """Stream url into part, resuming if part already has bytes. Raises on network/HTTP errors."""
    offset = part.stat().st_size if part.exists() else 0
    try:
        resp = opener(urllib.request.Request(url, headers=_headers(url, offset)), timeout=60)
    except urllib.error.HTTPError as exc:
        if exc.code == 416 and offset:  # range not satisfiable: the .part is already complete or stale
            return
        raise
    with resp:
        status = getattr(resp, "status", 200)
        mode = "ab" if (offset and status == 206) else "wb"  # server ignored Range -> restart
        with open(part, mode) as out:
            for block in iter(lambda: resp.read(CHUNK), b""):
                out.write(block)


def fetch(urls, dest: Path, expected: str = EXPECTED_SHA256, force: bool = False, opener=urllib.request.urlopen,
          log=print) -> int:
    if not force and is_good(dest, expected):
        log(f"{dest} already present and sha256 verified; nothing to do.")
        return 0
    part = dest.with_name(dest.name + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    for url in urls:
        try:
            log(f"Downloading {url}")
            download(url, part, opener)
            got = sha256_file(part)
            if got != expected:
                errors.append(f"{url}: sha256 mismatch (got {got[:12]}, want {expected[:12]})")
                part.unlink(missing_ok=True)  # never resume a corrupt file
                continue
            os.replace(part, dest)
            log(f"Saved {dest} ({dest.stat().st_size / 1e6:.1f} MB, sha256 {expected[:12]} verified). "
                "Set ENABLE_THERMAL=true.")
            return 0
        except (urllib.error.URLError, OSError, TimeoutError) as exc:
            errors.append(f"{url}: {exc}")  # keep .part so a rerun resumes
    for line in errors:
        print(f"  failed: {line}", file=sys.stderr)
    print("Could not obtain the thermal weights. Thermal detection stays off: keep ENABLE_THERMAL=false.",
          file=sys.stderr)
    return 1


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", action="append", help="source URL (repeatable); replaces the defaults")
    ap.add_argument("--dest", type=Path, default=DEST)
    ap.add_argument("--sha256", default=EXPECTED_SHA256, help="expected sha256 (64 hex chars)")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args(argv)
    if len(a.sha256) != 64:
        print("--sha256 must be a full 64-character hex digest", file=sys.stderr)
        return 2
    env_url = os.environ.get("SOLARDOCTOR_THERMAL_URL")
    urls = a.url or ([env_url] if env_url else list(DEFAULT_URLS))
    return fetch(urls, a.dest, a.sha256.lower(), a.force)


if __name__ == "__main__":
    raise SystemExit(main())
