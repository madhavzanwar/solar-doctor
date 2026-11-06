# Interface: vision prediction (Workstream 2 → consumed by Workstream 3)

Status: **implemented** in `backend/solardoctor/vision/` (+ router `api/routers/vision.py`). Fields marked (stable) will not change.

## Python API (preferred for in-process use, e.g. the inspections service)

```python
from solardoctor.vision import get_classifier

clf = get_classifier()            # loaded once per process (bundle from SOLARDOCTOR_RGB_MODEL_DIR or HF, pinned revision)
result = clf.predict(image_bytes) # bytes of a JPEG/PNG/WebP; raises ValueError for undecodable input
exp = clf.explain(image_bytes, method="gradcam" | "lime", num_samples=600, top_k=5)
info = clf.info()                 # same body as GET /api/v1/vision/model
```

If no model bundle is available (no dir, no pinned revision, download or load failure, bad bundle),
`get_classifier()` raises `VisionModelUnavailable(reason)`; the HTTP layer returns 503
`{"detail": "rgb_model_unavailable"}` (reason is logged). Callers must not fabricate a diagnosis in that case.

Configuration (env): `SOLARDOCTOR_RGB_MODEL_DIR` (local bundle dir, wins), else Hugging Face
`SOLARDOCTOR_RGB_MODEL_REPO` (default `solar-doctor/solar-doctor-rgb`) at `SOLARDOCTOR_RGB_MODEL_REVISION`
(**required**, pinned). The model loads lazily on first use (never at import); at API startup it is warmed in a
background thread only if the dir or revision is set, and a failure there just keeps the 503. The classifier itself
never touches the hub when the bundle's `config.json` carries `hf_config` (hf_* archs); OOD methods
`mahalanobis_dinov2` / `clip_zeroshot` download their small backbone from the Hugging Face hub on first load,
pinned to `ood.backbone_revision` (commit sha) from the bundle config.

## HTTP

| Method | Path | Body | Response |
|---|---|---|---|
| GET | `/api/v1/vision/model` | – | model info (below) |
| POST | `/api/v1/vision/predict` | multipart `file` | `PredictResult` |
| POST | `/api/v1/vision/explain?method=gradcam\|lime&num_samples=600&top_k=5` | multipart `file` | `ExplainResult` |

Auth: same policy as other internal routers (viewer+ read; POST = operator+ in users mode). Also served on the
hidden legacy alias without the `/api/v1` prefix.

Upload validation (`file` multipart field): ≤ 15 MB (**413**: rejected up front when `Content-Length` exceeds 15 MB + 64 KB multipart allowance, before the form is read; the chunked read is still enforced), non-empty (**400**), sniffed by PIL, not
the client MIME: must be JPEG (incl. MPO phone/camera JPEGs)/PNG/WebP and ≤ 50 MP, else **422**. `/explain` query: `method` ∈ gradcam|lime,
`num_samples` 50..2000, `top_k` 1..20, else **422**. Model not loadable: **503**. CPU inference runs in a threadpool. `/explain` and `/predict` share one model guarded by one lock: explain calls are serialised with predict (a LIME run with many samples delays predictions), hence the 2000-sample cap (the report default is 600).

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
- `ood_score`: higher = more out-of-distribution (`is_ood = ood_score > threshold`); with `ood_method` `"none"` it is `null` and `is_ood` is false.
- `probs` keys follow `CLASSES` order; floats are unrounded.

## `ExplainResult`

```json
{"method": "gradcam", "target_class": "dusty", "png_base64": "<overlay PNG>", "mask": [[0.0, …], …],
 "mask_shape": [224, 224], "image_sha256": "…", "num_samples": null, "top_k": null, "cached": false}
```

- `mask` is `[img_size, img_size]` (the model's input size, not the upload's). `target_class` = the predicted class. Grad-CAM `mask`: float heatmap in [0,1] (3 decimals). LIME `mask`: int superpixel map, 1 = among top-k positive superpixels.
- XAI artefact URIs (`xai_uri_gradcam`, `xai_uri_lime` on `inspections`) are **owned by Workstream 3**: store
  `png_base64` via the object store and record the URI. Vision does not persist images.
- LIME results are cached in-process (LRU, 16 entries) by `(image_sha256, method, num_samples, top_k, model_version)`; a hit returns `cached: true`. Grad-CAM is not cached.
- Overlays: Grad-CAM = viridis blended at 45%; LIME = selected superpixels outlined in `--sun` (#c9852a), the rest dimmed.

## Model info (`GET /api/v1/vision/model`)

```json
{"name": "convnext_tiny.fb_in22k_ft_in1k", "model_version": "…", "classes": [...], "sha256": "<model.safetensors>",
 "source": "hf:solar-doctor/solar-doctor-rgb@<revision>" | "local:<bundle dir name>", "metrics": {...}, "temperature": 1.3,
 "conf_threshold": 0.6, "ood": {"method": "...", "threshold": ...}}
```
