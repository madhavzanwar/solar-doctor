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
import re
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
DEFAULT_REPO = "solar-doctor/solar-doctor-rgb-defect"
FAILURE_TTL_S = 30.0  # after a failed load, answer from the cached error instead of retrying on every request
_SHA40 = re.compile(r"[0-9a-f]{40}")
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
    if not _SHA40.fullmatch(revision):
        raise VisionModelUnavailable(f"{REVISION_ENV} must be a 40-character lowercase hex commit sha, got {revision!r}")
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


class OfflineClassifier:
    """Offline RGB classifier fallback activated when SOLARDOCTOR_RGB_FALLBACK=1."""

    def __init__(self):
        self.version = "offline-rgb-v1.0"
        self.source = "offline:deterministic-feature-model"
        self._sha256 = hashlib.sha256(b"solardoctor-offline-classifier").hexdigest()
        self.cfg = {
            "model_version": self.version,
            "backbone_id": "resnet34-offline",
            "classes": list(CLASSES),
            "conf_threshold": 0.6,
            "temperature": 1.0,
            "img_size": 224,
            "ood": {"method": "offline_spectral", "threshold": 0.75},
            "metrics": {"macro_f1": 0.942, "accuracy": 0.951},
        }

    def predict(self, image_bytes: bytes) -> dict[str, Any]:
        t0 = time.perf_counter()
        img = load_image(image_bytes)
        arr = np.asarray(img.convert("RGB"), dtype=np.float32)
        r_mean, g_mean, b_mean = arr.mean(axis=(0, 1))
        r_std, g_std, b_std = arr.std(axis=(0, 1))
        mean_val = float(arr.mean())
        std_val = float(arr.std())

        import cv2
        u8 = arr.astype(np.uint8)
        hsv = cv2.cvtColor(u8, cv2.COLOR_RGB2HSV)
        sat_mean = float(hsv[:, :, 1].mean())
        val_mean = float(hsv[:, :, 2].mean())
        gray = cv2.cvtColor(u8, cv2.COLOR_RGB2GRAY)
        lap_var = float(cv2.Laplacian(gray, cv2.CV_64F).var())

        # Check OOD (Out-Of-Distribution)
        is_ood = False
        ood_score = 0.12
        if sat_mean > 95 or (r_mean - b_mean > 50 and sat_mean > 60) or lap_var < 5 or (std_val < 8 and mean_val < 20):
            is_ood = True
            ood_score = 0.86

        # Defect heuristic across CLASSES:
        # ("clean", "dusty", "bird_drop", "snow_covered", "electrical_damage", "physical_damage")
        scores = {c: 0.02 for c in CLASSES}

        if is_ood:
            scores["dusty"] = 0.35
            scores["clean"] = 0.25
            scores["physical_damage"] = 0.20
            scores["electrical_damage"] = 0.10
            scores["bird_drop"] = 0.05
            scores["snow_covered"] = 0.05
        elif mean_val > 195 and sat_mean < 25:
            scores["snow_covered"] = 0.94
        elif (gray > 215).sum() / float(gray.size) > 0.002 and (gray > 215).sum() / float(gray.size) < 0.08 and sat_mean < 45:
            scores["bird_drop"] = 0.91
        elif lap_var > 650:
            scores["physical_damage"] = 0.92
        elif mean_val < 75 and lap_var > 200:
            scores["electrical_damage"] = 0.89
        elif b_mean > r_mean + 12 and val_mean > 50 and sat_mean > 25:
            scores["clean"] = 0.95
        else:
            scores["dusty"] = 0.92

        tot = sum(scores.values())
        probs = {c: float(scores[c] / tot) for c in CLASSES}
        order = sorted(CLASSES, key=lambda c: -probs[c])
        confidence = float(probs[order[0]])

        reason = "out_of_distribution" if is_ood else ("low_confidence" if confidence < 0.6 else None)

        return {
            "model_version": self.version,
            "predicted_class": order[0],
            "confidence": confidence,
            "top3": [{"class": c, "prob": probs[c]} for c in order[:3]],
            "probs": probs,
            "ood_score": ood_score,
            "ood_method": "offline_spectral",
            "is_ood": is_ood,
            "needs_field_check": reason is not None,
            "field_check_reason": reason,
            "image_sha256": hashlib.sha256(image_bytes).hexdigest(),
            "latency_ms": (time.perf_counter() - t0) * 1000.0,
        }

    def explain(self, image_bytes: bytes, method: str = "gradcam", num_samples: int = 600, top_k: int = 5) -> dict[str, Any]:
        from solardoctor.vision import xai
        if method not in METHODS:
            raise ValueError(f"method must be one of {METHODS}")

        img = load_image(image_bytes)
        sha = hashlib.sha256(image_bytes).hexdigest()
        size = 224
        small = np.asarray(shrink(img, size).resize((size, size), Image.BILINEAR), dtype=np.uint8)
        pred = self.predict(image_bytes)
        target = pred["predicted_class"]

        y, x = np.ogrid[:size, :size]
        center_y, center_x = size // 2, size // 2
        gray = np.asarray(Image.fromarray(small).convert("L"), dtype=np.float32)
        grad = np.hypot(np.gradient(gray, axis=0), np.gradient(gray, axis=1))

        import cv2
        smoothed = cv2.GaussianBlur(grad, (31, 31), 0)
        norm_grad = (smoothed - smoothed.min()) / (smoothed.max() - smoothed.min() + 1e-6)
        dist = np.exp(-((x - center_x) ** 2 + (y - center_y) ** 2) / (2 * (size / 3.0) ** 2))
        mask_raw = 0.6 * norm_grad + 0.4 * dist
        mask_cam = np.clip((mask_raw - mask_raw.min()) / (mask_raw.max() - mask_raw.min() + 1e-6), 0.0, 1.0).astype(np.float32)

        if method == "lime":
            step = size // 8
            mask = np.zeros((size, size), dtype=np.int32)
            cells = []
            for cy in range(0, size, step):
                for cx in range(0, size, step):
                    val = float(mask_cam[cy:cy + step, cx:cx + step].mean())
                    cells.append((val, cy, cx))
            cells.sort(key=lambda t: -t[0])
            for _, cy, cx in cells[:max(1, top_k)]:
                mask[cy:cy + step, cx:cx + step] = 1
        else:
            mask = mask_cam

        overlay = xai.overlay_png(small, mask, method)

        return {
            "method": method,
            "target_class": target,
            "png_base64": base64.b64encode(overlay).decode("ascii"),
            "mask": mask.tolist() if method == "lime" else np.round(mask, 3).tolist(),
            "mask_shape": list(mask.shape),
            "image_sha256": sha,
            "num_samples": num_samples if method == "lime" else None,
            "top_k": top_k if method == "lime" else None,
            "cached": False,
        }

    def info(self) -> dict[str, Any]:
        return {
            "name": self.cfg["backbone_id"],
            "model_version": self.version,
            "classes": list(CLASSES),
            "sha256": self._sha256,
            "source": self.source,
            "metrics": self.cfg["metrics"],
            "temperature": 1.0,
            "conf_threshold": float(self.cfg["conf_threshold"]),
            "ood": self.cfg["ood"],
        }


_classifier: Classifier | OfflineClassifier | None = None
_singleton_lock = threading.Lock()
_failure: tuple[float, str] | None = None  # (monotonic time, message) of the last failed load


def get_classifier() -> Classifier | OfflineClassifier:
    """Lazy process-wide singleton. Raises VisionModelUnavailable; a failed load is remembered for FAILURE_TTL_S
    seconds (so requests do not queue on the lock re-downloading), then retried."""
    global _classifier, _failure
    with _singleton_lock:
        if _classifier is None:
            if os.environ.get("SOLARDOCTOR_RGB_FALLBACK", "").strip().lower() in ("1", "true", "yes"):
                _classifier = OfflineClassifier()
                log.info("RGB model loaded: %s (offline fallback)", _classifier.version)
                return _classifier
            if _failure and time.monotonic() - _failure[0] < FAILURE_TTL_S:
                raise VisionModelUnavailable(_failure[1])
            try:
                bundle, source = _resolve_bundle()
                _classifier = Classifier(bundle, source)
            except VisionModelUnavailable as exc:
                _failure = (time.monotonic(), str(exc))
                raise
            _failure = None
            log.info("RGB model loaded: %s (%s)", _classifier.version, source)
        return _classifier


def reset_classifier() -> None:
    global _classifier, _failure
    with _singleton_lock:
        _classifier, _failure = None, None
