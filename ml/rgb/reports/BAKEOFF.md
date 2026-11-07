# SolarDoctor RGB classifier bake-off

## Method

- Source data: Hugging Face dataset `metalmerge/solar-panel-inspection` @ 1b62720 (a 789-image mirror/subset of Kaggle
  "Solar Panel Images Clean and Faulty"; licence unknown on both: trained privately, never redistributed).
- Exact duplicates removed by sha256; near-duplicates grouped (pHash or dHash Hamming <= 6 incl. flip/rotation variants, or DINOv2-small cosine >= 0.95; transitive).
- Group-aware stratified split 70/15/15 (train/val/test) so a duplicate group never spans splits; 5-fold
  StratifiedGroupKFold over train+val. The test split is never used for selection.
- Same splits and seeds (seed + fold) for every config; epoch selection and model selection by validation macro-F1.
- Class imbalance: class-weighted cross-entropy. Temperature scaling is fitted on the validation split only, the same split used for epoch
  selection (so calibration on val is slightly optimistic; the reported test ECE/NLL are held-out).
- B0_gray100 is a PyTorch reproduction of the original Keras VGG16 (100x100 grayscale).

## Model comparison (5-fold CV, mean ± std)

| config | val macro-F1 (epoch selected on this fold, optimistic) | held-out test macro-F1 (mean ± std of the 5 fold models) | val accuracy | params | size MB | CPU p95 ms |
|---|---|---|---|---|---|---|
| B0_gray100 | 0.7085 ± 0.0160 | 0.7162 ± 0.0302 | 0.7133 ± 0.0284 | 134,285,126 | 512.3 | 284.4 |
| B0_rgb224 | 0.8566 ± 0.0197 | 0.8255 ± 0.0156 | 0.8599 ± 0.0230 | 134,285,126 | 512.3 | 241.0 |
| B1 | 0.8023 ± 0.0355 | 0.7720 ± 0.0267 | 0.8035 ± 0.0389 | 4,015,234 | 15.5 | 132.0 |
| B2 | 0.8696 ± 0.0126 | 0.7976 ± 0.0166 | 0.8663 ± 0.0159 | 27,824,742 | 106.2 | 163.4 |
| B3a | 0.8199 ± 0.0304 | 0.7694 ± 0.0294 | 0.8309 ± 0.0268 | 22,061,190 | 84.2 | 263.8 |
| B3b (winner) | 0.8969 ± 0.0247 | 0.8555 ± 0.0221 | 0.9002 ± 0.0232 | 22,061,190 | 84.2 | 300.3 |
| B4 | 0.7852 ± 0.0129 | 0.8161 ± 0.0195 | 0.7938 ± 0.0171 | 87,852,294 | 335.2 | 306.2 |

The CV val column is optimistic: each fold's epoch is selected on that same fold. The held-out test column is the unbiased estimate.

Winner (val macro-F1 mean; ties: latency, then size): **B3b**

## Winner: held-out test metrics

Model version: `rgb-B3b-20261106-07cf786`; temperature 0.6785

| metric | raw | calibrated |
|---|---|---|
| macro-F1 | 0.8545 | 0.8545 |
| accuracy | 0.8544 | 0.8544 |
| NLL | 0.4170 | 0.3848 |
| ECE (15 bins) | 0.0787 | 0.0619 |

| class | recall | F1 |
|---|---|---|
| clean | 0.9583 | 0.8679 |
| dusty | 0.6500 | 0.7429 |
| bird_drop | 0.8824 | 0.8333 |
| snow_covered | 0.9412 | 0.9697 |
| electrical_damage | 0.7692 | 0.8333 |
| physical_damage | 0.9167 | 0.8800 |

Confusion matrix (rows = true, cols = predicted):

```
  23    1    0    0    0    0
   4   13    2    0    0    1
   1    1   15    0    0    0
   1    0    0   16    0    0
   0    0    2    0   10    1
   0    0    0    0    1   11
```

## OOD guard (AUROC, OOD = positive)

Selection protocol: the 100 COCO images are split 50/50 (seed 42) into OOD-dev and OOD-test. Method (best AUROC) and threshold (95th percentile of in-distribution scores) were chosen on the **val** split + OOD-dev only. Numbers below are on the **test** split + OOD-test at each method's frozen threshold.

| method | AUROC | threshold | TPR | FPR |
|---|---|---|---|---|
| mahalanobis_dinov2 (chosen) | 1.0000 | 53.2615 | 1.0000 | 0.0680 |
| clip_zeroshot | 0.9988 | 0.2005 | 1.0000 | 0.0583 |
| autoencoder | 0.3194 | 0.0021 | 0.0000 | 0.0388 |

Caveat: AUROC 1.0 is on far-OOD COCO val2017 images (n=50 in OOD-test), and the chosen threshold still flags 6.8 % of in-distribution test images (FPR). It is likely optimistic for near-OOD inputs (roofs, other equipment, rooftop clutter, drone views of buildings) and is not evidence of near-OOD robustness.

## XAI faithfulness (deletion: lower is better; insertion: higher is better)

| method | deletion AUC | insertion AUC | test images |
|---|---|---|---|
| gradcam | 0.6019 ± 0.2847 | 0.7996 ± 0.1853 | 30 |
| lime | 0.6554 ± 0.2789 | 0.8476 ± 0.1529 | 30 |
| random | 0.5998 ± 0.3109 | 0.5967 ± 0.3214 | 30 |

Random is a random pixel ordering (seed 42, one draw per image): the chance-level reference. n = 30 test images only (seeded subset of 103), so variance is high; do not over-read small differences.

## ONNX parity

max abs logit diff {'random': 1.0967254638671875e-05, 'real': 9.179115295410156e-06} (tolerance 0.0001): PASS

## Comparison context

All numbers above are measured on the deduplicated mirror (metalmerge/solar-panel-inspection, 789 images, 724 after
exact-duplicate removal) with leak-free grouped splits. They are not comparable one-to-one with figures published on the
original Kaggle set: our original slides 91.46 % accuracy and HybridSolarNet (arXiv 2601.02928) 92.37 %. Those are
reported by their authors, were not reproduced here, and can include near-duplicate leakage across splits.
