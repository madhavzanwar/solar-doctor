"""Loader for the ORIGINAL SolarPulseAI code, used by golden tests.

SolarPulseAI (MIT) is cloned at /tmp/claude-0/sp/SolarPulseAI (override with SOLARPULSE_DIR). Its
sources import ``backend.ml.*`` / ``app.*`` and open an asyncpg engine at import time, so we copy the
needed files into a temp package ``sp_orig`` with import rewrites (async DB imports dropped; only pure
functions are exercised). Nothing in the repo imports this at runtime.
"""
from __future__ import annotations

import importlib
import os
import re
import sys
import tempfile
from pathlib import Path

SP_DIR = Path(os.environ.get("SOLARPULSE_DIR", "/tmp/claude-0/sp/SolarPulseAI")) / "backend"

_DROP = re.compile(
    r"^(from app\.core\.\w+ import .*|from app\.models\.\w+ import .*|"
    r"from sqlalchemy\.ext\.asyncio import .*|from sqlalchemy\.orm import selectinload)\n", re.M)

_STUBS = (
    "import logging\n"
    "get_logger = logging.getLogger\n"
    "class _Settings:\n"
    "    WEATHER_API_KEY = ''\n    ML_MODEL_PATH = '/nonexistent/lightgbm_model.txt'\n"
    "settings = _Settings()\n"
    "AsyncSession = object\n"
)


def available() -> bool:
    return (SP_DIR / "ml" / "models" / "lightgbm_model.py").exists()


def _rewrite(src: str, is_service: bool) -> str:
    src = src.replace("backend.ml.", "sp_orig.ml.").replace("app.services", "sp_orig.services")
    src = src.replace("app.schemas", "sp_orig.schemas")
    if is_service:
        src = _DROP.sub("", src)
        # place stubs right after the __future__ import (or at top)
        m = re.search(r"^from __future__ import annotations\n", src, re.M)
        pos = m.end() if m else 0
        src = src[:pos] + _STUBS + src[pos:]
    return src


def load() -> None:
    """Build and import the ``sp_orig`` package (idempotent)."""
    if "sp_orig" in sys.modules:
        return
    root = Path(tempfile.mkdtemp(prefix="sp_orig_")) / "sp_orig"
    for sub in ("ml", "ml/features", "ml/models", "ml/postprocessing", "ml/training", "ml/serving",
                "services", "schemas"):
        (root / sub).mkdir(parents=True, exist_ok=True)
        (root / sub / "__init__.py").write_text("")
    (root / "__init__.py").write_text("")
    for f in (SP_DIR / "ml").rglob("*.py"):
        rel = f.relative_to(SP_DIR / "ml")
        if rel.parts[0] in ("features", "models", "postprocessing", "training", "serving") or rel.name == "config.py":
            dst = root / "ml" / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(_rewrite(f.read_text(), False))
    for name in ("clipping_service", "soiling_service", "anomaly_service", "diagnosis_service",
                 "weather_service", "forecast_service"):
        (root / "services" / f"{name}.py").write_text(_rewrite((SP_DIR / "app/services" / f"{name}.py").read_text(), True))
    for f in (SP_DIR / "app/schemas").glob("*.py"):
        (root / "schemas" / f.name).write_text(_rewrite(f.read_text(), False))
    sys.path.insert(0, str(root.parent))
    importlib.invalidate_caches()
    importlib.import_module("sp_orig")


def mod(dotted: str):
    load()
    return importlib.import_module(f"sp_orig.{dotted}")
