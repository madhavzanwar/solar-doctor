"""Process-wide RGB classifier: loads a model bundle (ml/rgb/README.md, Contract 2) and serves predict/explain/info.

Never fabricates output: without a loadable bundle `get_classifier()` raises `VisionModelUnavailable`.
torch/timm are imported lazily so importing this module (and the API) stays cheap.
"""
from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from solardoctor.vision.model_def import CLASSES, load_image, preprocess, shrink

log = logging.getLogger("solardoctor.vision")

DIR_ENV = "SOLARDOCTOR_RGB_MODEL_DIR"
REPO_ENV = "SOLARDOCTOR_RGB_MODEL_REPO"
REVISION_ENV = "SOLARDOCTOR_RGB_MODEL_REVISION"
DEFAULT_REPO = "solar-doctor/solar-doctor-rgb"
METHODS = ("gradcam", "lime")
_LIME_CACHE_SIZE = 16


class VisionModelUnavailable(RuntimeError):
    """No usable model bundle; the message says why."""


def _resolve_bundle() -> tuple[Path, str]:
    local = os.environ.get(DIR_ENV, "").strip()
    if local:
        return Path(local), f"local:{Path(local).name}"
    revision = os.environ.get(REVISION_ENV, "").strip()
    if not revision:
        raise VisionModelUnavailable(f"set {DIR_ENV}, or {REVISION_ENV} to pin a Hugging Face revision")
    repo = os.environ.get(REPO_ENV, "").strip() or DEFAULT_REPO
    try:
        from huggingface_hub import snapshot_download
        return Path(snapshot_download(repo_id=repo, revision=revision)), f"hf:{repo}@{revision}"
    except Exception as exc:
        raise VisionModelUnavailable(f"could not download {repo}@{revision}: {exc}") from exc


class Classifier:
    def __init__(self, bundle: Path, source: str):
        from safetensors.torch import load_file
        from solardoctor.vision import ood
        from solardoctor.vision.model_def import build_model

        try:
            self.cfg: dict[str, Any] = json.loads((bundle / "config.json").read_text(encoding="utf-8"))
            if tuple(self.cfg.get("classes", CLASSES)) != CLASSES:
                raise ValueError("bundle classes differ from model_def.CLASSES")
            weights = bundle / "model.safetensors"
            self.model = build_model(self.cfg, pretrained=False)
            self.model.load_state_dict(load_file(str(weights)), strict=True)
            self.model.eval()
            self._scorer = ood.load_scorer(self.cfg, bundle)
            self._sha256 = hashlib.sha256(weights.read_bytes()).hexdigest()
        except Exception as exc:
            raise VisionModelUnavailable(f"cannot load bundle {bundle.name}: {exc}") from exc
        self.source = source
        self.version: str = self.cfg["model_version"]
        self._temperature = float(self.cfg.get("temperature", 1.0))
        self._lock = threading.RLock()  # Grad-CAM hooks the model, so all model use is serialised
        self._lime_cache: OrderedDict[tuple, dict] = OrderedDict()

    # ── helpers ──────────────────────────────────────────────────────────
    def _probs_batch(self, x: np.ndarray) -> np.ndarray:
        import torch
        with self._lock, torch.inference_mode():
            logits = self.model(torch.from_numpy(x))
            return torch.softmax(logits / self._temperature, dim=1).numpy()

    def _probs(self, img: Image.Image) -> np.ndarray:
        return self._probs_batch(preprocess(img, self.cfg)[None])[0]

    # ── public API ───────────────────────────────────────────────────────
    def predict(self, image_bytes: bytes) -> dict[str, Any]:
        t0 = time.perf_counter()
        img = load_image(image_bytes)
        probs = self._probs(img)
        order = np.argsort(-probs)
        confidence = float(probs[order[0]])

        ood_score = is_ood = None
        method = (self.cfg.get("ood") or {}).get("method", "none")
        if self._scorer is not None:
            with self._lock:
                ood_score = float(self._scorer(img))
            is_ood = ood_score > float(self.cfg["ood"]["threshold"])
        reason = ("out_of_distribution" if is_ood
                  else "low_confidence" if confidence < float(self.cfg.get("conf_threshold", 0.6)) else None)
        return {
            "model_version": self.version,
            "predicted_class": CLASSES[order[0]],
            "confidence": confidence,
            "top3": [{"class": CLASSES[i], "prob": float(probs[i])} for i in order[:3]],
            "probs": {c: float(p) for c, p in zip(CLASSES, probs)},
            "ood_score": ood_score,
            "ood_method": method,
            "is_ood": bool(is_ood),
            "needs_field_check": reason is not None,
            "field_check_reason": reason,
            "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
            "latency_ms": (time.perf_counter() - t0) * 1000.0,
        }

    def info(self) -> dict[str, Any]:
        ood = self.cfg.get("ood") or {}
        return {
            "name": self.cfg.get("backbone_id"), "model_version": self.version, "classes": list(CLASSES),
            "sha256": self._sha256, "source": self.source, "metrics": self.cfg.get("metrics", {}),
            "temperature": self._temperature, "conf_threshold": float(self.cfg.get("conf_threshold", 0.6)),
            "ood": {"method": ood.get("method", "none"), "threshold": ood.get("threshold")},
        }

    def explain(self, image_bytes: bytes, method: str = "gradcam", num_samples: int = 600,
                top_k: int = 5) -> dict[str, Any]:
        import torch
        from solardoctor.vision import xai

        if method not in METHODS:
            raise ValueError(f"method must be one of {METHODS}")
        img = load_image(image_bytes)
        sha = hashlib.sha256(image_bytes).hexdigest()
        lime = method == "lime"
        key = (sha, method, num_samples, top_k, self.version)
        if lime:
            with self._lock:
                if key in self._lime_cache:
                    self._lime_cache.move_to_end(key)
                    return {**self._lime_cache[key], "cached": True}

        size = int(self.cfg["img_size"])
        small = np.asarray(shrink(img, size).resize((size, size), Image.BILINEAR), dtype=np.uint8)
        target = int(np.argmax(self._probs(img)))
        with self._lock:
            if lime:
                mask, _, _ = xai.lime_mask(
                    lambda b: self._probs_batch(np.stack([preprocess(Image.fromarray(a), self.cfg) for a in b])),
                    small, target, num_samples, top_k)
            else:
                x = torch.from_numpy(preprocess(img, self.cfg))[None]
                mask = xai.gradcam_mask(self.model, self.cfg, x, target)
        result = {
            "method": method, "target_class": CLASSES[target],
            "png_base64": base64.b64encode(xai.overlay_png(small, mask, method)).decode("ascii"),
            "mask": (mask.tolist() if lime else np.round(mask, 3).tolist()), "mask_shape": list(mask.shape),
            "image_sha256": sha, "num_samples": num_samples if lime else None,
            "top_k": top_k if lime else None, "cached": False,
        }
        if lime:
            with self._lock:
                self._lime_cache[key] = result
                while len(self._lime_cache) > _LIME_CACHE_SIZE:
                    self._lime_cache.popitem(last=False)
        return result


_classifier: Classifier | None = None
_singleton_lock = threading.Lock()


def get_classifier() -> Classifier:
    """Lazy process-wide singleton. Raises VisionModelUnavailable (failures are not cached, so a fix is picked up)."""
    global _classifier
    with _singleton_lock:
        if _classifier is None:
            bundle, source = _resolve_bundle()
            _classifier = Classifier(bundle, source)
            log.info("RGB model loaded: %s (%s)", _classifier.version, source)
        return _classifier


def reset_classifier() -> None:
    global _classifier
    with _singleton_lock:
        _classifier = None
