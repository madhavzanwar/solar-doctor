# Interface: vision prediction (Workstream 2 → consumed by Workstream 3)

Status: **contract draft** — implementation in `backend/solardoctor/vision/`. Fields marked (stable) will not change.

## Python API (preferred for in-process use, e.g. the inspections service)

```python
from solardoctor.vision import get_classifier

clf = get_classifier()            # loaded once per process (bundle from SOLARDOCTOR_RGB_MODEL_DIR or HF, pinned revision)
result = clf.predict(image_bytes) # bytes of a JPEG/PNG/WebP; raises ValueError for undecodable input
exp = clf.explain(image_bytes, method="gradcam" | "lime", num_samples=600, top_k=5)
info = clf.info()                 # same body as GET /api/v1/vision/model
```

If no model bundle is available, `get_classifier()` raises `VisionModelUnavailable`; the HTTP layer returns 503
`{"detail": "rgb_model_unavailable"}`. Callers must not fabricate a diagnosis in that case.

## HTTP

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/v1/vision/model` | – | model info (below) |
| POST | `/api/v1/vision/predict` | multipart `file` | `PredictResult` |
| POST | `/api/v1/vision/explain?method=gradcam\|lime&num_samples=600&top_k=5` | multipart `file` | `ExplainResult` |

Auth: same policy as other internal routers (viewer+ read; POST = operator+ in users mode). Upload limit 15 MB.

## `PredictResult` (stable)

```json
{
  "model_version": "rgb-convnext_tiny-20261106-ab12cd3",
  "predicted_class": "dusty",
  "confidence": 0.87,
  "top3": [{"class": "dusty", "prob": 0.87}, {"class": "clean", "prob": 0.08}, {"class": "bird_drop", "prob": 0.03}],
  "probs": {"clean": 0.08, "dusty": 0.87, "bird_drop": 0.03, "snow_covered": 0.01, "electrical_damage": 0.005, "physical_damage": 0.005},
  "ood_score": 0.12,
  "ood_method": "mahalanobis_dinov2",
  "is_ood": false,
  "needs_field_check": false,
  "field_check_reason": null,
  "image_sha256": "…",
  "latency_ms": 85.3
}
```

- `confidence` = calibrated (temperature-scaled) max probability; `probs` sum to 1.
- `predicted_class` is always the argmax, even when `needs_field_check` is true (UI shows it greyed).
- `needs_field_check = is_ood or confidence < conf_threshold` (0.6); `field_check_reason` ∈
  `null | "out_of_distribution" | "low_confidence"` (OOD wins when both).
- `ood_score`: higher = more out-of-distribution; `ood_method` may be `"none"` (then `is_ood` is false).

## `ExplainResult`

```json
{"method": "gradcam", "target_class": "dusty", "png_base64": "<overlay PNG>", "mask": [[0.0, …], …],
 "mask_shape": [224, 224], "image_sha256": "…", "num_samples": null, "top_k": null, "cached": false}
```

- Grad-CAM `mask`: float heatmap in [0,1]. LIME `mask`: int superpixel map, 1 = among top-k positive superpixels.
- XAI artefact URIs (`xai_uri_gradcam`, `xai_uri_lime` on `inspections`) are **owned by Workstream 3**: store
  `png_base64` via the object store and record the URI. Vision does not persist images.
- LIME results are cached in-process by `(image_sha256, method, num_samples, top_k, model_version)`.

## Model info (`GET /api/v1/vision/model`)

```json
{"name": "convnext_tiny.fb_in22k_ft_in1k", "model_version": "…", "classes": [...], "sha256": "<model.safetensors>",
 "source": "hf:solar-doctor/solar-doctor-rgb@<revision>" , "metrics": {...}, "temperature": 1.3,
 "conf_threshold": 0.6, "ood": {"method": "...", "threshold": ...}}
```
