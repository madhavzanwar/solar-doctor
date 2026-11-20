"""Deletion / insertion AUC (RISE-style, Petsiuk et al. 2018).

Pixels are ranked by saliency; deletion replaces the most salient pixels by a blurred baseline step by step
(lower AUC = more faithful), insertion starts from the baseline and restores them (higher AUC = more faithful).
"""
from __future__ import annotations

import numpy as np
import torch
import torch.nn.functional as F


def _blur(x: torch.Tensor, k: int = 11) -> torch.Tensor:
    """Heavy box blur of a [1,3,S,S] tensor (baseline that keeps the colour statistics)."""
    return F.avg_pool2d(F.pad(x, (k // 2,) * 4, mode="reflect"), k, stride=1)


@torch.no_grad()
def deletion_insertion_auc(predict_fn, x: torch.Tensor, saliency: np.ndarray, target: int, steps: int = 20) -> dict:
    """predict_fn: tensor [N,3,S,S] -> probs [N,C]; x: [1,3,S,S]; saliency: [S,S]. Returns {"deletion","insertion"}."""
    s = x.shape[-1]
    order = torch.as_tensor(np.argsort(-np.asarray(saliency, dtype=np.float64).ravel(), kind="stable").copy())
    base = _blur(x)
    fracs = np.linspace(0, 1, steps + 1)
    rank = torch.empty(s * s, dtype=torch.long)
    rank[order] = torch.arange(s * s)  # rank 0 = most salient pixel
    imgs_del, imgs_ins = [], []
    for f in fracs:
        removed = (rank < round(f * s * s)).view(1, 1, s, s)
        imgs_del.append(torch.where(removed, base, x))
        imgs_ins.append(torch.where(removed, x, base))
    p = predict_fn(torch.cat(imgs_del + imgs_ins))[:, target]
    p = np.asarray(p.detach().cpu() if torch.is_tensor(p) else p, dtype=np.float64)
    n = len(fracs)
    return {"deletion": float(np.trapezoid(p[:n], fracs)), "insertion": float(np.trapezoid(p[n:], fracs))}
