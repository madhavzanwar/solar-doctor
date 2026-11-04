# Plan 05 — ML Evaluation Tooling
**Priority:** P2 | **Effort:** Medium
**Goal:** Add structured evaluation scripts so model quality can be measured, tracked, and compared after any change.

---

## Why

The current state: inference works (`ml/checkpoints/best.pt`), but there is no repeatable way to:
- Measure mAP@0.5 on the test set
- Compare a new checkpoint to the current best
- Detect per-class regression (e.g., "hot-spot-high recall dropped")

Without this, retraining is flying blind.

---

## What to Build

```
ml/
└── eval/
    ├── __init__.py
    ├── evaluate.py       ← CLI: runs YOLO val on test split, saves metrics JSON
    ├── compare.py        ← Compares two metrics JSONs, flags regressions
    └── confusion.py      ← Generates per-class confusion matrix PNG
```

---

## Implementation

### `ml/eval/evaluate.py`

```python
#!/usr/bin/env python3
"""
Usage:
    python -m ml.eval.evaluate \
        --model ml/checkpoints/best.pt \
        --data ml/thermal_dataset.yaml \
        --split test \
        --output ml/eval/results/

Saves:
    ml/eval/results/<timestamp>/metrics.json
    ml/eval/results/<timestamp>/confusion_matrix.png
    ml/eval/results/<timestamp>/PR_curve.png
"""
import argparse
import json
from datetime import datetime
from pathlib import Path
from ultralytics import YOLO

def run_eval(model_path: str, data_yaml: str, split: str, output_dir: str) -> dict:
    model = YOLO(model_path)
    metrics = model.val(data=data_yaml, split=split, plots=True, save_json=True)

    result = {
        "model": model_path,
        "timestamp": datetime.utcnow().isoformat(),
        "split": split,
        "map50": float(metrics.box.map50),
        "map50_95": float(metrics.box.map),
        "per_class": {
            cls: {"precision": float(p), "recall": float(r), "ap50": float(ap)}
            for cls, p, r, ap in zip(
                metrics.names.values(),
                metrics.box.p,
                metrics.box.r,
                metrics.box.ap50,
            )
        },
    }

    out = Path(output_dir) / datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    out.mkdir(parents=True, exist_ok=True)
    (out / "metrics.json").write_text(json.dumps(result, indent=2))
    return result

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="ml/checkpoints/best.pt")
    parser.add_argument("--data", default="ml/thermal_dataset.yaml")
    parser.add_argument("--split", default="test")
    parser.add_argument("--output", default="ml/eval/results/")
    args = parser.parse_args()
    result = run_eval(args.model, args.data, args.split, args.output)
    print(f"mAP@0.5: {result['map50']:.4f}")
```

### `ml/eval/compare.py`

```python
"""
Usage:
    python -m ml.eval.compare baseline.json new.json

Prints a table of per-class delta and flags regressions (>5% drop in AP50).
Exit code 1 if any CRITICAL class has regression.
"""
import json, sys

CRITICAL_CLASSES = {"hot-spot-high", "string", "bypass-diode"}
REGRESSION_THRESHOLD = 0.05  # 5% drop triggers warning

def compare(baseline_path: str, new_path: str) -> int:
    baseline = json.loads(open(baseline_path).read())
    new = json.loads(open(new_path).read())

    regressions = []
    print(f"{'Class':<25} {'Baseline AP50':>14} {'New AP50':>10} {'Delta':>8}")
    print("-" * 60)

    for cls in baseline["per_class"]:
        b_ap = baseline["per_class"][cls]["ap50"]
        n_ap = new["per_class"].get(cls, {}).get("ap50", 0.0)
        delta = n_ap - b_ap
        flag = " ⚠" if delta < -REGRESSION_THRESHOLD else ""
        print(f"{cls:<25} {b_ap:>14.4f} {n_ap:>10.4f} {delta:>+8.4f}{flag}")
        if delta < -REGRESSION_THRESHOLD and cls in CRITICAL_CLASSES:
            regressions.append(cls)

    if regressions:
        print(f"\nREGRESSION in CRITICAL classes: {regressions}")
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(compare(sys.argv[1], sys.argv[2]))
```

---

## Add to CI (optional)

In `.github/workflows/ci.yml`, add a step after tests:

```yaml
- name: Run ML regression check
  if: github.event_name == 'pull_request'
  run: |
    python -m ml.eval.evaluate --output /tmp/new_eval/
    python -m ml.eval.compare ml/eval/baseline/metrics.json /tmp/new_eval/*/metrics.json
```

Store a committed `ml/eval/baseline/metrics.json` as the reference point.

---

## Done When

- [ ] `python -m ml.eval.evaluate` runs to completion on test split
- [ ] Produces `metrics.json` with mAP50, mAP50-95, per-class AP50
- [ ] `python -m ml.eval.compare baseline.json new.json` prints delta table
- [ ] Exits 1 if a CRITICAL class regresses >5%
- [ ] `ml/eval/baseline/metrics.json` committed with current model's scores
