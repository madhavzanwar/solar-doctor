"""
model_info.py — describe the model weights file the platform actually serves.

/health used to report a hard-coded model name, which hid weight drift between
environments. This module reads the truth from the checkpoint on disk:

- architecture / name from the Ultralytics checkpoint metadata (``model.yaml``),
- file size and a short sha256 prefix to fingerprint the exact weights.

Reading the metadata does NOT load the model or import torch. An Ultralytics
``.pt`` is a torch zip archive whose ``data.pkl`` holds the pickled checkpoint
dict; tensor payloads live in separate zip entries referenced via
``persistent_load``. ``_MetadataUnpickler`` never resolves real classes (every
global becomes an inert stub, except ``OrderedDict``/``set``/``frozenset``), so
no code from the pickle is executed and no tensor bytes are read — it takes
~10 ms for the 109 MB YOLO11x checkpoint.

Results are cached per (path, size, mtime) so /health stays cheap.
"""

from __future__ import annotations

import collections
import hashlib
import pickle
import re
import threading
import zipfile
from pathlib import Path

from ml.src.utils import get_logger

logger = get_logger("axalon.model_info")

UNKNOWN = "unknown"
SHA256_PREFIX_LEN = 12
_HASH_CHUNK_BYTES = 1 << 20
_REPO_ROOT = Path(__file__).resolve().parents[2]

_SAFE_GLOBALS = {
    ("collections", "OrderedDict"): collections.OrderedDict,
    ("builtins", "set"): set,
    ("builtins", "frozenset"): frozenset,
}

_cache: dict[tuple[str, int, int], dict] = {}
_cache_lock = threading.Lock()


class _Stub:
    """Inert placeholder for any class/function referenced by the pickle."""

    def __init__(self, *args, **kwargs) -> None:
        self._args = args

    def __setstate__(self, state) -> None:
        self._state = state


class _MetadataUnpickler(pickle.Unpickler):
    """Unpickler that builds inert stubs instead of importing real globals."""

    def find_class(self, module: str, name: str):  # noqa: D401
        safe = _SAFE_GLOBALS.get((module, name))
        if safe is not None:
            return safe
        return type(name, (_Stub,), {"__module__": module})

    def persistent_load(self, pid):
        return None  # tensor storage — never read


def model_display_name(yaml_file: str | None, scale: str | None) -> str | None:
    """Turn an Ultralytics model yaml name into a human label.

    ``yolo11x.yaml`` -> ``YOLO11x``; ``yolo11.yaml`` + scale ``m`` -> ``YOLO11m``;
    ``rtdetr-x.yaml`` -> ``RT-DETR-x``. Returns None when there is nothing to name.
    """
    if not yaml_file:
        return None
    stem = Path(yaml_file).stem
    if scale and not re.search(r"\d[a-z]$", stem) and stem.lower().startswith("yolo"):
        stem = f"{stem}{scale}"
    lowered = stem.lower()
    if lowered.startswith("yolo"):
        return "YOLO" + stem[4:]
    if lowered.startswith("rtdetr"):
        return "RT-DETR" + stem[6:]
    return stem


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(_REPO_ROOT))
    except ValueError:
        return str(path)


def _sha256_prefix(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(_HASH_CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()[:SHA256_PREFIX_LEN]


def _read_checkpoint_dict(path: Path) -> dict | None:
    """Return the pickled checkpoint dict from a torch zip archive, or None."""
    if not zipfile.is_zipfile(path):
        return None
    with zipfile.ZipFile(path) as archive:
        pkl_names = [n for n in archive.namelist() if n.endswith("data.pkl")]
        if not pkl_names:
            return None
        with archive.open(pkl_names[0]) as fh:
            ckpt = _MetadataUnpickler(fh).load()
    return ckpt if isinstance(ckpt, dict) else None


def _model_yaml(ckpt: dict) -> dict:
    for key in ("model", "ema"):
        state = getattr(ckpt.get(key), "_state", None)
        if isinstance(state, dict) and isinstance(state.get("yaml"), dict):
            return state["yaml"]
    return {}


def empty_model_info(path: Path) -> dict:
    return {
        "name": UNKNOWN,
        "architecture": UNKNOWN,
        "task": UNKNOWN,
        "num_classes": None,
        "ultralytics_version": UNKNOWN,
        "trained_at": UNKNOWN,
        "weights_path": _display_path(path),
        "exists": False,
        "size_bytes": None,
        "size_mb": None,
        "sha256": None,
    }


def _metadata_fields(path: Path) -> dict:
    try:
        ckpt = _read_checkpoint_dict(path)
    except Exception:  # corrupt / foreign format — file facts are still useful
        logger.warning("Could not read checkpoint metadata from %s", path, exc_info=True)
        return {}
    if not ckpt:
        return {}
    yaml = _model_yaml(ckpt)
    train_args = ckpt.get("train_args") if isinstance(ckpt.get("train_args"), dict) else {}
    fields = {
        "name": model_display_name(yaml.get("yaml_file"), yaml.get("scale")),
        "architecture": yaml.get("yaml_file"),
        "task": train_args.get("task"),
        "num_classes": yaml.get("nc") if isinstance(yaml.get("nc"), int) else None,
        "ultralytics_version": ckpt.get("version"),
        "trained_at": ckpt.get("date"),
    }
    return {k: v for k, v in fields.items() if v is not None}


def describe_weights(path: str | Path) -> dict:
    """Describe a weights file without loading the model. Never raises for I/O."""
    path = Path(path)
    info = empty_model_info(path)
    try:
        stat = path.stat()
    except OSError:
        return info
    if not path.is_file():
        return info

    info.update(
        exists=True,
        size_bytes=stat.st_size,
        size_mb=round(stat.st_size / (1024 * 1024), 1),
    )
    try:
        info["sha256"] = _sha256_prefix(path)
    except OSError:
        logger.warning("Could not hash weights file %s", path, exc_info=True)
    info.update(_metadata_fields(path))
    return info


def get_model_info(path: str | Path) -> dict:
    """Cached :func:`describe_weights`, invalidated when size or mtime change."""
    path = Path(path)
    try:
        stat = path.stat()
        key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns)
    except OSError:
        return describe_weights(path)  # missing file: cheap, don't cache
    with _cache_lock:
        cached = _cache.get(key)
    if cached is not None:
        return dict(cached)
    info = describe_weights(path)
    with _cache_lock:
        _cache[key] = info
    return dict(info)


def clear_cache() -> None:
    with _cache_lock:
        _cache.clear()
