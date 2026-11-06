"""Bake-off registry: each entry = bundle config fields ("bundle") + training hyper-parameters ("hp").

B0 is a PyTorch reproduction of the team's original Keras VGG16 (100x100 gray); the autoencoder half of the
original idea lives in ood_eval.py. hp["mode"]: "finetune" (gradient training) or "probe" (frozen features +
sklearn LogisticRegression whose coefficients are copied into the model's `head`).
"""
from __future__ import annotations

IMAGENET = {"mean": [0.485, 0.456, 0.406], "std": [0.229, 0.224, 0.225]}
CLIP_NORM = {"mean": [0.48145466, 0.4578275, 0.40821073], "std": [0.26862954, 0.26130258, 0.27577711]}

_HP = dict(mode="finetune", epochs=30, patience=8, batch_size=32, lr=2e-4, head_lr_mult=10.0, weight_decay=0.05,
           layer_decay=None, ema=None, label_smoothing=0.0, warmup_epochs=2, trainable="all", amp=True)
_VIT = {"type": "vit", "grid": 16, "prefix_tokens": 1}


def _entry(arch, backbone_id, hp, img_size=224, grayscale=False, norm=IMAGENET, layer=None, reshape=None):
    return {"bundle": dict(arch=arch, backbone_id=backbone_id, img_size=img_size, grayscale=grayscale, **norm,
                           gradcam_target_layer=layer, gradcam_reshape=reshape),
            "hp": {**_HP, **hp}}


CONFIGS: dict[str, dict] = {
    "B0_gray100": _entry("torchvision", "vgg16", dict(lr=1e-4, weight_decay=1e-4, batch_size=64),
                         img_size=100, grayscale=True, layer="features.29"),
    "B0_rgb224": _entry("torchvision", "vgg16", dict(lr=1e-4, weight_decay=1e-4), layer="features.29"),
    "B1": _entry("timm", "efficientnet_b0.ra_in1k", dict(lr=5e-4, weight_decay=1e-2), layer="conv_head"),
    "B2": _entry("timm", "convnext_tiny.fb_in22k_ft_in1k",
                 dict(lr=2e-4, layer_decay=0.75, ema=0.99, label_smoothing=0.1), layer="stages.3"),
    "B3a": _entry("hf_dinov2", "facebook/dinov2-small", dict(mode="probe", batch_size=64),
                  layer="backbone.encoder.layer.11.norm1", reshape=_VIT),
    "B3b": _entry("hf_dinov2", "facebook/dinov2-small",
                  dict(epochs=25, lr=2e-5, head_lr_mult=50.0, trainable="dinov2_last4", label_smoothing=0.1),
                  layer="backbone.encoder.layer.11.norm1", reshape=_VIT),
    "B4": _entry("hf_clip", "openai/clip-vit-base-patch32", dict(mode="probe", batch_size=64), norm=CLIP_NORM,
                 layer="backbone.vision_model.encoder.layers.11.layer_norm1",
                 reshape={"type": "vit", "grid": 7, "prefix_tokens": 1}),
}


def hf_ids() -> list[str]:
    """Every Hugging Face repo id the registry downloads weights from."""
    ids = set()
    for e in CONFIGS.values():
        b = e["bundle"]
        if b["arch"] == "timm":
            ids.add("timm/" + b["backbone_id"])
        elif b["arch"].startswith("hf_"):
            ids.add(b["backbone_id"])
    return sorted(ids)
