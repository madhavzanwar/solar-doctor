#!/usr/bin/env python3
"""Run YOLO11m validation on a dataset split and persist a metrics JSON.

Usage:
    python3 -m ml.eval.evaluate \
        --model ml/checkpoints/best.pt \
        --data ml/thermal_dataset.yaml \
        --split test \
        --output ml/eval/results/

Saves (under ml/eval/results/<timestamp>/):
    metrics.json          — mAP50, mAP50-95, per-class precision/recall/AP50
    confusion_matrix.png  — written by ultralytics (plots=True)
    *_curve.png           — PR/F1 curves (plots=True)

NOTE: requires the full thermal dataset referenced by the --data YAML, which is
stored outside the repo. CI/dev environments without the dataset cannot run this.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def run_eval(model_path: str, data_yaml: str, split: str, output_dir: str) -> dict:
    """Validate `model_path` on `split` of `data_yaml`, save + return metrics."""
    from ultralytics import YOLO  # imported lazily so import-only checks stay light

    model = YOLO(model_path)
    out = Path(output_dir) / datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)

    metrics = model.val(
        data=data_yaml,
        split=split,
        plots=True,
        save_json=True,
        project=str(out),
        name="val",
        exist_ok=True,
    )

    per_class = {
        name: {"precision": float(p), "recall": float(r), "ap50": float(ap)}
        for name, p, r, ap in zip(
            metrics.names.values(),
            metrics.box.p,
            metrics.box.r,
            metrics.box.ap50,
        )
    }

    result = {
        "model": model_path,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "split": split,
        "map50": float(metrics.box.map50),
        "map50_95": float(metrics.box.map),
        "per_class": per_class,
    }

    (out / "metrics.json").write_text(json.dumps(result, indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="ml/checkpoints/best.pt")
    parser.add_argument("--data", default="ml/thermal_dataset.yaml")
    parser.add_argument("--split", default="test")
    parser.add_argument("--output", default="ml/eval/results/")
    args = parser.parse_args()

    result = run_eval(args.model, args.data, args.split, args.output)
    print(f"mAP@0.5:      {result['map50']:.4f}")
    print(f"mAP@0.5:0.95: {result['map50_95']:.4f}")


if __name__ == "__main__":
    main()
