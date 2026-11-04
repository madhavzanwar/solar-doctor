#!/usr/bin/env python3
"""Evaluate a Weighted-Boxes-Fusion ensemble of two bake-off candidates.

Runs both models independently on every image in the held-out test split,
fuses their per-image detections with Weighted Boxes Fusion (WBF), and scores
the fused predictions against ground truth via pycocotools -- the same
test.json split and methodology used for the individual candidates, so the
result is directly comparable to ml/eval/results/*.

Usage:
    python3 -m ml.eval.ensemble_eval \
        --model-a ml/checkpoints/candidates/yolo11x_best.pt \
        --model-b ml/checkpoints/candidates/rtdetr_x_best.pt \
        --coco-json ml/data/combined_coco/test.json \
        --images-root ml/data/combined/test/images \
        --output ml/eval/results/ensemble_test_metrics.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from ml.src.utils import CANONICAL_CLASSES, get_logger

logger = get_logger(__name__)


def run_ensemble_eval(
    model_a_path: str,
    model_b_path: str,
    coco_json: str,
    images_root: str,
    output_path: str,
    conf: float = 0.25,
    iou_thr: float = 0.55,
    weights: tuple[float, float] = (1.0, 1.0),
) -> dict:
    """Run WBF-ensembled inference over every image and score against ground truth."""
    import numpy as np
    from ensemble_boxes import weighted_boxes_fusion
    from pycocotools.coco import COCO
    from pycocotools.cocoeval import COCOeval
    from ultralytics import YOLO

    coco_gt = COCO(coco_json)
    img_ids = coco_gt.getImgIds()
    cat_ids = sorted(coco_gt.getCatIds())  # COCO category ids, ordered

    model_a = YOLO(model_a_path)
    model_b = YOLO(model_b_path)
    images_root_p = Path(images_root)

    results_coco: list[dict] = []
    for img_id in img_ids:
        img_info = coco_gt.loadImgs([img_id])[0]
        img_path = images_root_p / img_info["file_name"]
        w, h = img_info["width"], img_info["height"]

        boxes_list, scores_list, labels_list = [], [], []
        for model in (model_a, model_b):
            preds = model(str(img_path), conf=conf, verbose=False)[0]
            if preds.boxes is None or len(preds.boxes) == 0:
                boxes_list.append([])
                scores_list.append([])
                labels_list.append([])
                continue
            xyxy = preds.boxes.xyxy.cpu().numpy()
            norm_boxes = xyxy / np.array([w, h, w, h])  # WBF expects [0,1]-normalised coords
            boxes_list.append(norm_boxes.tolist())
            scores_list.append(preds.boxes.conf.cpu().numpy().tolist())
            labels_list.append(preds.boxes.cls.cpu().numpy().astype(int).tolist())

        fused_boxes, fused_scores, fused_labels = weighted_boxes_fusion(
            boxes_list, scores_list, labels_list,
            weights=list(weights), iou_thr=iou_thr, skip_box_thr=conf,
        )

        for (x1, y1, x2, y2), score, label in zip(fused_boxes, fused_scores, fused_labels):
            px1, py1, px2, py2 = x1 * w, y1 * h, x2 * w, y2 * h
            results_coco.append({
                "image_id": img_id,
                "category_id": cat_ids[int(label)],
                "bbox": [px1, py1, px2 - px1, py2 - py1],
                "score": float(score),
            })

    if not results_coco:
        raise RuntimeError("Ensemble produced zero detections across the whole test set")

    coco_dt = coco_gt.loadRes(results_coco)
    ev = COCOeval(coco_gt, coco_dt, iouType="bbox")
    ev.evaluate()
    ev.accumulate()
    ev.summarize()

    map50_95 = float(ev.stats[0])
    map50 = float(ev.stats[1])

    per_class: dict[str, dict] = {}
    cat_id_to_name = {c["id"]: c["name"] for c in coco_gt.loadCats(cat_ids)}
    for idx, cat_id in enumerate(cat_ids):
        ev_cls = COCOeval(coco_gt, coco_dt, iouType="bbox")
        ev_cls.params.catIds = [cat_id]
        ev_cls.evaluate()
        ev_cls.accumulate()
        ap50 = ev_cls.eval["precision"][0, :, 0, 0, -1]
        ap50 = float(ap50[ap50 > -1].mean()) if (ap50 > -1).any() else 0.0
        name = cat_id_to_name.get(cat_id, CANONICAL_CLASSES[idx] if idx < len(CANONICAL_CLASSES) else str(cat_id))
        per_class[name] = {"precision": None, "recall": None, "ap50": ap50}

    result = {
        "model": f"ensemble(WBF): {model_a_path} + {model_b_path}",
        "split": "test",
        "map50": map50,
        "map50_95": map50_95,
        "per_class": per_class,
        "_note": "WBF ensemble of YOLO11x + RT-DETR-x, weights=%s, iou_thr=%s. "
                 "precision/recall left null (pycocotools reports AP/AR, not per-class P/R "
                 "in the Ultralytics sense)." % (weights, iou_thr),
    }
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text(json.dumps(result, indent=2))
    logger.info("Wrote %s", output_path)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model-a", required=True)
    parser.add_argument("--model-b", required=True)
    parser.add_argument("--coco-json", required=True)
    parser.add_argument("--images-root", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--iou-thr", type=float, default=0.55)
    parser.add_argument("--weight-a", type=float, default=1.0)
    parser.add_argument("--weight-b", type=float, default=1.0)
    args = parser.parse_args()

    result = run_ensemble_eval(
        args.model_a, args.model_b, args.coco_json, args.images_root, args.output,
        conf=args.conf, iou_thr=args.iou_thr, weights=(args.weight_a, args.weight_b),
    )
    print(f"mAP@0.5:      {result['map50']:.4f}")
    print(f"mAP@0.5:0.95: {result['map50_95']:.4f}")


if __name__ == "__main__":
    main()
