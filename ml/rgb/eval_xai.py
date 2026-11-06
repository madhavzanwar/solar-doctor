"""Deletion/insertion faithfulness of Grad-CAM vs LIME on the test split for one bundle."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import torch

from ml.rgb.faithfulness import deletion_insertion_auc


def summarize(rows: list[dict]) -> dict:
    out = {}
    for m in ("deletion", "insertion"):
        v = np.array([r[m] for r in rows])
        out[m] = {"mean": float(v.mean()), "std": float(v.std())}
    out["n"] = len(rows)
    return out


def main() -> None:
    import pandas as pd
    from PIL import Image
    from ml.rgb.export_onnx import load_bundle
    from solardoctor.vision import xai
    from solardoctor.vision.model_def import load_image, preprocess

    ap = argparse.ArgumentParser()
    ap.add_argument("--bundle", required=True)
    ap.add_argument("--manifest", default="ml/rgb/data/manifest.csv")
    ap.add_argument("--raw-dir", default="ml/rgb/data/raw")
    ap.add_argument("--lime-samples", type=int, default=600)
    ap.add_argument("--max-images", type=int, default=0, help="0 = whole test split")
    ap.add_argument("--out", default="ml/rgb/reports/xai_faithfulness.json")
    a = ap.parse_args()

    model, cfg = load_bundle(Path(a.bundle))
    T, size = cfg["temperature"], cfg["img_size"]
    rows = pd.read_csv(a.manifest)
    rows = rows[rows.split == "test"]
    if a.max_images:
        rows = rows.sample(min(a.max_images, len(rows)), random_state=42)

    @torch.no_grad()
    def probs_t(x):  # tensor [N,3,S,S] -> calibrated probs
        return torch.softmax(model(x) / T, 1)

    def probs_u8(arr):  # uint8 [N,S,S,3] -> probs
        x = torch.as_tensor(np.stack([preprocess(Image.fromarray(i), cfg) for i in arr]))
        return probs_t(x).numpy()

    res = {"gradcam": [], "lime": []}
    for rel in rows.rel_path:
        img = load_image((Path(a.raw_dir) / rel).read_bytes()).resize((size, size))
        u8 = np.asarray(img)
        x = torch.as_tensor(preprocess(img, cfg))[None]
        target = int(probs_t(x).argmax())
        cam = xai.gradcam_mask(model, cfg, x, target)
        _, segments, weights = xai.lime_mask(probs_u8, u8, target, a.lime_samples, 5, 0)
        lime_sal = np.vectorize(lambda s: weights.get(s, 0.0))(segments)
        res["gradcam"].append(deletion_insertion_auc(probs_t, x, cam, target))
        res["lime"].append(deletion_insertion_auc(probs_t, x, lime_sal, target))
    out = {"bundle": cfg["model_version"], "lime_samples": a.lime_samples, "steps": 20,
           **{k: summarize(v) for k, v in res.items()}}
    Path(a.out).parent.mkdir(parents=True, exist_ok=True)
    Path(a.out).write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
