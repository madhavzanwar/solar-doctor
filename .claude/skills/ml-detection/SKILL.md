---
name: ml-detection
description: Use when running, calling, or modifying YOLO11m thermal anomaly detection — the 11 canonical classes, severity mapping, the detection-dict shape, or inference via platform/core/detector.py. Read before touching anything that classifies thermal faults.
---

# ML Detection (YOLO11m, thermal IR)

## Model
- Weights: `ml/checkpoints/best.pt` — Ultralytics **YOLO11m**.
- Input: **640×640** (Ultralytics resizes automatically). Confidence threshold **0.25**.
- **Thermal IR only.** Never run on RGB images directly.

## Single source of truth — `ml/src/utils.py`
NEVER redefine classes, ids, or severities. Import them:
```python
from ml.src.utils import (
    CANONICAL_CLASSES, CLASS2ID, ID2CLASS,
    SEVERITY_MAP, SEVERITY_COLOR_BGR,
    draw_detections_severity, read_yolo_label, write_yolo_label,
    yolo_to_pixel, load_bgr, get_logger,
)
```
(Legacy code used `solar_thermal_detection.src.utils` — the canonical path is now `ml.src.utils`.)

## The 11 classes (order fixed, ids 0–10)
| id | class | severity |
|----|-------|----------|
| 0 | cell | MEDIUM |
| 1 | cell-multi | MEDIUM |
| 2 | module | MEDIUM |
| 3 | string | CRITICAL |
| 4 | bypass-diode | CRITICAL |
| 5 | offline-module | HIGH |
| 6 | vegetation-shading | LOW |
| 7 | soiling | LOW |
| 8 | short-circuit | HIGH |
| 9 | hot-spot-low | HIGH |
| 10 | hot-spot-high | CRITICAL |

## Detection dict (the contract every consumer expects)
```python
{
  "class": str,            # from CANONICAL_CLASSES
  "class_id": int,         # 0-10
  "confidence": float,
  "bbox": [x1, y1, x2, y2],     # pixel coords
  "bbox_norm": [cx, cy, w, h],  # YOLO normalized
  "severity": str,         # CRITICAL/HIGH/MEDIUM/LOW (from SEVERITY_MAP)
  "color_bgr": tuple,      # from SEVERITY_COLOR_BGR
}
```

## Running inference
The platform wraps the model in `platform/core/detector.py`. Quick standalone:
```python
from ultralytics import YOLO
results = YOLO('ml/checkpoints/best.pt')('ml/data/images/test/', conf=0.25)
```

## Gotchas
- Don't edit `ml/src/augmentation.py`, `ml/src/dataset.py`, or notebooks — training code, stable.
- Severity and color come ONLY from `utils.py`; never hardcode them in the API/reporting/frontend.
- See also: `analysis-pipeline` (how detections flow to reports), `reporting` (rendering).
