"""Process-wide ModelRegistry accessor (lazy), replacing SolarPulse's per-module copies."""
from __future__ import annotations

import threading

from ml.forecast.serving.model_registry import ModelRegistry

_registry: ModelRegistry | None = None
_lock = threading.Lock()


def get_registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        with _lock:
            if _registry is None:
                _registry = ModelRegistry()
    return _registry


def reset_registry(registry: ModelRegistry | None = None) -> None:
    """Tests: swap/clear the singleton."""
    global _registry
    _registry = registry
