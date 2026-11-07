# Data card: SolarDoctor RGB defect classifier

## Source and licence

Kaggle `pythonafroz/solar-panel-images` (Solar Panel Images Clean and Faulty). The licence is listed as **Unknown** on Kaggle, so the images are used for private training only: they are not in git, not redistributed and not on Hugging Face. Only file names and hashes (`manifest.csv`) are committed.

## Comparability with published figures

The data here is the Hugging Face mirror `metalmerge/solar-panel-inspection` (pinned revision `1b62720`, 789 images, 724 after deduplication). All model metrics in `reports/BAKEOFF.md` are measured on this deduplicated, group-split data and are NOT directly comparable to figures published on the original Kaggle set (the team's original 91.46 %, HybridSolarNet 92.37 %), which were not reproduced here and may include near-duplicate leakage.

## Cleaning

Near-duplicate rule: two images are linked when pHash Hamming <= 6 or dHash Hamming <= 6 (hash size 8), taking the minimum distance over the other image's horizontal flip, vertical flip and 90/180/270 degree rotations as well as the original, or when their DINOv2-small embeddings have cosine similarity >= 0.95. Groups are the transitive closure of the links. Split seed 42.

Images per class before and after removing corrupt files and exact duplicates:

| stage | clean | dusty | bird_drop | snow_covered | electrical_damage | physical_damage | total |
|---|---|---|---|---|---|---|---|
| raw (decodable) | 177 | 143 | 134 | 146 | 103 | 86 | 789 |
| after exact dedupe | 172 | 136 | 123 | 127 | 91 | 75 | 724 |

Removed files by reason: exact_duplicate: 65

Near-duplicate groups (more than one image):

| measure | clean | dusty | bird_drop | snow_covered | electrical_damage | physical_damage | total |
|---|---|---|---|---|---|---|---|
| groups | 15 | 7 | 18 | 16 | 14 | 14 | 84 |
| images in such groups | 32 | 11 | 40 | 35 | 32 | 33 | 183 |

## Splits (grouped by near-duplicate group, stratified by label)

| split | clean | dusty | bird_drop | snow_covered | electrical_damage | physical_damage | total |
|---|---|---|---|---|---|---|---|
| test | 24 | 20 | 17 | 17 | 13 | 12 | 103 |
| train | 124 | 97 | 89 | 92 | 65 | 50 | 517 |
| val | 24 | 19 | 17 | 18 | 13 | 13 | 104 |

Cross-validation folds (-1 = test):

| fold | clean | dusty | bird_drop | snow_covered | electrical_damage | physical_damage | total |
|---|---|---|---|---|---|---|---|
| -1 | 24 | 20 | 17 | 17 | 13 | 12 | 103 |
| 0 | 30 | 23 | 21 | 22 | 15 | 13 | 124 |
| 1 | 30 | 23 | 22 | 22 | 15 | 12 | 124 |
| 2 | 30 | 23 | 21 | 22 | 16 | 12 | 124 |
| 3 | 29 | 23 | 20 | 22 | 16 | 14 | 124 |
| 4 | 29 | 24 | 22 | 22 | 16 | 12 | 125 |

## Examples of removed duplicates (file names only)

- exact: `Faulty_solar_panel_Train/Bird-drop/Bird (195).jpg` duplicates `Faulty_solar_panel_Train/Bird-drop/Bird (132).jpg` (distance 0)
- exact: `Faulty_solar_panel_Validation/Bird-drop/Bird (142).jpg` duplicates `Faulty_solar_panel_Train/Bird-drop/Bird (141).jpg` (distance 0)
- exact: `Faulty_solar_panel_Train/Bird-drop/Bird (147).jpg` duplicates `Faulty_solar_panel_Train/Bird-drop/Bird (144).jpg` (distance 0)
- exact: `Faulty_solar_panel_Train/Bird-drop/Bird (182).jpg` duplicates `Faulty_solar_panel_Train/Bird-drop/Bird (144).jpg` (distance 0)
- exact: `Faulty_solar_panel_Train/Bird-drop/Bird (6).jpg` duplicates `Faulty_solar_panel_Train/Bird-drop/Bird (144).jpg` (distance 0)
- exact: `Faulty_solar_panel_Train/Bird-drop/Bird (60).jpg` duplicates `Faulty_solar_panel_Train/Bird-drop/Bird (166).jpg` (distance 0)
- exact: `Faulty_solar_panel_Train/Bird-drop/Bird (194).jpg` duplicates `Faulty_solar_panel_Train/Bird-drop/Bird (190).jpg` (distance 0)
- exact: `Faulty_solar_panel_Train/Bird-drop/Bird (41).jpg` duplicates `Faulty_solar_panel_Train/Bird-drop/Bird (37).jpg` (distance 0)
- exact: `Faulty_solar_panel_Validation/Bird-drop/Bird (174).jpg` duplicates `Faulty_solar_panel_Train/Bird-drop/Bird (38).jpg` (distance 0)
- exact: `Faulty_solar_panel_Train/Bird-drop/Bird (70).jpg` duplicates `Faulty_solar_panel_Train/Bird-drop/Bird (5).jpg` (distance 0)
- near: `Faulty_solar_panel_Train/Bird-drop/Bird (127).jpg` ~ `Faulty_solar_panel_Train/Bird-drop/Bird (191).jpg` (pHash 0, dHash 0)
- near: `Faulty_solar_panel_Train/Bird-drop/Bird (146).jpg` ~ `Faulty_solar_panel_Train/Bird-drop/Bird (36).jpg` (pHash 0, dHash 0)
- near: `Faulty_solar_panel_Train/Bird-drop/Bird (192).jpg` ~ `Faulty_solar_panel_Train/Bird-drop/Bird (81).jpg` (pHash 0, dHash 0)
- near: `Faulty_solar_panel_Train/Bird-drop/Bird (192).jpg` ~ `Faulty_solar_panel_Validation/Bird-drop/Bird (87).jpg` (pHash 0, dHash 0)
- near: `Faulty_solar_panel_Train/Bird-drop/Bird (39).jpg` ~ `Faulty_solar_panel_Validation/Bird-drop/Bird (178).jpg` (pHash 0, dHash 0)
- near: `Faulty_solar_panel_Train/Bird-drop/Bird (81).jpg` ~ `Faulty_solar_panel_Validation/Bird-drop/Bird (87).jpg` (pHash 0, dHash 0)
- near: `Faulty_solar_panel_Train/Clean/Clean (10).JPG` ~ `Faulty_solar_panel_Train/Clean/Clean (141).JPG` (pHash 0, dHash 0)
- near: `Faulty_solar_panel_Train/Clean/Clean (171).jpg` ~ `Faulty_solar_panel_Train/Clean/Clean (31).jpg` (pHash 0, dHash 0)
- near: `Faulty_solar_panel_Train/Electrical-damage/Electrical (42).jpg` ~ `Faulty_solar_panel_Train/Electrical-damage/Electrical (9).jpg` (pHash 0, dHash 0)
- near: `Faulty_solar_panel_Train/Physical-Damage/Physical (10).jpg` ~ `Faulty_solar_panel_Train/Physical-Damage/Physical (34).jpg` (pHash 0, dHash 0)

Links found: 88 by hash, 128 by embedding (46 by embedding only). Embedding-only pairs with the highest cosine (audit these to judge the threshold):
- `Faulty_solar_panel_Train/Snow-Covered/Snow (81).JPG` ~ `Faulty_solar_panel_Validation/Snow-Covered/Snow (87).JPG` (cosine 0.992)
- `Faulty_solar_panel_Train/Bird-drop/Bird (136).JPG` ~ `Faulty_solar_panel_Train/Bird-drop/Bird (63).jpg` (cosine 0.991)
- `Faulty_solar_panel_Train/Bird-drop/Bird (191).jpg` ~ `Faulty_solar_panel_Validation/Bird-drop/Bird (197).jpg` (cosine 0.989)
- `Faulty_solar_panel_Train/Bird-drop/Bird (132).jpg` ~ `Faulty_solar_panel_Train/Bird-drop/Bird (167).JPG` (cosine 0.988)
- `Faulty_solar_panel_Train/Bird-drop/Bird (132).jpg` ~ `Faulty_solar_panel_Train/Bird-drop/Bird (137).JPG` (cosine 0.986)
- `Faulty_solar_panel_Train/Electrical-damage/Electrical (4).png` ~ `Faulty_solar_panel_Train/Electrical-damage/Electrical (86).JPG` (cosine 0.985)
- `Faulty_solar_panel_Train/Physical-Damage/Physical (23).jpg` ~ `Faulty_solar_panel_Train/Physical-Damage/Physical (49).jpg` (cosine 0.984)
- `Faulty_solar_panel_Train/Physical-Damage/Physical (25).jpg` ~ `Faulty_solar_panel_Train/Physical-Damage/Physical (49).jpg` (cosine 0.984)
- `Faulty_solar_panel_Validation/Bird-drop/image (14).jpeg` ~ `solar-Panel-Dataset_Test/Bird-drop/image (14).jpeg` (cosine 0.981)
- `Faulty_solar_panel_Train/Bird-drop/Bird (126).jpg` ~ `Faulty_solar_panel_Train/Bird-drop/Bird (129).jpg` (cosine 0.981)

## Possible label noise (near-duplicate groups with different labels)

- group 40: `Faulty_solar_panel_Train/Bird-drop/Bird (3).jpeg` (bird_drop), `Faulty_solar_panel_Train/Physical-Damage/Physical (44).jpg` (physical_damage)
- group 110: `Faulty_solar_panel_Train/Clean/Clean (157).jpg` (clean), `Faulty_solar_panel_Train/Clean/Clean (166).jpg` (clean), `Faulty_solar_panel_Train/Clean/Clean (185).jpg` (clean), `Faulty_solar_panel_Train/Clean/Clean (3).jpg` (clean), `Faulty_solar_panel_Train/Physical-Damage/Physical (66).jpg` (physical_damage)
- group 113: `Faulty_solar_panel_Train/Clean/Clean (16).JPG` (clean), `Faulty_solar_panel_Train/Dusty/Dust (182).jpg` (dusty)
- group 154: `Faulty_solar_panel_Train/Clean/Clean (64).jpg` (clean), `Faulty_solar_panel_Train/Dusty/Dust (31).jpg` (dusty)
- group 467: `Faulty_solar_panel_Validation/Clean/Clean (84).jpg` (clean), `Faulty_solar_panel_Validation/Dusty/Dust (154).jpg` (dusty)
- group 525: `Faulty_solar_panel_Validation/Physical-Damage/Physical (57).jpg` (physical_damage), `solar-Panel-Dataset_Test/Snow-Covered/images (8).jpeg` (snow_covered)

## Leakage check

Passed: no group spans splits or folds. Minimum test vs train/val Hamming distance: pHash 12, dHash 8 (must exceed 6/6).

## Out-of-distribution evaluation images (COCO)

The OOD guard is evaluated on 100 non-panel photos from COCO val2017 (ids and sha256 in `ml/rgb/data/ood_manifest.csv`, fetched by `ml/rgb/fetch_ood.py`). Each image keeps its own Flickr licence: Attribution License: 12, Attribution-NoDerivs License: 14, Attribution-NonCommercial License: 16, Attribution-NonCommercial-NoDerivs License: 22, Attribution-NonCommercial-ShareAlike License: 28, Attribution-ShareAlike License: 8. Several are NonCommercial and/or NoDerivs, so these images are used for evaluation only: they are never redistributed, never committed to git and never used for training. The images are split 50/50 (seed 42) into OOD-dev (method and threshold selection) and OOD-test (reporting).
