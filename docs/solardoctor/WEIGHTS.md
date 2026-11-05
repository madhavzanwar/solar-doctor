# Thermal model weights

## What the file is
| | |
|---|---|
| Path (git-ignored) | `ml/thermal/checkpoints/best.pt` |
| Size | 114,395,865 bytes |
| sha256 | `fabb41c88f9db29fa5e6803542a6804ee6c0b356aabd7e7c1c0ed6f2d727297d` |
| Architecture | Ultralytics YOLO11x detector, 11 classes (`cell, cell-multi, module, string, bypass-diode, offline-module, vegetation-shading, soiling, short-circuit, hot-spot-low, hot-spot-high`) |
| Trained with | Ultralytics 8.4.84, 150 epochs, 640 px, batch 16; checkpoint dated 2026-07-02 (read from the checkpoint metadata) |
| Input | Thermal IR only. Never run it on RGB photos. |

## Provenance
Trained by AxalonSystems (https://github.com/Parakh20/AxalonSystems). In that repo `best.pt` is a Git LFS
object whose pointer carries the sha256 above; our git proxy cannot read that LFS store. The identical
file is publicly served by upstream's Hugging Face Space `parakh20/axalon-api` at
`ml/checkpoints/best.pt` (the Space's LFS oid equals the sha256 above). We downloaded it from
`https://huggingface.co/spaces/parakh20/axalon-api/resolve/main/ml/checkpoints/best.pt` without a token and
verified the full sha256. The GitHub media URL and release assets were not needed and not tried after that
succeeded.

## Licence
AGPL-3.0 (Ultralytics YOLO11 and weights trained with it). Implications:
- Redistributing the weights requires AGPL-3.0 terms and source availability; the model card we publish says so.
- AGPL section 13: if a modified version of AGPL software is made available to users over a network, those users
  must be offered the corresponding source. Serving this model behind the SolarDoctor API/dashboard is network
  use. Keep the SolarDoctor source (including the code that loads and wraps the model) public under a
  compatible licence, or obtain a commercial Ultralytics licence. Have the owner confirm this with a licence
  adviser before any commercial deployment; this note is not legal advice.
- The weights are never committed to git here (`ml/thermal/checkpoints/*.pt` is ignored).

## Accuracy: only what is established
- Upstream claims mAP@0.5 = 0.792 on its own split. **Unverified by us**: we did not reproduce it (no labelled
  evaluation set was run).
- The checkpoint's own embedded `train_metrics` (read by us) are mAP@0.5 = 0.727, mAP@0.5:0.95 = 0.610,
  precision 0.677, recall 0.693. This does not match the 0.792 claim; treat 0.792 as unexplained until
  upstream's evaluation is reproduced.
- Smoke check only: inference on `tests/fixtures/sample_mission/thermal/img_00{1,2,3}.jpg` returns one
  `hot-spot-low` box covering the whole frame (conf 0.69-0.71). That says the model loads and runs; the fixture
  images are not labelled ground truth, so it says nothing about accuracy.

## Obtain
```bash
python scripts/fetch_weights.py          # tries SolarDoctor HF repo, then upstream's public Space; sha256-verified
```
Behaviour: skips if a verified file already exists; resumes interrupted downloads (`best.pt.part`); a wrong
hash never lands at the destination; `--force`, `--dest`, `--url` available. Then set `ENABLE_THERMAL=true`.

## Publish to the SolarDoctor HF repo (owner only; needs a write token)
Nothing has been uploaded by the build agents.
```bash
export HF_TOKEN=hf_xxx                       # your own write token; do not commit or paste it anywhere
python scripts/fetch_weights.py
python scripts/publish_weights_hf.py --dry-run
python scripts/publish_weights_hf.py         # creates madhavzanwar/solar-doctor-thermal-yolo11x, uploads model card + best.pt
```
The script refuses any file whose sha256 differs from the pinned value and uploads a model card stating the
licence, source, and that the 0.792 mAP is upstream's and unverified. After publishing, optionally make the
SolarDoctor repo the only source by passing `--url` or `SOLARDOCTOR_THERMAL_URL`.

Risk to note: the fallback Space belongs to a third party and can disappear or change; publishing our own copy
removes that dependency.
