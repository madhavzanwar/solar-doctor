# ml/rgb — 6-class RGB panel defect classifier (Prompt 2, Workstream 2)

Classes (fixed order, index = logit index): `clean, dusty, bird_drop, snow_covered, electrical_damage, physical_damage`
(`solardoctor.vision.model_def.CLASSES`). Architecture + preprocessing live in
`backend/solardoctor/vision/model_def.py` and are shared by training and serving.

Dataset: Kaggle "Solar Panel Images Clean and Faulty" (pythonafroz/solar-panel-images), licence **Unknown**:
trained privately, images are never committed or redistributed. Raw data: `ml/rgb/data/raw/` (gitignored).

## Contract 1 — manifest `ml/rgb/data/manifest.csv` (committed; file names + hashes only)

| column | meaning |
|---|---|
| `rel_path` | path relative to `ml/rgb/data/raw/` (forward slashes) |
| `label` | normalised class name (one of the 6) |
| `sha256` | of the file bytes |
| `phash`, `dhash` | hex strings from `imagehash` (hash_size 8) |
| `group_id` | int; near-duplicates share a group (transitive edges: pHash **or** dHash Hamming ≤ 6, minimised over the other image's hflip/vflip/rot90/180/270 variants; **or** DINOv2-small cosine ≥ 0.95 unless `--no-embed`); a group never spans splits |
| `split` | `train` / `val` / `test` (≈70/15/15, stratified by label, grouped by group_id) |
| `fold` | 0-4 for train+val rows (5-fold StratifiedGroupKFold over train+val), -1 for test |

Exact duplicates (same sha256) keep one row; dropped rows are listed in `ml/rgb/data/removed.csv`
(`rel_path, reason, kept_rel_path`).

## Contract 2 — model bundle directory (`ml/rgb/checkpoints/<model_version>/`, gitignored; same layout on HF)

- `config.json`:
  ```json
  {"model_version": "rgb-convnext_tiny-20261106-ab12cd3", "arch": "timm|torchvision|hf_dinov2|hf_clip",
   "backbone_id": "convnext_tiny.fb_in22k_ft_in1k", "classes": [...6...], "img_size": 224, "grayscale": false,
   "mean": [0.485,0.456,0.406], "std": [0.229,0.224,0.225], "temperature": 1.0, "conf_threshold": 0.6,
   "gradcam_target_layer": "stages.3", "gradcam_reshape": null,
   "ood": {"method": "none|mahalanobis_dinov2|clip_zeroshot|autoencoder", "threshold": 0.0,
           "backbone_id": "facebook/dinov2-small", "prompts_pos": [...], "prompts_neg": [...]},
   "metrics": {}}
  ```
  `gradcam_target_layer` is a dotted module path inside the model (`"backbone.encoder.layer.11.norm1"` for DINOv2);
  `gradcam_reshape` is `null` for CNNs or `{"type": "vit", "grid": 16, "prefix_tokens": 1}` for ViTs.
  OOD score convention: **higher = more out-of-distribution**; `is_ood = score > threshold`.
- `model.safetensors`: `state_dict` of `build_model(config)`.
- `model.onnx` (opset 17, input `pixel_values` float32 [N,3,S,S], output `logits`), optional.
- `ood_stats.npz` (`mean` [D], `precision` [D,D]) for `mahalanobis_dinov2`; `autoencoder.safetensors` for
  `autoencoder` (`build_autoencoder(100)`, grayscale 100×100 in [0,1]).

## Contract 3 — inference

See `docs/solardoctor/interfaces/vision-predict.md`.
