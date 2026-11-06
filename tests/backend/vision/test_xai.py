from __future__ import annotations

import base64
import io

import numpy as np
import pytest
from PIL import Image

from solardoctor.vision import xai


@pytest.mark.parametrize("arch,size", [("test_resnet", 64), ("test_vit", 160)])
def test_gradcam_mask_shape_and_range(bundle_env, png, arch, size):
    """CNN uses the plain target layer; the ViT bundle goes through the token reshape_transform."""
    from solardoctor.vision import get_classifier
    bundle_env(arch=arch, img_size=size)
    r = get_classifier().explain(png, "gradcam")
    m = np.array(r["mask"])
    assert m.shape == (size, size) and r["mask_shape"] == [size, size]
    assert m.min() >= 0.0 and m.max() <= 1.0
    assert (r["num_samples"], r["top_k"], r["cached"]) == (None, None, False)
    assert Image.open(io.BytesIO(base64.b64decode(r["png_base64"]))).size == (size, size)


def test_gradcam_mask_direct(bundle_env, png):
    import torch
    from solardoctor.vision import get_classifier
    from solardoctor.vision.model_def import load_image, preprocess
    bundle_env()
    c = get_classifier()
    x = torch.from_numpy(preprocess(load_image(png), c.cfg))[None]
    m = xai.gradcam_mask(c.model, c.cfg, x, 2)
    assert m.dtype == np.float32 and m.shape == (64, 64)


def test_lime_topk_and_cache(clf, png):
    r1 = clf.explain(png, "lime", num_samples=60, top_k=3)
    m = np.array(r1["mask"])
    assert m.shape == (64, 64) and set(np.unique(m)) <= {0, 1}
    assert r1["cached"] is False and (r1["num_samples"], r1["top_k"]) == (60, 3)
    assert r1["target_class"] == clf.predict(png)["predicted_class"]
    r2 = clf.explain(png, "lime", num_samples=60, top_k=3)
    assert r2["cached"] is True and r2["mask"] == r1["mask"]
    assert clf.explain(png, "lime", num_samples=60, top_k=4)["cached"] is False  # key includes top_k


def test_lime_mask_selects_at_most_topk_superpixels():
    img = np.random.default_rng(0).integers(0, 255, (48, 48, 3), dtype=np.uint8)
    # class 0 prob rises with brightness of the top-left quadrant -> some positive superpixels
    def fn(batch):
        p = batch[:, :24, :24].mean(axis=(1, 2, 3)) / 255.0
        return np.stack([p, 1 - p], axis=1)
    mask, seg, w = xai.lime_mask(fn, img, 0, num_samples=200, top_k=2)
    assert len(np.unique(seg[mask == 1])) <= 2
    assert mask.shape == seg.shape == (48, 48) and all(isinstance(k, (int, np.integer)) for k in w)


def test_overlay_png_decodes_and_differs():
    img = np.full((32, 32, 3), 200, dtype=np.uint8)
    heat = np.linspace(0, 1, 32 * 32, dtype=np.float32).reshape(32, 32)
    for method, mask in (("gradcam", heat), ("lime", (heat > 0.7).astype(int))):
        out = np.array(Image.open(io.BytesIO(xai.overlay_png(img, mask, method))))
        assert out.shape == (32, 32, 3) and not np.array_equal(out, img)
    lime = np.array(Image.open(io.BytesIO(xai.overlay_png(img, (heat > 0.7).astype(int), "lime"))))
    assert (lime == xai.SUN).all(axis=2).any()  # sun-coloured outline present
    with pytest.raises(ValueError):
        xai.overlay_png(img, heat, "nope")


def test_explain_rejects_bad_method(clf, png):
    with pytest.raises(ValueError):
        clf.explain(png, "shap")
