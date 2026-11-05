# Adapted from SolarPulseAI (https://github.com/anugrahpatil-creator/SolarPulseAI)
# MIT License, Copyright (c) 2026 anugrahpatil-creator. See THIRD_PARTY_NOTICES.md.
# Modified for SolarDoctor: package path ml.forecast; logic otherwise unchanged.
"""
Model registry for loading, caching, and serving trained forecaster artifacts.

Extended in v1.1 to also track per-plant OnlineResidualAdapter instances
(see ONLINE_LEARNING_SPEC.md §6.2).
"""

import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional, Union
import joblib

from ml.forecast.models.base_model import BaseForecaster
from ml.forecast.models.lightgbm_model import LightGBMForecaster
from ml.forecast.models.probabilistic_model import ProbabilisticForecaster
from ml.forecast.models.online_residual_adapter import OnlineResidualAdapter

logger = logging.getLogger("solarpulse.registry")


class ModelRegistry:
    """
    In-memory registry and cache for model artifacts stored on disk.
    Avoids redundant file I/O during real-time API inference and background worker tasks.
    """

    def __init__(self, artifact_dir: Optional[Union[str, Path]] = None):
        import os
        env_root = os.getenv("SOLARDOCTOR_FORECAST_ARTIFACTS")
        base = Path(env_root) if env_root else Path(__file__).resolve().parent.parent / "artifacts"
        if artifact_dir is None:
            self.artifact_dir = base / "models"
        else:
            self.artifact_dir = Path(artifact_dir)

        # ── Static model cache ──────────────────────────────────────────────
        self._cache: Dict[str, BaseForecaster] = {}

        # ── Online adapter store ─────────────────────────────────────────────
        # Keyed by plant_id (str).  Created lazily on first access.
        self._online_adapters: Dict[str, OnlineResidualAdapter] = {}
        self._adapters_lock = threading.Lock()

        # Directory for JSON checkpoint files
        self._online_state_dir: Path = base / "online_states"

    def get_model(
        self,
        plant_id: str = "default",
        version: Optional[str] = None,
        probabilistic: bool = False
    ) -> BaseForecaster:
        """
        Retrieves a cached model instance or loads it from disk.

        Parameters
        ----------
        plant_id : str
            Identifier for the solar plant.
        version : Optional[str]
            Specific model version (e.g. "1.0.0"). If None, resolves latest model.
        probabilistic : bool
            If True, loads quantile probabilistic forecaster instead of point forecaster.

        Returns
        -------
        BaseForecaster
            Fitted forecaster ready for inference.
        """
        prefix = "prob" if probabilistic else "lgbm"
        cache_key = f"{prefix}_{plant_id}_{version or 'latest'}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        model_path = self._resolve_model_path(
            plant_id=plant_id,
            version=version,
            prefix=prefix
        )

        logger.info("Loading model artifact from %s", model_path)
        if probabilistic:
            model = ProbabilisticForecaster.load(model_path)
        else:
            model = LightGBMForecaster.load(model_path)

        self._cache[cache_key] = model
        return model

    def _resolve_model_path(
        self,
        plant_id: str,
        version: Optional[str],
        prefix: str
    ) -> Path:
        """
        Locates the appropriate model artifact path on disk.
        """
        self.artifact_dir.mkdir(parents=True, exist_ok=True)

        # 1. Check versioned file for specific plant
        if version:
            candidate = self.artifact_dir / f"{prefix}_{plant_id}_v{version}.pkl"
            if candidate.exists():
                return candidate

        # 2. Check plant-specific latest
        plant_latest = self.artifact_dir / f"{prefix}_{plant_id}_latest.pkl"
        if plant_latest.exists():
            return plant_latest

        # 3. Check generic latest
        generic_latest = self.artifact_dir / f"{prefix}_latest.pkl"
        if generic_latest.exists():
            return generic_latest

        # 4. Search any matching prefix artifact
        matches = list(self.artifact_dir.glob(f"{prefix}*.pkl"))
        if matches:
            # Pick latest modified
            matches.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return matches[0]

        raise FileNotFoundError(
            f"No model artifact found for prefix '{prefix}', plant '{plant_id}', "
            f"in {self.artifact_dir}"
        )

    def list_available_models(self) -> List[Dict[str, str]]:
        """
        Lists all serialized model files in the artifact directory.
        """
        if not self.artifact_dir.exists():
            return []

        models = []
        for path in self.artifact_dir.glob("*.pkl"):
            models.append({
                "filename": path.name,
                "path": str(path),
                "size_kb": f"{path.stat().st_size / 1024:.1f}",
            })
        return models

    def clear_cache(self) -> None:
        """Flushes the in-memory model cache."""
        self._cache.clear()
        logger.info("Model registry cache cleared.")

    # ── Online Residual Adapter API ───────────────────────────────────────────

    def get_online_adapter(self, plant_id: str) -> OnlineResidualAdapter:
        """
        Return the OnlineResidualAdapter for *plant_id*, creating one if absent.

        The adapter is first looked up from an on-disk checkpoint so state
        survives server restarts.  Thread-safe.

        Parameters
        ----------
        plant_id : str
            Unique plant identifier (matches the Plant.id stored as a string).
        """
        with self._adapters_lock:
            if plant_id not in self._online_adapters:
                adapter = self._load_or_create_adapter(plant_id)
                self._online_adapters[plant_id] = adapter
            return self._online_adapters[plant_id]

    def update_online_state(
        self,
        plant_id: str,
        y_actual: float,
        y_pred_base: float,
        ghi: float,
        has_active_anomaly: bool = False,
        is_curtailed: bool = False,
        persist: bool = True,
    ) -> bool:
        """
        Convenience wrapper: get adapter, call update(), and optionally persist.

        Parameters
        ----------
        persist : bool
            If True, write a JSON checkpoint after a successful update so state
            is durable across restarts.

        Returns
        -------
        bool
            True if the adapter step was applied (same as adapter.update()).
        """
        adapter = self.get_online_adapter(plant_id)
        applied = adapter.update(
            y_actual=y_actual,
            y_pred_base=y_pred_base,
            ghi=ghi,
            has_active_anomaly=has_active_anomaly,
            is_curtailed=is_curtailed,
        )
        if applied and persist:
            self._persist_adapter(adapter)
        return applied

    def list_online_adapters(self) -> List[dict]:
        """Return a summary of all active online adapter states."""
        with self._adapters_lock:
            return [a.get_status() for a in self._online_adapters.values()]

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _checkpoint_path(self, plant_id: str) -> Path:
        return self._online_state_dir / f"adapter_{plant_id}.json"

    def _load_or_create_adapter(self, plant_id: str) -> OnlineResidualAdapter:
        """Load from disk checkpoint if available, else create a fresh adapter."""
        path = self._checkpoint_path(plant_id)
        if path.exists():
            try:
                adapter = OnlineResidualAdapter.load_checkpoint(path)
                logger.info(
                    "Online adapter restored for plant '%s' (n=%d samples)",
                    plant_id, adapter.state.samples_observed,
                )
                return adapter
            except Exception as exc:
                logger.warning(
                    "Failed to load adapter checkpoint for plant '%s': %s — creating fresh adapter.",
                    plant_id, exc,
                )
        logger.info("Creating new online adapter for plant '%s'.", plant_id)
        return OnlineResidualAdapter(plant_id=plant_id)

    def _persist_adapter(self, adapter: OnlineResidualAdapter) -> None:
        """Write adapter state to disk (non-blocking; errors are logged, not raised)."""
        try:
            path = self._checkpoint_path(adapter.plant_id)
            adapter.save_checkpoint(path)
        except Exception as exc:
            logger.error(
                "Could not persist online adapter checkpoint for plant '%s': %s",
                adapter.plant_id, exc,
            )
