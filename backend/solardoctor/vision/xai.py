"""Explainability helpers: Grad-CAM, LIME and PNG overlays.

Signatures are shared with the training code (faithfulness study) — keep them stable. Heavy imports are local so
importing `solardoctor.vision` never pulls in torch.
"""
from __future__ import annotations

import io
from typing import Any, Callable

import numpy as np
from PIL import Image

SUN = (201, 133, 42)        # DESIGN.md --sun (#c9852a): LIME superpixel outline
GRADCAM_ALPHA = 0.45        # DESIGN.md: viridis heatmap at 45% opacity
LIME_DIM = 0.6              # brightness of pixels outside the selected superpixels
LIME_SEGMENTS = 50


def gradcam_mask(model, cfg: dict[str, Any], x, target: int) -> np.ndarray:
    """Grad-CAM heatmap [S, S] float32 in [0, 1] for class `target`; x is a preprocessed [1, 3, S, S] tensor.

    Needs gradients, so call it outside torch.inference_mode().
    """
    import torch
    from pytorch_grad_cam import GradCAM
    from pytorch_grad_cam.utils.model_targets import ClassifierOutputTarget

    layer = model.get_submodule(cfg["gradcam_target_layer"])
    reshape = None
    spec = cfg.get("gradcam_reshape")
    if spec:
        if spec.get("type") != "vit":
            raise ValueError(f"unknown gradcam_reshape {spec!r}")
        grid, prefix = int(spec["grid"]), int(spec["prefix_tokens"])

        def reshape(t):  # (B, prefix + G*G, C) -> (B, C, G, G)
            t = t[:, prefix:, :]
            return t.reshape(t.size(0), grid, grid, t.size(2)).permute(0, 3, 1, 2)

    model.eval()
    with torch.enable_grad(), GradCAM(model=model, target_layers=[layer], reshape_transform=reshape) as cam:
        out = cam(input_tensor=x, targets=[ClassifierOutputTarget(int(target))])
    return out[0].astype(np.float32)


def lime_mask(predict_fn: Callable[[np.ndarray], np.ndarray], img_uint8: np.ndarray, target: int,
              num_samples: int, top_k: int, seed: int = 0):
    """LIME over ~50 SLIC superpixels. predict_fn maps uint8 [N,H,W,3] -> probabilities [N,C].

    Returns (mask, segments, weights): mask int[S,S] with 1 on the top_k positive-weight superpixels,
    segments int[S,S] superpixel ids, weights {segment_id: weight} for `target`.
    """
    from lime.lime_image import LimeImageExplainer
    from skimage.segmentation import slic

    exp = LimeImageExplainer(random_state=seed).explain_instance(
        img_uint8, predict_fn, labels=(int(target),), top_labels=None, hide_color=0,
        num_samples=int(num_samples), batch_size=32, random_seed=seed,
        segmentation_fn=lambda im: slic(im, n_segments=LIME_SEGMENTS, compactness=10, start_label=0),
    )
    weights = dict(exp.local_exp[int(target)])
    best = sorted((s for s, w in weights.items() if w > 0), key=lambda s: -weights[s])[:int(top_k)]
    mask = np.isin(exp.segments, best).astype(np.int32)
    return mask, exp.segments, weights


def overlay_png(img_uint8: np.ndarray, mask: np.ndarray, method: str) -> bytes:
    """PNG of the explanation: viridis heatmap blend (gradcam) or sun-coloured superpixel outlines (lime)."""
    base = img_uint8.astype(np.float32)
    if mask.shape != base.shape[:2]:
        raise ValueError("mask and image sizes differ")
    if method == "gradcam":
        import matplotlib
        heat = matplotlib.colormaps["viridis"](np.clip(mask, 0, 1))[..., :3] * 255
        out = (1 - GRADCAM_ALPHA) * base + GRADCAM_ALPHA * heat
    elif method == "lime":
        from skimage.segmentation import find_boundaries
        sel = mask.astype(bool)
        out = np.where(sel[..., None], base, base * LIME_DIM)
        out[find_boundaries(sel, mode="outer")] = SUN
    else:
        raise ValueError(f"unknown method {method!r}")
    buf = io.BytesIO()
    Image.fromarray(np.clip(out, 0, 255).astype(np.uint8)).save(buf, format="PNG")
    return buf.getvalue()
