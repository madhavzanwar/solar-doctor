# Thermal Anomaly Detection — Model Retraining & Architecture Bake-Off

**Date:** 2026-07-01
**Status:** Approved for planning

## Problem

The current production model (`ml/checkpoints/best.pt`) cannot be reproduced or improved from what's in this repo:

- `ml/thermal_dataset.yaml` points to `ml/data/combined`, which does not exist.
- `ml/Datasets/` contains three raw candidate datasets, none of which matches the canonical 11-class taxonomy defined in `ml/src/utils.py` (`CANONICAL_CLASSES`).
- The one prior training run recorded in-repo (`ml/runs/thermal/train/results.csv`) shows mAP/precision/recall stuck at 0 through 79 epochs — a stalled/failed run from the old `AxalonPIPE` repo, not a usable baseline.
- We have $300 of Google Cloud credit earmarked for this effort and no cost/VRAM constraint, since inference will run server-side (see Non-Goals).

This spec covers: (1) building a real, honestly-labeled combined training set from the datasets we actually have, and (2) training and comparing multiple detector architectures to pick the best model for production, using GCP GPU compute.

## Goals

- Produce a `ml/data/combined/` training set covering as many of the 11 canonical classes as the available data honestly supports, with a documented class-mapping table (source class → canonical class) for every source used.
- Train and evaluate three candidate architectures on the identical combined dataset:
  1. **YOLO11x** (Ultralytics)
  2. **RT-DETR-x** (Ultralytics)
  3. **Co-DETR** (MMDetection), with DINO as a fallback if Co-DETR training proves unstable
- Select a winner using `ml/eval/compare.py`-style per-class metrics, weighted toward CRITICAL-severity classes (`string`, `bypass-diode`, `hot-spot-high`), and promote it to `ml/checkpoints/best.pt`.
- Run all training on GCP Compute Engine within the $300 credit budget.
- Document `short-circuit` as a class with no real training data across all three sources, kept in the schema for downstream (severity map, API) compatibility but explicitly flagged as unsupported.

## Non-Goals

- Real-time or onboard (Jetson) inference. Detection today runs server-side, post-flight, via `platform/core/detector.py` with no latency constraint. Onboard deployment is a separate, future effort with its own model (likely a smaller/distilled architecture) — out of scope here.
- Sourcing new data for `short-circuit`. This spec documents the gap; filling it is future work.
- Any change to the detection dict schema, severity map, or platform API — this is purely a training/model-swap effort. `ml/src/utils.py` constants stay the source of truth.

## Dataset Plan

### Sources and their native format

| Source | Location | Format | Volume |
|---|---|---|---|
| Roboflow "Anomalies Detection" | `ml/Datasets/archive.zip` | YOLO detection (real bboxes), 8 classes, pre-augmented 3x by Roboflow | 7,339 images |
| InfraredSolarModules (Duke/RaptorMaps) | `ml/Datasets/InfraredSolarModules/` | Classification only, 24x40px crops, 12 classes | 20,000 images |
| PVMD dataset | `ml/Datasets/Photovoltaic module dataset....zip` (contains `.rar`) | Classification only (folder-per-class), 512x512 | ~1,003 images |

### Class mapping (source -> canonical)

`archive.zip` (8 classes, real bboxes -- kept as real detection labels):

| Source class | Canonical class |
|---|---|
| MultiByPassed, SingleByPassed | bypass-diode |
| MultiDiode, SingleDiode | bypass-diode |
| MultiHotSpot | cell-multi |
| SingleHotSpot | hot-spot-low |
| StringOpenCircuit, StringReversedPolarity | string |

`InfraredSolarModules` (12 classes, classification -> weak full-crop bbox):

| Source class | Canonical class |
|---|---|
| Cell | cell |
| Cell-Multi | cell-multi |
| Cracking | module |
| Hot-Spot | hot-spot-low |
| Hot-Spot-Multi | hot-spot-high |
| Shadowing, Vegetation | vegetation-shading |
| Diode, Diode-Multi | bypass-diode |
| Soiling | soiling |
| Offline-Module | offline-module |
| No-Anomaly | dropped / used as background negatives only |

`PVMD` (3 classes, classification -> weak full-crop bbox):

| Source class | Canonical class |
|---|---|
| Cracks | module |
| Hotspots | hot-spot-high |
| Shadings | vegetation-shading |

**Known gap:** `short-circuit` has zero examples across all three sources. It stays in `CANONICAL_CLASSES` / `SEVERITY_MAP` for schema compatibility, but the trained model will have no real signal for it. This must be stated plainly in the training report and is not blocking.

### Weak-label bbox strategy

For classification-only sources (InfraredSolarModules, PVMD), each crop becomes one detection label with a bbox covering the full image extent (normalized `[0.5, 0.5, 1.0, 1.0]` in YOLO format, or a small inset like `0.95` extent to avoid teaching the model to always predict full-frame boxes). This is standard practice for bootstrapping detection training from classification crops. `No-Anomaly` crops from InfraredSolarModules are used unlabeled as background negatives (images with an empty label file) to reduce false positives, capped at a reasonable ratio (e.g. 1:1 against real anomaly images) so negatives don't dominate.

### Pipeline implementation

Extend the existing `ml/scripts/prepare_dataset.py` (not a new script) to:
1. Extract and normalize all three sources into a common intermediate format.
2. Apply the class-mapping tables above.
3. Generate weak bboxes for classification sources.
4. Split into train/val/test (stratified by class where possible, respecting any existing splits from `archive.zip`).
5. Write output to `ml/data/combined/{train,val,test}/{images,labels}` matching what `ml/thermal_dataset.yaml` already expects -- no config changes needed there.
6. Emit a class-distribution report (counts per canonical class per split) so imbalance is visible before training starts, not discovered after.

## Model Bake-Off

All three candidates train on the identical `ml/data/combined` dataset for a fair comparison.

### 1. YOLO11x (Ultralytics)

Reuse `ml/configs/thermal.yaml`, swapping `model: yolo11m.pt` -> `yolo11x.pt`. Keep the existing thermal-tuned augmentation (no hue/saturation, brightness jitter, small rotation, mosaic/mixup/copy-paste) and AdamW/cos_lr schedule. Largest model in the YOLO11 family Ultralytics ships -- best accuracy ceiling within that family.

### 2. RT-DETR-x (Ultralytics)

Same training entrypoint and dataset format as YOLO11x (Ultralytics supports RT-DETR natively) -- minimal extra pipeline work. Transformer-based; historically stronger than YOLO on small/dense objects, which matters here since hot-spots and cell defects are small targets in full-panel-field imagery.

### 3. Co-DETR (MMDetection)

Requires:
- Converting `ml/data/combined` YOLO-format labels to COCO JSON.
- A separate MMDetection training config (not reusing `ml/configs/thermal.yaml`).
- DINO as a documented fallback if Co-DETR training is unstable or fails to converge on our dataset size (Co-DETR's collaborative-head training is more hyperparameter-sensitive than YOLO/RT-DETR).

Currently near the top of COCO leaderboards, particularly for small-object detection -- the candidate most likely to beat YOLO/RT-DETR on accuracy, at the cost of more engineering surface.

### Evaluation & selection

- Run all three checkpoints through `ml/eval/evaluate.py` and `ml/eval/compare.py` against each other and against the current `best.pt` baseline.
- Report per-class precision/recall/mAP50-95, with explicit extra weight on CRITICAL-severity classes (`string`, `bypass-diode`, `hot-spot-high`) since those drive real-world remediation priority.
- Winner is promoted to `ml/checkpoints/best.pt`; the other two runs' weights remain under `ml/runs/` for reference, not deployed.
- `short-circuit` is reported with zero/near-zero support explicitly -- not silently omitted from the report.

## Compute Plan (GCP, $300 budget)

- **Compute Engine VM, single GPU (L4 or better), spot/preemptible.** No need to economize on GPU tier given budget -- pick whatever's available and cost-effective at spot pricing.
- Persistent disk to hold `ml/data/combined` (avoids re-uploading on every VM restart).
- Startup script: clone repo, mount dataset disk, kick off training, auto-shutdown on completion to avoid idle billing.
- Checkpointing via `save_period` (already configured in `ml/configs/thermal.yaml`) so spot preemption doesn't lose more than a few epochs of progress.
- Budget comfortably covers three training runs (YOLO11x, RT-DETR-x, Co-DETR) plus one hyperparameter follow-up run on the eventual winner.

## Risks

- **Weak-label bboxes are noisy supervision.** Full-crop boxes from classification data are a known-imperfect proxy; if a candidate model overfits to "always predict full-frame," tighten the synthetic bbox inset or downweight classification-derived samples in the loss.
- **Co-DETR engineering cost.** MMDetection is a different ecosystem from Ultralytics; if setup/label-conversion consumes disproportionate time, DINO (simpler MMDetection config) or dropping this candidate are acceptable fallbacks -- YOLO11x/RT-DETR-x still deliver a usable result on their own.
- **Class imbalance.** `archive.zip`'s `StringReversedPolarity` (30 labels) and the near-total absence of `short-circuit` mean per-class metrics for rare classes will be noisy regardless of architecture -- report this rather than over-interpreting small-sample metrics.
- **Spot preemption.** Mitigated by periodic checkpointing; a preempted run resumes from `last.pt` rather than restarting.
