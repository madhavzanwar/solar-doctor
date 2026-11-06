"""Single source of truth for the RGB classifier's architecture and preprocessing.

Training (`ml/rgb/`) and serving (`solardoctor.vision`) both import from here, so a bundle trained by one is
loadable by the other. A *bundle* is a directory with `config.json` + `model.safetensors` (+ optional
`model.onnx`, `ood_stats.npz`, `autoencoder.safetensors`); see `ml/rgb/README.md` for the full schema.
"""
from __future__ import annotations

import io
from typing import Any

import numpy as np
from PIL import Image, ImageOps

CLASSES: tuple[str, ...] = (
    "clean", "dusty", "bird_drop", "snow_covered", "electrical_damage", "physical_damage",
)
IMAGENET_MEAN = (0.485, 0.456, 0.406)
IMAGENET_STD = (0.229, 0.224, 0.225)


def load_image(data: bytes | Image.Image) -> Image.Image:
    """Bytes or PIL -> RGB PIL with EXIF orientation applied. Raises ValueError on undecodable input."""
    if isinstance(data, Image.Image):
        img = data
    else:
        try:
            img = Image.open(io.BytesIO(data))
            img.load()
        except Exception as exc:  # PIL raises many types for bad input
            raise ValueError(f"not a decodable image: {exc}") from exc
    return ImageOps.exif_transpose(img).convert("RGB")


def shrink(img: Image.Image, img_size: int) -> Image.Image:
    """Step 1 of the eval resize: BILINEAR downscale so the shorter side is round(img_size*256/224) (if larger).

    Idempotent; the training dataset caches this, so cached eval tensors equal `preprocess` on the original.
    """
    target = round(img_size * 256 / 224)
    m = min(img.size)
    if m <= target:
        return img
    s = target / m
    return img.resize((round(img.width * s), round(img.height * s)), Image.BILINEAR)


def preprocess(img: Image.Image, cfg: dict[str, Any]) -> np.ndarray:
    """RGB PIL -> float32 CHW array (`shrink`, BILINEAR square resize to img_size, optional grayscale, normalise).

    The training *eval* transform must produce exactly this; train-time augmentation happens before it.
    """
    size = int(cfg["img_size"])
    img = shrink(img, size)
    if cfg.get("grayscale"):
        img = img.convert("L").convert("RGB")  # 3 identical channels so ImageNet backbones still fit
    arr = np.asarray(img.resize((size, size), Image.BILINEAR), dtype=np.float32) / 255.0
    mean = np.asarray(cfg.get("mean", IMAGENET_MEAN), dtype=np.float32)
    std = np.asarray(cfg.get("std", IMAGENET_STD), dtype=np.float32)
    return ((arr - mean) / std).transpose(2, 0, 1).copy()


def build_model(cfg: dict[str, Any], pretrained: bool = False):
    """Build the classifier nn.Module described by cfg["arch"] / cfg["backbone_id"] with len(classes) outputs.

    arch:
      - "timm":        timm.create_model(backbone_id, num_classes=n)
      - "torchvision": torchvision VGG16 (backbone_id "vgg16"), last classifier layer replaced (works at 100x100)
      - "hf_dinov2":   transformers Dinov2Model + Linear on [CLS ‖ mean(patch tokens)]
      - "hf_clip":     transformers CLIPVisionModelWithProjection + Linear on image_embeds
    pretrained=False never downloads weights. For HF archs, if cfg["hf_config"] (the backbone's `config.to_dict()`,
    written into every trained bundle) is present the backbone is built from it, so serving never touches the
    network; without it the small config.json is fetched from the hub.
    """
    import torch.nn as nn

    n = len(cfg.get("classes", CLASSES))
    arch, bid = cfg["arch"], cfg["backbone_id"]
    if arch == "timm":
        import timm
        return timm.create_model(bid, pretrained=pretrained, num_classes=n)
    if arch == "torchvision":
        import torchvision
        if bid != "vgg16":
            raise ValueError(f"unsupported torchvision backbone {bid!r}")
        m = torchvision.models.vgg16(weights="IMAGENET1K_V1" if pretrained else None)
        m.classifier[-1] = nn.Linear(m.classifier[-1].in_features, n)
        return m
    if arch in ("hf_dinov2", "hf_clip"):
        return _HFHead(arch, bid, n, pretrained, cfg.get("hf_config"))
    raise ValueError(f"unknown arch {arch!r}")


def _hf_head_cls():  # defined lazily so importing this module never imports torch/transformers
    import torch
    import torch.nn as nn

    class HFHead(nn.Module):
        def __init__(self, arch: str, bid: str, n: int, pretrained: bool, hf_config: dict | None = None):
            super().__init__()
            self.arch = arch
            if arch == "hf_dinov2":
                from transformers import Dinov2Config, Dinov2Model
                self.backbone = (Dinov2Model.from_pretrained(bid) if pretrained else Dinov2Model(
                    Dinov2Config(**hf_config) if hf_config else Dinov2Config.from_pretrained(bid)))
                dim = 2 * self.backbone.config.hidden_size
            else:
                from transformers import CLIPVisionConfig, CLIPVisionModelWithProjection
                self.backbone = (CLIPVisionModelWithProjection.from_pretrained(bid) if pretrained
                                 else CLIPVisionModelWithProjection(
                                     CLIPVisionConfig(**hf_config) if hf_config
                                     else CLIPVisionConfig.from_pretrained(bid)))
                dim = self.backbone.config.projection_dim
            self.head = nn.Linear(dim, n)

        def features(self, x: "torch.Tensor") -> "torch.Tensor":
            out = self.backbone(pixel_values=x)
            if self.arch == "hf_dinov2":
                h = out.last_hidden_state
                return torch.cat([h[:, 0], h[:, 1:].mean(1)], dim=1)
            return out.image_embeds

        def forward(self, x: "torch.Tensor") -> "torch.Tensor":
            return self.head(self.features(x))

    return HFHead


def _HFHead(arch: str, bid: str, n: int, pretrained: bool, hf_config: dict | None = None):
    return _hf_head_cls()(arch, bid, n, pretrained, hf_config)


def build_autoencoder(img_size: int = 100):
    """Small conv autoencoder on grayscale img_size x img_size (the team's original OOD idea).

    Input/output: (B, 1, H, W) in [0, 1]; OOD score = per-image mean squared reconstruction error.
    """
    import torch.nn as nn

    if img_size % 4:
        raise ValueError("img_size must be divisible by 4")
    return nn.Sequential(
        nn.Conv2d(1, 32, 3, stride=2, padding=1), nn.ReLU(),
        nn.Conv2d(32, 64, 3, stride=2, padding=1), nn.ReLU(),
        nn.ConvTranspose2d(64, 32, 4, stride=2, padding=1), nn.ReLU(),
        nn.ConvTranspose2d(32, 1, 4, stride=2, padding=1), nn.Sigmoid(),
    )
