# Adapted from SolarPulseAI (https://github.com/anugrahpatil-creator/SolarPulseAI)
# MIT License, Copyright (c) 2026 anugrahpatil-creator. See THIRD_PARTY_NOTICES.md.
# Modified for SolarDoctor: package path ml.forecast; logic otherwise unchanged.
"""
ml/models/online_residual_adapter.py

Online Residual and Bias Adapter for real-time solar generation forecast adjustment.

Implements a Dual Additive-Multiplicative Dynamic Estimator with exponential decay
and safety clipping (see ONLINE_LEARNING_SPEC.md §4).

Key concepts
------------
* Tier 1 (Base Predictor): Pre-trained LightGBM — weights stay frozen.
* Tier 2 (This Module): Tracks real-time prediction error ε_t = y_actual - ŷ_base
  via recursive exponential smoothing and applies a horizon-decayed correction to
  near-term forecasts.

Safety gates (§5)
-----------------
1. Physical daylight gate — GHI > 20 W/m² required.
2. Fault / anomaly containment — updates blocked while alerts are active.
3. Bounded adjustments — γ clamped to [0.70, 1.30].
4. Stale-state relaxation — γ exponentially reverts to 1.0 after 60 min of silence.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger("solarpulse.online_adapter")

# ── Constants ──────────────────────────────────────────────────────────────────

_NIGHT_GHI_THRESHOLD_W_M2: float = 20.0   # W/m² below which learning is gated
_MIN_BASE_POWER_KW: float = 5.0            # kW: avoid tiny-denominator ratios
_STALE_TIMEOUT_MINUTES: float = 60.0      # minutes before γ reverts to 1.0
_STALE_REVERSION_ALPHA: float = 0.05       # reversion step per minute of silence
_EPSILON_KW: float = 1.0                   # division-by-zero guard (δ in spec)

_DEFAULT_ALPHA: float = 0.12              # learning rate
_DEFAULT_DECAY: float = 0.90              # λ — horizon decay per 15-min step
_DEFAULT_MIN_SCALING: float = 0.70
_DEFAULT_MAX_SCALING: float = 1.30


# ── State dataclass ────────────────────────────────────────────────────────────


@dataclass
class AdapterState:
    """Serialisable snapshot of the online adapter weights for one plant."""

    plant_id: str
    scaling_factor: float = 1.0         # Multiplicative γ
    bias_kw: float = 0.0                # Additive residual bias (kW)
    last_updated: Optional[str] = None  # ISO-8601 UTC string (JSON-serialisable)
    samples_observed: int = 0
    recent_rmse: float = 0.0            # Running RMSE tracker (squared-error EMA)
    # Internal running squared-error accumulator (not serialised to JSON output)
    _sse_accum: float = field(default=0.0, repr=False, compare=False)

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict (excludes private fields)."""
        d = asdict(self)
        d.pop("_sse_accum", None)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "AdapterState":
        d.setdefault("_sse_accum", 0.0)
        return cls(**d)


# ── Adapter ───────────────────────────────────────────────────────────────────


class OnlineResidualAdapter:
    """
    Lightweight streaming residual corrector for a single solar plant.

    Parameters
    ----------
    plant_id : str
        Unique identifier for the solar plant.
    alpha : float
        Exponential smoothing learning rate ∈ [0.05, 0.20].
    decay_factor : float
        Per-step horizon decay λ ∈ [0.85, 0.95].
    min_scaling, max_scaling : float
        Hard clamps on multiplicative correction γ.
    """

    def __init__(
        self,
        plant_id: str,
        alpha: float = _DEFAULT_ALPHA,
        decay_factor: float = _DEFAULT_DECAY,
        min_scaling: float = _DEFAULT_MIN_SCALING,
        max_scaling: float = _DEFAULT_MAX_SCALING,
    ) -> None:
        if not (0.05 <= alpha <= 0.20):
            raise ValueError(f"alpha must be in [0.05, 0.20]; got {alpha}")
        if not (0.80 <= decay_factor <= 0.99):
            raise ValueError(f"decay_factor must be in [0.80, 0.99]; got {decay_factor}")

        self.plant_id = plant_id
        self.alpha = alpha
        self.decay_factor = decay_factor
        self.min_scaling = min_scaling
        self.max_scaling = max_scaling
        self.state = AdapterState(plant_id=plant_id)

    # ── Public API ─────────────────────────────────────────────────────────────

    def update(
        self,
        y_actual: float,
        y_pred_base: float,
        ghi: float,
        has_active_anomaly: bool = False,
        is_curtailed: bool = False,
    ) -> bool:
        """
        Incrementally update internal state given a new SCADA telemetry reading.

        Returns
        -------
        bool
            True if the update was applied; False if rejected by safety gates.
        """
        # ── Safety Gate 1: Nighttime / dark conditions ─────────────────────────
        if ghi < _NIGHT_GHI_THRESHOLD_W_M2 or y_pred_base <= _MIN_BASE_POWER_KW:
            logger.debug(
                "Plant %s: update skipped — nighttime/dark (GHI=%.1f, base=%.1f kW)",
                self.plant_id, ghi, y_pred_base,
            )
            return False

        # ── Safety Gate 2: Hardware fault / anomaly contamination ──────────────
        if has_active_anomaly:
            logger.debug("Plant %s: update blocked — active anomaly alert.", self.plant_id)
            return False

        # ── Safety Gate 3: Grid curtailment ────────────────────────────────────
        if is_curtailed:
            logger.debug("Plant %s: update blocked — grid curtailment active.", self.plant_id)
            return False

        # ── Compute residual and instantaneous scaling ratio ───────────────────
        residual = y_actual - y_pred_base                      # ε_t  (additive)
        instant_ratio = (y_actual + _EPSILON_KW) / (y_pred_base + _EPSILON_KW)  # r_t

        # Clamp to [γ_min, γ_max] before smoothing
        clamped_ratio = float(np.clip(instant_ratio, self.min_scaling, self.max_scaling))

        # ── Exponential smoothing update (§4.3) ────────────────────────────────
        self.state.scaling_factor = (
            (1.0 - self.alpha) * self.state.scaling_factor + self.alpha * clamped_ratio
        )
        self.state.bias_kw = (
            (1.0 - self.alpha) * self.state.bias_kw + self.alpha * residual
        )

        # Running RMSE via exponential moving average of squared error
        sq_err = residual ** 2
        self.state._sse_accum = (
            (1.0 - self.alpha) * self.state._sse_accum + self.alpha * sq_err
        )
        self.state.recent_rmse = float(np.sqrt(self.state._sse_accum))

        self.state.last_updated = datetime.now(timezone.utc).isoformat()
        self.state.samples_observed += 1

        logger.debug(
            "Plant %s: adapter updated — γ=%.4f bias=%.2f kW residual=%.2f kW (n=%d)",
            self.plant_id,
            self.state.scaling_factor,
            self.state.bias_kw,
            residual,
            self.state.samples_observed,
        )
        return True

    def adjust_forecast(
        self,
        y_pred_base: np.ndarray,
        step_horizons: np.ndarray,
    ) -> np.ndarray:
        """
        Apply horizon-decayed online correction to an array of base predictions.

        Parameters
        ----------
        y_pred_base : np.ndarray, shape (N,)
            Raw base-model predictions in kW, ordered by ascending lead time.
        step_horizons : np.ndarray, shape (N,)
            Integer step indices (0 = now, 1 = t+15 min, 2 = t+30 min, …).

        Returns
        -------
        np.ndarray
            Corrected predictions clipped to ≥ 0.0 kW.

        Notes
        -----
        Formula (§4.4):
            ŷ_final(t+k) = max(0, ŷ_base(t+k) · [1 + (γ - 1) · λ^k])
        """
        # No data yet — pass through unmodified
        if self.state.samples_observed == 0:
            return y_pred_base.copy()

        # Check stale state and apply gradual reversion if needed
        self._maybe_revert_stale_state()

        gamma = self.state.scaling_factor
        # Horizon factors: 1 + (γ - 1) · λ^k
        horizon_factors = 1.0 + (gamma - 1.0) * (self.decay_factor ** step_horizons)
        adjusted = y_pred_base * horizon_factors

        # Physical floor: power cannot be negative
        return np.maximum(0.0, adjusted)

    def get_status(self) -> dict:
        """
        Return a summary dict for the monitoring endpoint.

        Returns
        -------
        dict matching OnlineAdapterStatusResponse schema.
        """
        gamma = self.state.scaling_factor
        if gamma > 1.05:
            adapter_status = "ADAPTING_ABOVE_NWP"
        elif gamma < 0.90:
            adapter_status = "ADAPTING_SOILING_HAZE"
        else:
            adapter_status = "BASELINE_OPTIMAL"

        return {
            "plant_id": self.plant_id,
            "scaling_factor": round(self.state.scaling_factor, 4),
            "bias_kw": round(self.state.bias_kw, 2),
            "samples_observed_today": self.state.samples_observed,
            "recent_rmse_kw": round(self.state.recent_rmse, 2),
            "status": adapter_status,
            "last_updated": self.state.last_updated,
            "alpha": self.alpha,
            "decay_factor": self.decay_factor,
        }

    # ── Serialisation ──────────────────────────────────────────────────────────

    def save_checkpoint(self, path: Path) -> None:
        """Persist adapter state to a JSON checkpoint file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "plant_id": self.plant_id,
            "alpha": self.alpha,
            "decay_factor": self.decay_factor,
            "min_scaling": self.min_scaling,
            "max_scaling": self.max_scaling,
            "state": self.state.to_dict(),
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        logger.info("Adapter checkpoint saved → %s", path)

    @classmethod
    def load_checkpoint(cls, path: Path) -> "OnlineResidualAdapter":
        """Restore an adapter from a JSON checkpoint file."""
        payload = json.loads(path.read_text(encoding="utf-8"))
        adapter = cls(
            plant_id=payload["plant_id"],
            alpha=payload.get("alpha", _DEFAULT_ALPHA),
            decay_factor=payload.get("decay_factor", _DEFAULT_DECAY),
            min_scaling=payload.get("min_scaling", _DEFAULT_MIN_SCALING),
            max_scaling=payload.get("max_scaling", _DEFAULT_MAX_SCALING),
        )
        adapter.state = AdapterState.from_dict(payload["state"])
        logger.info("Adapter checkpoint loaded ← %s", path)
        return adapter

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _maybe_revert_stale_state(self) -> None:
        """
        If telemetry has been silent for > 60 min (§5.4), exponentially relax γ → 1.0.
        Called lazily from adjust_forecast so it runs on every inference call.
        """
        if self.state.last_updated is None:
            return

        last_dt = datetime.fromisoformat(self.state.last_updated)
        now = datetime.now(timezone.utc)
        elapsed_minutes = (now - last_dt).total_seconds() / 60.0

        if elapsed_minutes <= _STALE_TIMEOUT_MINUTES:
            return

        # For every elapsed minute beyond timeout, move γ a step toward 1.0
        excess_minutes = elapsed_minutes - _STALE_TIMEOUT_MINUTES
        reversion_steps = int(excess_minutes)  # integer steps applied lazily
        if reversion_steps < 1:
            return

        # γ_new = γ_old + reversion_alpha * steps * (1.0 - γ_old) [capped to 1.0]
        gamma = self.state.scaling_factor
        for _ in range(min(reversion_steps, 200)):   # cap loop iterations
            gamma = gamma + _STALE_REVERSION_ALPHA * (1.0 - gamma)
        self.state.scaling_factor = float(np.clip(gamma, self.min_scaling, self.max_scaling))

        if abs(self.state.scaling_factor - 1.0) > 1e-3:
            logger.debug(
                "Plant %s: stale reversion applied (%.0f min silence) → γ=%.4f",
                self.plant_id, elapsed_minutes, self.state.scaling_factor,
            )

    def reset(self) -> None:
        """Reset adapter weights to factory defaults (keeps hyperparameters)."""
        self.state = AdapterState(plant_id=self.plant_id)
        logger.info("Plant %s: online adapter state reset.", self.plant_id)
