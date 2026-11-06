"""Trainer for the RGB bake-off: `cv` (per-fold models) and `final` (calibrated, benchmarked bundle).

Class imbalance: class-weighted cross-entropy (weights from ml.rgb.dataset.class_weights), no sampler.
Seeds: fold k uses seed+k for every config, so splits and seeds are identical across configs.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import random
import subprocess
import time
from datetime import date
from pathlib import Path

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import DataLoader

from ml.rgb.calibrate import ece, fit_temperature, reliability_png, softmax
from ml.rgb.configs import CONFIGS
from solardoctor.vision.model_def import CLASSES, build_model

N_CLASSES = len(CLASSES)


def seed_everything(seed: int) -> None:
    random.seed(seed); np.random.seed(seed); torch.manual_seed(seed); torch.cuda.manual_seed_all(seed)
    torch.backends.cudnn.deterministic = True


def git_short() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], text=True).strip()
    except Exception:
        return "nogit"


def sha256_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def metrics(logits: np.ndarray, labels: np.ndarray) -> dict:
    from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, recall_score
    rng = list(range(N_CLASSES))
    pred = logits.argmax(1)
    nll = F.cross_entropy(torch.as_tensor(logits, dtype=torch.float64), torch.as_tensor(labels)).item()
    return {"macro_f1": float(f1_score(labels, pred, labels=rng, average="macro", zero_division=0)),
            "accuracy": float(accuracy_score(labels, pred)),
            "per_class_recall": recall_score(labels, pred, labels=rng, average=None, zero_division=0).tolist(),
            "per_class_f1": f1_score(labels, pred, labels=rng, average=None, zero_division=0).tolist(),
            "confusion_matrix": confusion_matrix(labels, pred, labels=rng).tolist(), "nll": float(nll)}


@torch.no_grad()
def predict_logits(model, ds, device, bs: int = 64, amp: bool = False):
    model.eval().to(device)
    xs, ys = [], []
    for x, y in DataLoader(ds, batch_size=bs, shuffle=False, num_workers=0):
        with torch.autocast(device_type=device.split(":")[0], dtype=torch.float16, enabled=amp and "cuda" in device):
            xs.append(model(x.to(device)).float().cpu())
        ys.append(y)
    return torch.cat(xs).numpy(), torch.cat(ys).numpy()


def head_params(model) -> list:
    if hasattr(model, "head") and isinstance(model.head, nn.Linear) and hasattr(model, "backbone"):
        return list(model.head.parameters())
    if hasattr(model, "get_classifier"):
        return list(model.get_classifier().parameters())
    return list(model.classifier[-1].parameters())  # torchvision VGG


def set_trainable(model, mode: str) -> None:
    if mode == "all":
        return
    if mode != "dinov2_last4":
        raise ValueError(mode)
    for p in model.parameters():
        p.requires_grad = False
    keep = [model.head, model.backbone.layernorm] + list(model.backbone.encoder.layer[-4:])
    for m in keep:
        for p in m.parameters():
            p.requires_grad = True


def make_optimizer(model, hp: dict):
    """AdamW whose param groups carry `lr_scale`; effective lr = hp["lr"] * lr_scale * schedule (see `fit`).

    Head groups get an extra `head_lr_mult`; layer decay (timm) gives earlier layers smaller scales.
    """
    head = {id(p) for p in head_params(model)}
    if hp["layer_decay"]:
        from timm.optim import create_optimizer_v2
        opt = create_optimizer_v2(model, "adamw", lr=hp["lr"], weight_decay=hp["weight_decay"],
                                  layer_decay=hp["layer_decay"])
        for g in opt.param_groups:
            g["lr_scale"] = g.get("lr_scale", 1.0) * (hp["head_lr_mult"] if any(id(p) in head for p in g["params"])
                                                       else 1.0)
        return opt
    body = [p for p in model.parameters() if p.requires_grad and id(p) not in head]
    groups = [{"params": body, "lr": hp["lr"], "lr_scale": 1.0},
              {"params": [p for p in model.parameters() if id(p) in head], "lr": hp["lr"],
               "lr_scale": hp["head_lr_mult"]}]
    return torch.optim.AdamW(groups, weight_decay=hp["weight_decay"])


def set_lrs(opt, base_lr: float, factor: float) -> None:
    for g in opt.param_groups:
        g["lr"] = base_lr * g.get("lr_scale", 1.0) * factor


def fit(model, train_ds, val_ds, hp: dict, class_w: np.ndarray, device: str, seed: int):
    """Gradient fine-tuning; returns (best state_dict on CPU, best_epoch (1-based), history)."""
    seed_everything(seed)
    model.to(device)
    set_trainable(model, hp["trainable"])
    opt = make_optimizer(model, hp)
    bs = hp["batch_size"]
    dl = DataLoader(train_ds, batch_size=bs, shuffle=True, drop_last=len(train_ds) > bs, num_workers=0,
                    generator=torch.Generator().manual_seed(seed))
    total, warm = hp["epochs"] * len(dl), hp["warmup_epochs"] * len(dl)

    def lr_at(step: int) -> float:
        if step < warm:
            return (step + 1) / warm
        return 0.5 * (1 + math.cos(math.pi * (step - warm) / max(1, total - warm)))

    ema = None
    if hp["ema"]:
        from timm.utils import ModelEmaV3
        ema = ModelEmaV3(model, decay=hp["ema"])
    use_amp = hp["amp"] and "cuda" in device
    scaler = torch.amp.GradScaler("cuda", enabled=use_amp)
    loss_fn = nn.CrossEntropyLoss(weight=torch.as_tensor(class_w, dtype=torch.float32, device=device),
                                  label_smoothing=hp["label_smoothing"])
    best_f1, best_state, best_epoch, bad, hist, step = -1.0, None, 0, 0, [], 0
    for ep in range(1, hp["epochs"] + 1):
        model.train()
        tot = 0.0
        for x, y in dl:
            set_lrs(opt, hp["lr"], lr_at(step))
            x, y = x.to(device), y.to(device)
            with torch.autocast(device_type=device.split(":")[0], dtype=torch.float16, enabled=use_amp):
                loss = loss_fn(model(x).float(), y)
            opt.zero_grad(set_to_none=True)
            scaler.scale(loss).backward()
            scaler.step(opt); scaler.update()
            if ema:
                ema.update(model, step=step)
            tot += loss.item(); step += 1
        net = ema.module if ema else model
        lg, yv = predict_logits(net, val_ds, device, bs=bs, amp=use_amp)
        f1 = metrics(lg, yv)["macro_f1"]
        hist.append({"epoch": ep, "train_loss": tot / len(dl), "val_macro_f1": f1})
        if f1 > best_f1:
            best_f1, best_epoch, bad = f1, ep, 0
            best_state = {k: v.detach().cpu().clone() for k, v in net.state_dict().items()}
        else:
            bad += 1
            if bad >= hp["patience"]:
                break
    return best_state, best_epoch, hist


def fit_probe(model, train_ds, hp: dict, device: str, groups=None, seed: int = 42) -> float:
    """Frozen features + LogisticRegression (C by inner CV on the training part only); copies weights to head."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import GridSearchCV, StratifiedGroupKFold, StratifiedKFold
    seed_everything(seed)
    model.eval().to(device)
    feats, ys = [], []
    with torch.no_grad():
        for x, y in DataLoader(train_ds, batch_size=hp["batch_size"], num_workers=0):
            feats.append(model.features(x.to(device)).float().cpu()); ys.append(y)
    X, y = torch.cat(feats).numpy(), torch.cat(ys).numpy()
    cv = (StratifiedGroupKFold(5, shuffle=True, random_state=seed) if groups is not None
          else StratifiedKFold(5, shuffle=True, random_state=seed))
    gs = GridSearchCV(LogisticRegression(max_iter=3000, class_weight="balanced"),
                      {"C": [0.01, 0.1, 1.0, 10.0, 100.0]}, cv=cv, scoring="f1_macro")
    gs.fit(X, y, groups=groups)
    clf = gs.best_estimator_
    with torch.no_grad():
        model.head.weight.copy_(torch.as_tensor(clf.coef_, dtype=torch.float32))
        model.head.bias.copy_(torch.as_tensor(clf.intercept_, dtype=torch.float32))
    return float(gs.best_params_["C"])


def run_one(bundle_cfg: dict, hp: dict, train_ds, val_ds, test_ds, class_w, device: str, seed: int,
            groups=None, pretrained: bool = True):
    """Train one model; returns (model with best weights, result dict with val/test logits)."""
    model = build_model(bundle_cfg, pretrained=pretrained)
    t0 = time.time()
    extra = {}
    if hp["mode"] == "probe":
        extra["probe_C"] = fit_probe(model, train_ds, hp, device, groups, seed)
        best_epoch = 0
    else:
        state, best_epoch, extra["history"] = fit(model, train_ds, val_ds, hp, class_w, device, seed)
        model.load_state_dict(state)
    secs = time.time() - t0
    vl, vy = predict_logits(model, val_ds, device)
    tl, ty = predict_logits(model, test_ds, device)
    return model, {"best_epoch": best_epoch, "train_seconds": secs, "val_logits": vl, "val_y": vy,
                   "test_logits": tl, "test_y": ty, **extra}


def count_params(model) -> int:
    return sum(p.numel() for p in model.parameters())


def measure_latency(model, img_size: int, threads: int | None, n: int = 50, warm: int = 5) -> dict:
    """CPU latency (ms), batch 1, fp32. threads=None keeps torch's default thread count."""
    m = copy.deepcopy(model).cpu().eval()
    old = torch.get_num_threads()
    if threads:
        torch.set_num_threads(threads)
    x = torch.randn(1, 3, img_size, img_size)
    ts = []
    with torch.no_grad():
        for i in range(warm + n):
            t = time.perf_counter(); m(x); ts.append((time.perf_counter() - t) * 1000)
    torch.set_num_threads(old)
    ts = np.array(ts[warm:])
    return {"p50_ms": float(np.percentile(ts, 50)), "p95_ms": float(np.percentile(ts, 95))}


def write_bundle(model, bundle_cfg: dict, out_dir: Path, model_version: str, temperature: float,
                 metrics_: dict, conf_threshold: float = 0.6) -> Path:
    from safetensors.torch import save_file
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)
    cfg = {"model_version": model_version, **bundle_cfg, "classes": list(CLASSES), "temperature": temperature,
           "conf_threshold": conf_threshold,
           "ood": {"method": "none", "threshold": 0.0}, "metrics": metrics_}
    if bundle_cfg["arch"].startswith("hf_"):  # lets serving rebuild the backbone without any hub access
        cfg["hf_config"] = model.backbone.config.to_dict()
    (out_dir / "config.json").write_text(json.dumps(cfg, indent=2))
    save_file({k: v.detach().cpu().contiguous() for k, v in model.state_dict().items()},
              str(out_dir / "model.safetensors"))
    return out_dir


def confusion_png(cm, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(6, 5))
    ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(N_CLASSES), CLASSES, rotation=45, ha="right"); ax.set_yticks(range(N_CLASSES), CLASSES)
    for i in range(N_CLASSES):
        for j in range(N_CLASSES):
            ax.text(j, i, cm[i][j], ha="center", va="center")
    ax.set_xlabel("predicted"); ax.set_ylabel("true"); fig.tight_layout()
    fig.savefig(path, dpi=120); plt.close(fig)


def finalize(name: str, bundle_cfg: dict, model, res: dict, run_dir: Path, ckpt_root: Path) -> dict:
    """Temperature-fit on val, evaluate test raw + calibrated, benchmark, write bundle + final.json."""
    T = fit_temperature(res["val_logits"], res["val_y"])
    y = res["test_y"]
    raw, cal = metrics(res["test_logits"], y), metrics(res["test_logits"] / T, y)
    p_raw, p_cal = softmax(res["test_logits"]), softmax(res["test_logits"], T)
    raw["ece"], cal["ece"] = ece(p_raw, y), ece(p_cal, y)
    version = f"rgb-{name}-{date.today():%Y%m%d}-{git_short()}"
    run_dir.mkdir(parents=True, exist_ok=True)
    confusion_png(cal["confusion_matrix"], run_dir / "confusion_matrix.png")
    reliability_png(p_raw, p_cal, y, run_dir / "reliability.png")
    lat = {"threads1": measure_latency(model, bundle_cfg["img_size"], 1),
           "default": measure_latency(model, bundle_cfg["img_size"], None)}
    bundle_metrics = {"val_macro_f1": metrics(res["val_logits"], res["val_y"])["macro_f1"],
                      "test_macro_f1": cal["macro_f1"], "test_accuracy": cal["accuracy"],
                      "per_class_recall": cal["per_class_recall"], "ece_before": raw["ece"],
                      "ece_after": cal["ece"], "nll_before": raw["nll"], "nll_after": cal["nll"],
                      "latency_p95_ms": lat["default"]["p95_ms"]}
    out = write_bundle(model, bundle_cfg, ckpt_root / version, version, T, bundle_metrics)
    size_mb = (out / "model.safetensors").stat().st_size / 2**20
    final = {"config": name, "model_version": version, "bundle": str(out), "temperature": T,
             "best_epoch": res["best_epoch"], "train_seconds": res["train_seconds"],
             "test_raw": raw, "test_calibrated": cal, "params": count_params(model), "size_mb": size_mb,
             "latency": lat, "git_commit": git_short()}
    (run_dir / "final.json").write_text(json.dumps(final, indent=2))
    return final


def main() -> None:
    import pandas as pd
    from ml.rgb.dataset import RGBPanelDataset, class_weights

    ap = argparse.ArgumentParser()
    ap.add_argument("--config", required=True, choices=sorted(CONFIGS))
    ap.add_argument("--manifest", default="ml/rgb/data/manifest.csv")
    ap.add_argument("--raw-dir", default="ml/rgb/data/raw")
    ap.add_argument("--mode", choices=["cv", "final"], required=True)
    ap.add_argument("--folds", default="0,1,2,3,4")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--out", default="ml/rgb/runs")
    a = ap.parse_args()

    bcfg, hp = CONFIGS[a.config]["bundle"], CONFIGS[a.config]["hp"]
    ds_cfg = {**bcfg, **hp}
    df = pd.read_csv(a.manifest)
    raw = Path(a.raw_dir)
    probe = hp["mode"] == "probe"
    mk = lambda rows, train: RGBPanelDataset(rows.reset_index(drop=True), raw, ds_cfg, train=train)  # noqa: E731
    run_dir = Path(a.out) / a.config
    test_rows = df[df.split == "test"]

    if a.mode == "cv":
        pool = df[df.split != "test"]
        (run_dir / "cv").mkdir(parents=True, exist_ok=True)
        for k in [int(f) for f in a.folds.split(",")]:
            tr, va = pool[pool.fold != k], pool[pool.fold == k]
            model, res = run_one(bcfg, hp, mk(tr, not probe), mk(va, False), mk(test_rows, False),
                                 class_weights(tr.label.map(CLASSES.index).values), a.device, a.seed + k,
                                 groups=tr.group_id.values if probe else None)
            out = {"config": a.config, "fold": k, "seed": a.seed + k, "val": metrics(res["val_logits"], res["val_y"]),
                   "test": metrics(res["test_logits"], res["test_y"]), "best_epoch": res["best_epoch"],
                   "train_seconds": res["train_seconds"], "params": count_params(model),
                   "git_commit": git_short(), "manifest_sha256": sha256_file(Path(a.manifest))}
            (run_dir / "cv" / f"fold{k}.json").write_text(json.dumps(out, indent=2))
            print(f"{a.config} fold{k}: val F1 {out['val']['macro_f1']:.4f} test F1 {out['test']['macro_f1']:.4f}")
    else:
        tr, va = df[df.split == "train"], df[df.split == "val"]
        model, res = run_one(bcfg, hp, mk(tr, not probe), mk(va, False), mk(test_rows, False),
                             class_weights(tr.label.map(CLASSES.index).values), a.device, a.seed,
                             groups=tr.group_id.values if probe else None)
        f = finalize(a.config, bcfg, model, res, run_dir, Path("ml/rgb/checkpoints"))
        print(f"{f['model_version']}: test F1 {f['test_calibrated']['macro_f1']:.4f} "
              f"ECE {f['test_raw']['ece']:.3f}->{f['test_calibrated']['ece']:.3f}")


if __name__ == "__main__":
    main()
