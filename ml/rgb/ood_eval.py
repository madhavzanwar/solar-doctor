"""Compare 3 "is this a solar panel photo?" guards by AUROC, pick the best, write it into a bundle.

Score convention: higher = more out-of-distribution. Positives for AUROC = OOD images, negatives = in-distribution.
Protocol: the OOD images are split in half (seed 42) into OOD-dev and OOD-test. The method (best AUROC) and its
threshold (95th percentile of in-distribution scores) are chosen on val + OOD-dev only; every method's AUROC and
TPR/FPR at its frozen threshold are then reported on the test split + OOD-test.
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

import numpy as np

PROMPTS_POS = ["a photo of a solar panel"]
PROMPTS_NEG = ["a photo of a roof", "a photo of a person", "a photo of a document", "a photo of a car",
               "a photo of a tree"]
DINO_ID, CLIP_ID = "facebook/dinov2-small", "openai/clip-vit-base-patch32"
ARTEFACT = {"mahalanobis_dinov2": "ood_stats.npz", "autoencoder": "autoencoder.safetensors", "clip_zeroshot": None}


def evaluate_ood(in_scores: dict[str, np.ndarray], ood_scores: dict[str, np.ndarray]) -> dict:
    """AUROC per method, best method, and its 95th-percentile-of-in-distribution threshold with TPR/FPR."""
    from sklearn.metrics import roc_auc_score
    res = {}
    for m in in_scores:
        i, o = np.asarray(in_scores[m]), np.asarray(ood_scores[m])
        thr = float(np.percentile(i, 95))
        res[m] = {"auroc": float(roc_auc_score(np.r_[np.zeros(len(i)), np.ones(len(o))], np.r_[i, o])),
                  "threshold": thr, "tpr": float((o > thr).mean()), "fpr": float((i > thr).mean())}
    best = max(res, key=lambda m: res[m]["auroc"])
    return {"methods": res, "best": best, "n_in": len(i), "n_ood": len(o)}


def backbone_revision(model_id: str) -> str:
    """Commit sha of an OOD backbone: from reports/hf_ids.json if recorded, else asked from the hub."""
    p = Path(__file__).parent / "reports" / "hf_ids.json"
    rec = json.loads(p.read_text())["resolved"].get(model_id) if p.exists() else None
    if rec:
        return rec["sha"]
    from huggingface_hub import model_info
    return model_info(model_id).sha


def split_ood(names: list[str], seed: int = 42) -> tuple[list[str], list[str]]:
    """Deterministic OOD-dev / OOD-test halves of the (sorted) file names."""
    names = sorted(names)
    perm = np.random.default_rng(seed).permutation(len(names))
    h = len(names) // 2
    return sorted(names[i] for i in perm[:h]), sorted(names[i] for i in perm[h:])


def select_and_test(val_in: dict, dev_ood: dict, test_in: dict, test_ood: dict) -> dict:
    """Choose method + threshold on val/OOD-dev (`selection`); report all methods at frozen thresholds on test."""
    from sklearn.metrics import roc_auc_score
    sel = evaluate_ood(val_in, dev_ood)
    test = {}
    for m, v in sel["methods"].items():
        i, o = np.asarray(test_in[m]), np.asarray(test_ood[m])
        thr = v["threshold"]
        test[m] = {"auroc": float(roc_auc_score(np.r_[np.zeros(len(i)), np.ones(len(o))], np.r_[i, o])),
                   "threshold": thr, "tpr": float((o > thr).mean()), "fpr": float((i > thr).mean())}
    return {"best": sel["best"], "selection": sel,
            "test": {"methods": test, "n_in": len(i), "n_ood": len(o)}}


def train_autoencoder(gray: "torch.Tensor", device: str, epochs: int = 30, seed: int = 42):
    import torch
    from solardoctor.vision.model_def import build_autoencoder
    torch.manual_seed(seed)
    ae = build_autoencoder(100).to(device)
    opt = torch.optim.Adam(ae.parameters(), 1e-3)
    dl = torch.utils.data.DataLoader(gray, batch_size=32, shuffle=True)
    for _ in range(epochs):
        for x in dl:
            x = x.to(device)
            loss = torch.nn.functional.mse_loss(ae(x), x)
            opt.zero_grad(); loss.backward(); opt.step()
    return ae.cpu().eval()


def main() -> None:
    import pandas as pd
    import torch
    from PIL import Image
    from safetensors.torch import save_file
    from solardoctor.vision import ood
    from solardoctor.vision.model_def import load_image, preprocess

    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--manifest", default="ml/rgb/data/manifest.csv")
    ap.add_argument("--raw-dir", default="ml/rgb/data/raw")
    ap.add_argument("--ood-dir", default="ml/rgb/data/ood/coco")
    ap.add_argument("--device", default="cuda" if torch.cuda.is_available() else "cpu")
    ap.add_argument("--out", default="ml/rgb/reports/ood.json")
    a = ap.parse_args()

    df = pd.read_csv(a.manifest)
    load = lambda paths: [load_image(Path(p).read_bytes()) for p in paths]  # noqa: E731
    train_imgs = load(Path(a.raw_dir) / r for r in df[df.split == "train"].rel_path)
    val_imgs = load(Path(a.raw_dir) / r for r in df[df.split == "val"].rel_path)
    in_imgs = load(Path(a.raw_dir) / r for r in df[df.split == "test"].rel_path)
    dev_names, test_names = split_ood([p.name for p in Path(a.ood_dir).glob("*.jpg")])
    dev_imgs, ood_imgs = (load(Path(a.ood_dir) / n for n in ns) for ns in (dev_names, test_names))
    work = Path(a.out).parent / "_ood_work"; work.mkdir(parents=True, exist_ok=True)

    def gray100(imgs):
        return torch.as_tensor(np.stack([np.asarray(i.convert("L").resize((100, 100), Image.BILINEAR),
                                                    dtype=np.float32) / 255 for i in imgs]))[:, None]

    ae = train_autoencoder(gray100(train_imgs), a.device)
    save_file({k: v.contiguous() for k, v in ae.state_dict().items()}, str(work / "autoencoder.safetensors"))

    from transformers import Dinov2Model
    bb = Dinov2Model.from_pretrained(DINO_ID, revision=backbone_revision(DINO_ID)).eval()
    dcfg = {"img_size": 224}

    def dino(imgs):
        x = torch.as_tensor(np.stack([preprocess(i, dcfg) for i in imgs]))
        with torch.no_grad():
            return np.concatenate([ood.dinov2_features(bb, x[s:s + 32]) for s in range(0, len(x), 32)])

    mean, prec = ood.fit_mahalanobis(dino(train_imgs))
    np.savez(work / "ood_stats.npz", mean=mean, precision=prec)
    clip = ood.ClipZeroShot(CLIP_ID, PROMPTS_POS, PROMPTS_NEG, revision=backbone_revision(CLIP_ID))
    scorers = {"mahalanobis_dinov2": lambda im: ood.mahalanobis_score(dino(im), mean, prec),
               "clip_zeroshot": lambda im: clip.score(im),
               "autoencoder": lambda im: ood.autoencoder_score(ae, gray100(im))}
    score = lambda imgs: {m: f(imgs) for m, f in scorers.items()}  # noqa: E731
    res = select_and_test(score(val_imgs), score(dev_imgs), score(in_imgs), score(ood_imgs))
    res["split"] = {"ood_dev": dev_names, "ood_test": test_names, "seed": 42}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(res, indent=2))

    best, bundle = res["best"], Path(a.bundle)
    cfg = json.loads((bundle / "config.json").read_text())
    cfg["ood"] = {"method": best, "threshold": res["selection"]["methods"][best]["threshold"]}
    if best == "mahalanobis_dinov2":
        cfg["ood"].update(backbone_id=DINO_ID, backbone_revision=backbone_revision(DINO_ID))
    elif best == "clip_zeroshot":
        cfg["ood"].update(backbone_id=CLIP_ID, backbone_revision=backbone_revision(CLIP_ID),
                          prompts_pos=PROMPTS_POS, prompts_neg=PROMPTS_NEG)
    if ARTEFACT[best]:
        shutil.copy(work / ARTEFACT[best], bundle / ARTEFACT[best])
    (bundle / "config.json").write_text(json.dumps(cfg, indent=2))
    print(json.dumps(res, indent=2))


if __name__ == "__main__":
    main()
