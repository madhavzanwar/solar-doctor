"""Out-of-distribution scorers. Convention: higher score = more OOD; `is_ood = score > threshold`.

The public functions/classes are also imported by the training code in `ml/rgb/`; keep signatures stable.
A scorer is a callable `PIL.Image -> float`; `load_scorer` returns None when the bundle uses method "none".
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from solardoctor.vision.model_def import build_autoencoder, preprocess

DINOV2_ID = "facebook/dinov2-small"
CLIP_ID = "openai/clip-vit-base-patch32"
DEFAULT_PROMPTS_POS = ["a photo of a solar panel", "a close-up photo of a photovoltaic module"]
DEFAULT_PROMPTS_NEG = ["a photo of a person", "a photo of an animal", "a photo of a building", "a photo of a landscape"]


# ── Mahalanobis on DINOv2 features ───────────────────────────────────────────
def dinov2_features(backbone, x):
    """[CLS ‖ mean(patch tokens)] -> [N, 2*hidden]; backbone is a transformers Dinov2Model."""
    import torch
    h = backbone(pixel_values=x).last_hidden_state
    return torch.cat([h[:, 0], h[:, 1:].mean(1)], 1)


def fit_mahalanobis(feats: np.ndarray):
    """Ledoit-Wolf shrunk Gaussian fit -> (mean, precision)."""
    from sklearn.covariance import LedoitWolf
    lw = LedoitWolf().fit(feats)
    return lw.location_, lw.precision_


def mahalanobis_score(feats: np.ndarray, mean: np.ndarray, precision: np.ndarray) -> np.ndarray:
    d = np.asarray(feats) - mean
    return np.sqrt(np.maximum(np.einsum("ij,jk,ik->i", d, precision, d), 0.0))


class MahalanobisDinov2:
    def __init__(self, backbone, mean: np.ndarray, precision: np.ndarray):
        self.backbone, self.mean, self.precision = backbone.eval(), mean, precision

    def __call__(self, img) -> float:
        import torch
        x = torch.from_numpy(preprocess(img, {"img_size": 224}))[None]
        with torch.inference_mode():
            feats = dinov2_features(self.backbone, x).numpy()
        return float(mahalanobis_score(feats, self.mean, self.precision)[0])


# ── CLIP zero-shot ───────────────────────────────────────────────────────────
class ClipZeroShot:
    """OOD score = 1 - P(positive prompts) under a softmax over positive + negative prompts."""

    def __init__(self, model_id: str = CLIP_ID, prompts_pos: list[str] = DEFAULT_PROMPTS_POS,
                 prompts_neg: list[str] = DEFAULT_PROMPTS_NEG, model=None, processor=None):
        from transformers import CLIPModel, CLIPProcessor
        self.model = (model or CLIPModel.from_pretrained(model_id)).eval()
        self.processor = processor or CLIPProcessor.from_pretrained(model_id)
        self.prompts_pos, self.prompts_neg = list(prompts_pos), list(prompts_neg)

    def score(self, pil_images: list) -> np.ndarray:
        import torch
        inputs = self.processor(text=self.prompts_pos + self.prompts_neg, images=pil_images,
                                return_tensors="pt", padding=True)
        with torch.inference_mode():
            probs = self.model(**inputs).logits_per_image.softmax(dim=1)
        return (1.0 - probs[:, :len(self.prompts_pos)].sum(1)).numpy()

    def __call__(self, img) -> float:
        return float(self.score([img])[0])


# ── Autoencoder reconstruction error ─────────────────────────────────────────
def to_gray100(pil):
    """PIL -> float tensor [1, 100, 100] in [0, 1]."""
    import torch
    from PIL import Image
    arr = np.asarray(pil.convert("L").resize((100, 100), Image.BILINEAR), dtype=np.float32) / 255.0
    return torch.from_numpy(arr)[None]


def autoencoder_score(ae, x_gray) -> np.ndarray:
    """Per-image MSE; x_gray float [N, 1, 100, 100] in [0, 1]."""
    import torch
    with torch.inference_mode():
        return ((ae(x_gray) - x_gray) ** 2).mean(dim=(1, 2, 3)).numpy()


class AutoencoderOOD:
    def __init__(self, ae):
        self.ae = ae.eval()

    def __call__(self, img) -> float:
        return float(autoencoder_score(self.ae, to_gray100(img)[None])[0])


# ── bundle loading ───────────────────────────────────────────────────────────
def _load_dinov2(backbone_id: str):
    from transformers import Dinov2Model
    return Dinov2Model.from_pretrained(backbone_id)


def load_scorer(cfg: dict[str, Any], bundle: Path):
    """Scorer for cfg["ood"]["method"], or None for "none". Raises if its artefacts are missing."""
    o = cfg.get("ood") or {}
    method = o.get("method", "none")
    if method == "none":
        return None
    if method == "mahalanobis_dinov2":
        with np.load(bundle / "ood_stats.npz") as st:
            return MahalanobisDinov2(_load_dinov2(o.get("backbone_id", DINOV2_ID)), st["mean"], st["precision"])
    if method == "clip_zeroshot":
        return ClipZeroShot(o.get("backbone_id", CLIP_ID), o.get("prompts_pos", DEFAULT_PROMPTS_POS),
                            o.get("prompts_neg", DEFAULT_PROMPTS_NEG))
    if method == "autoencoder":
        from safetensors.torch import load_file
        ae = build_autoencoder(100)
        ae.load_state_dict(load_file(str(bundle / "autoencoder.safetensors")), strict=True)
        return AutoencoderOOD(ae)
    raise ValueError(f"unknown ood method {method!r}")
