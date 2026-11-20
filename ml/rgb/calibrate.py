"""Temperature scaling, ECE and reliability diagram."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import torch
import torch.nn.functional as F


def fit_temperature(logits: np.ndarray, labels: np.ndarray) -> float:
    """Single scalar T > 0 minimising NLL of softmax(logits / T); optimised over log T with LBFGS."""
    z = torch.as_tensor(logits, dtype=torch.float64)
    y = torch.as_tensor(labels, dtype=torch.long)
    log_t = torch.zeros(1, dtype=torch.float64, requires_grad=True)
    opt = torch.optim.LBFGS([log_t], lr=0.5, max_iter=100, line_search_fn="strong_wolfe")

    def closure():
        opt.zero_grad()
        loss = F.cross_entropy(z / log_t.exp(), y)
        loss.backward()
        return loss

    opt.step(closure)
    return float(log_t.exp().item())


def softmax(logits: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    z = np.asarray(logits, dtype=np.float64) / temperature
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def _bins(probs: np.ndarray, labels: np.ndarray, n_bins: int):
    conf, pred = probs.max(1), probs.argmax(1)
    acc = (pred == labels).astype(float)
    idx = np.minimum((conf * n_bins).astype(int), n_bins - 1)
    return conf, acc, idx


def ece(probs: np.ndarray, labels: np.ndarray, n_bins: int = 15) -> float:
    """Expected calibration error (top-label confidence, equal-width bins)."""
    conf, acc, idx = _bins(np.asarray(probs), np.asarray(labels), n_bins)
    return float(sum((idx == b).mean() * abs(acc[idx == b].mean() - conf[idx == b].mean())
                     for b in range(n_bins) if (idx == b).any()))


def reliability_png(probs_before: np.ndarray, probs_after: np.ndarray, labels: np.ndarray,
                    path: Path, n_bins: int = 15) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(4.5, 4.5))
    ax.plot([0, 1], [0, 1], "k--", lw=1)
    for name, p in (("before", probs_before), ("after", probs_after)):
        conf, acc, idx = _bins(np.asarray(p), np.asarray(labels), n_bins)
        xs = [conf[idx == b].mean() for b in range(n_bins) if (idx == b).any()]
        ys = [acc[idx == b].mean() for b in range(n_bins) if (idx == b).any()]
        ax.plot(xs, ys, "o-", label=f"{name} (ECE {ece(p, labels, n_bins):.3f})")
    ax.set_xlabel("confidence"); ax.set_ylabel("accuracy"); ax.legend(); fig.tight_layout()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=120); plt.close(fig)
