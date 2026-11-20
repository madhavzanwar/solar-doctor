"""Fixtures: a tiny random timm bundle (no network, no real weights)."""
from __future__ import annotations

import io
import json

import pytest
from PIL import Image


def png_bytes(size=(80, 60), color=(120, 90, 60), noise=True) -> bytes:
    img = Image.new("RGB", size, color)
    if noise:
        px = img.load()
        for x in range(size[0]):
            for y in range(size[1]):
                px[x, y] = ((x * 7) % 256, (y * 5) % 256, (x + y) % 256)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def make_bundle(path, arch="test_resnet", img_size=64, seed=0, **overrides):
    import timm
    import torch
    from safetensors.torch import save_file

    from solardoctor.vision.model_def import CLASSES

    torch.manual_seed(seed)
    model = timm.create_model(arch, pretrained=False, num_classes=len(CLASSES))
    vit = arch.endswith("vit")
    cfg = {
        "model_version": "rgb-test-0001", "arch": "timm", "backbone_id": arch, "classes": list(CLASSES),
        "img_size": img_size, "grayscale": False, "temperature": 1.0, "conf_threshold": 0.6,
        "gradcam_target_layer": "blocks.1.norm1" if vit else "layer4",
        "gradcam_reshape": ({"type": "vit", "grid": img_size // 16, "prefix_tokens": 1} if vit else None),
        "ood": {"method": "none", "threshold": 0.0}, "metrics": {},
    }
    cfg.update(overrides)
    path.mkdir(parents=True, exist_ok=True)
    (path / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    save_file({k: v.contiguous() for k, v in model.state_dict().items()}, str(path / "model.safetensors"))
    return path


@pytest.fixture
def png():
    return png_bytes()


@pytest.fixture
def bundle_env(tmp_path, monkeypatch):
    """Factory: build a bundle, point SOLARDOCTOR_RGB_MODEL_DIR at it and reset the singleton."""
    from solardoctor.vision.classifier import reset_classifier

    def _make(**kw):
        d = make_bundle(tmp_path / "bundle", **kw)
        monkeypatch.setenv("SOLARDOCTOR_RGB_MODEL_DIR", str(d))
        reset_classifier()
        return d
    yield _make
    reset_classifier()


@pytest.fixture
def clf(bundle_env):
    from solardoctor.vision import get_classifier
    bundle_env()
    return get_classifier()
