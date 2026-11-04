"""Hardened ZIP extraction.

Uploaded archives are untrusted. Extraction defends against zip-slip,
symlink/device members, zip bombs, and pathological archives that never
finish extracting.
"""
from __future__ import annotations

import logging
import stat
import zipfile
from pathlib import Path

from fastapi import HTTPException

logger = logging.getLogger("axalon.api")

_MAX_ZIP_BYTES = 2 * 1024 * 1024 * 1024              # 2 GB per zip (compressed)
_MAX_ZIP_UNCOMPRESSED_BYTES = 8 * 1024 * 1024 * 1024  # 8 GB extracted — blocks zip-bombs
_MAX_ZIP_RATIO = 200                                  # max compressed→uncompressed ratio per member
_MAX_ZIP_MEMBERS = 10_000                             # max files inside a zip
_ZIP_EXTRACT_TIMEOUT_S = 300


def _is_unsafe_member(member: zipfile.ZipInfo) -> str | None:
    """Return a reason string if the member should be rejected, else None.

    Rejects symlinks, devices, and any non-regular file. external_attr in
    zip stores Unix mode in the high 16 bits — anything that isn't a plain
    file or directory is refused to prevent symlink-based sandbox escapes.
    """
    mode = (member.external_attr >> 16) & 0xFFFF
    if mode and not (stat.S_ISREG(mode) or stat.S_ISDIR(mode)):
        return f"non-regular file (mode={oct(mode)})"
    # Absolute paths or drive letters
    if member.filename.startswith(("/", "\\")) or ":" in member.filename:
        return "absolute or drive-qualified path"
    return None


def _safe_extract_zip(zf: zipfile.ZipFile, extract_dir: Path) -> None:
    """Extract zip entries with defenses against:
       - Zip-slip (path traversal)
       - Symlink/device members (sandbox escape)
       - Zip bombs (uncompressed-size cap + per-member ratio cap)
    """
    extract_root = extract_dir.resolve()
    total_uncompressed = 0

    for member in zf.infolist():
        reason = _is_unsafe_member(member)
        if reason:
            logger.warning("Rejected zip entry (%s): %s", reason, member.filename)
            continue

        # Per-member ratio check — flags pathological compression early
        if member.compress_size > 0:
            ratio = member.file_size / max(member.compress_size, 1)
            if ratio > _MAX_ZIP_RATIO and member.file_size > 1024 * 1024:
                logger.warning(
                    "Rejected zip entry with extreme compression ratio %.0fx: %s",
                    ratio, member.filename,
                )
                continue

        total_uncompressed += member.file_size
        if total_uncompressed > _MAX_ZIP_UNCOMPRESSED_BYTES:
            raise HTTPException(
                status_code=400,
                detail="ZIP archive uncompressed size exceeds the allowed limit",
            )

        member_path = (extract_dir / member.filename).resolve()
        try:
            member_path.relative_to(extract_root)
        except ValueError:
            logger.warning("Rejected zip entry with path traversal: %s", member.filename)
            continue
        zf.extract(member, str(extract_dir))


def _safe_extract_zip_with_timeout(
    zf: zipfile.ZipFile, extract_dir: Path, timeout_s: int = _ZIP_EXTRACT_TIMEOUT_S
) -> None:
    """Run _safe_extract_zip under a SIGALRM watchdog (Unix-only).

    Batch jobs run in a worker thread via BackgroundTasks, but extraction itself
    has no inner bound — this caps it so a pathological ZIP raises TimeoutError
    instead of stalling indefinitely. SIGALRM only fires on the main thread; when
    it isn't available (non-main thread or non-Unix) we fall back to a plain call.
    """
    import signal

    try:
        def _handler(_signum, _frame):
            raise TimeoutError(f"ZIP extraction exceeded {timeout_s}s")

        old = signal.signal(signal.SIGALRM, _handler)
    except (ValueError, AttributeError):
        # Not the main thread, or SIGALRM unavailable — extract without the watchdog.
        _safe_extract_zip(zf, extract_dir)
        return

    signal.alarm(timeout_s)
    try:
        _safe_extract_zip(zf, extract_dir)
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


__all__ = [
    "_MAX_ZIP_BYTES",
    "_MAX_ZIP_MEMBERS",
    "_MAX_ZIP_RATIO",
    "_MAX_ZIP_UNCOMPRESSED_BYTES",
    "_ZIP_EXTRACT_TIMEOUT_S",
    "_is_unsafe_member",
    "_safe_extract_zip",
    "_safe_extract_zip_with_timeout",
]
