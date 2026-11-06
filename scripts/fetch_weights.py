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
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

EXPECTED_SHA256 = "fabb41c88f9db29fa5e6803542a6804ee6c0b356aabd7e7c1c0ed6f2d727297d"
EXPECTED_SIZE = 114395865
DEST = Path(__file__).resolve().parents[1] / "ml" / "thermal" / "checkpoints" / "best.pt"
DEFAULT_URLS = (
    "https://huggingface.co/solar-doctor/solar-doctor-thermal-yolo11x/resolve/main/best.pt",
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


def _is_hf_host(host: str) -> bool:
    return host == "huggingface.co" or host.endswith((".huggingface.co", ".hf.co"))


def _headers(url: str, offset: int, use_token: bool = True) -> dict[str, str]:
    headers = {"User-Agent": "solardoctor-fetch-weights"}
    token = os.environ.get("HF_TOKEN")
    if use_token and token and _is_hf_host(urlparse(url).hostname or ""):
        headers["Authorization"] = f"Bearer {token}"
    if offset:
        headers["Range"] = f"bytes={offset}-"
    return headers


class _StripAuthOnOffHostRedirect(urllib.request.HTTPRedirectHandler):
    """urllib forwards Authorization on redirects; drop it unless the new host is Hugging Face."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        new = super().redirect_request(req, fp, code, msg, headers, newurl)
        if new is not None and not _is_hf_host(urlparse(newurl).hostname or ""):
            for name in list(new.headers):
                if name.lower() == "authorization":
                    del new.headers[name]
            for name in list(new.unredirected_hdrs):
                if name.lower() == "authorization":
                    del new.unredirected_hdrs[name]
        return new


_OPENER = urllib.request.build_opener(_StripAuthOnOffHostRedirect)


def _default_open(req, timeout=None):
    return _OPENER.open(req, timeout=timeout)


class ShortRead(OSError):
    """Server closed early or sent bytes that do not line up with the requested range."""


def download(url: str, part: Path, opener=None, use_token: bool = True) -> None:
    """Stream url into part, resuming if part already has bytes. Raises on network/HTTP errors."""
    opener = opener or _default_open
    offset = part.stat().st_size if part.exists() else 0
    try:
        resp = opener(urllib.request.Request(url, headers=_headers(url, offset, use_token)), timeout=60)
    except urllib.error.HTTPError as exc:
        if exc.code == 416 and offset:  # range not satisfiable: .part is already full-size (or stale); hash decides
            return
        raise
    with resp:
        status = getattr(resp, "status", 200)
        resuming = bool(offset) and status == 206
        if resuming:
            cr = resp.headers.get("Content-Range", "") if getattr(resp, "headers", None) else ""
            if cr and not cr.startswith(f"bytes {offset}-"):
                raise ShortRead(f"server answered 206 with unexpected Content-Range {cr!r} for offset {offset}")
        expected = None
        length = resp.headers.get("Content-Length") if getattr(resp, "headers", None) else None
        if length and length.isdigit():
            expected = int(length)
        written = 0
        with open(part, "ab" if resuming else "wb") as out:  # server ignored Range -> restart
            for block in iter(lambda: resp.read(CHUNK), b""):
                out.write(block)
                written += len(block)
        if expected is not None and written != expected:
            raise ShortRead(f"connection closed early ({written} of {expected} bytes); kept {part.name}")


def _is_unpublished(exc: Exception) -> bool:
    return isinstance(exc, urllib.error.HTTPError) and exc.code in (401, 404)


def fetch(urls, dest: Path, expected: str = EXPECTED_SHA256, force: bool = False, opener=None, log=print,
          retries: int = 2, backoff: float = 2.0, sleep=time.sleep) -> int:
    if not force and is_good(dest, expected):
        log(f"{dest} already present and sha256 verified; nothing to do.")
        return 0
    part = dest.with_name(dest.name + ".part")
    dest.parent.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    for url in urls:
        # The token is only for our own (possibly private) repo, never for the public upstream Space.
        use_token = "/spaces/parakh20/" not in url
        for attempt in range(retries + 1):
            try:
                log(f"Downloading {url}" + (f" (retry {attempt})" if attempt else ""))
                download(url, part, opener, use_token)
                got = sha256_file(part)
                if got == expected:
                    os.replace(part, dest)
                    log(f"Saved {dest} ({dest.stat().st_size / 1e6:.1f} MB, sha256 {expected[:12]} verified). "
                        "Set ENABLE_THERMAL=true.")
                    return 0
                errors.append(f"{url}: sha256 mismatch (got {got[:12]}, want {expected[:12]})")
                part.unlink(missing_ok=True)  # never resume a corrupt file
                if attempt < retries:  # a short read can look like a mismatch: retry from scratch
                    sleep(backoff * (2 ** attempt))
                    continue
                break
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                if _is_unpublished(exc):
                    log(f"Skipping {url}: not published yet (HTTP {exc.code}).")
                    break
                errors.append(f"{url}: {exc}")  # keep .part so the retry/rerun resumes
                if attempt < retries:
                    sleep(backoff * (2 ** attempt))
                    continue
                break
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
