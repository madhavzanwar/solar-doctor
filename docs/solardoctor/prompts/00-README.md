# SolarDoctor build prompts — how to use them

Three prompts build SolarDoctor end to end. Run them **in order**, each in a **fresh Claude Code session** attached
to https://github.com/madhavzanwar/solar-doctor with push access. Each prompt is self-contained (it restates the
context it needs) and ends by committing and pushing to `main`, so the next prompt starts from the repo state.

| # | File | Goal | Rough effort |
|---|---|---|---|
| 1 | [`01-foundation.md`](01-foundation.md) | Import AxalonSystems as the base, restructure the monorepo, clone the SolarPulseAI UI exactly (with the upgraded fonts), port SolarPulseAI's physics backend, unify auth/DB/API, set up subagent definitions and CI. | Longest |
| 2 | [`02-intelligence.md`](02-intelligence.md) | Build the four pillars: physics deficit engine, best-in-class RGB defect classifier (Hugging Face), LIME + Grad-CAM explainability, telemetry–image fusion, ₹ ROI decisions, work orders, and every new screen. | Longest |
| 3 | [`03-hardening-launch.md`](03-hardening-launch.md) | Validate everything, independent review, bug bash, visual QA against the design references, security, docs, deploy (HF Space + Vercel), demo script, release. | Medium |

## Read before you start

- **Design source of truth:** [`../design/DESIGN.md`](../design/DESIGN.md) + screenshots in
  [`../design/reference/`](../design/reference/).
- **Research behind every decision:** [`../research/landscape-report.md`](../research/landscape-report.md)
  (also as PDF).

## Secrets / accounts the sessions will ask for

| Secret | Needed in | Why |
|---|---|---|
| GitHub push access to `madhavzanwar/solar-doctor` | 1, 2, 3 | Commit and push |
| `HF_TOKEN` (write scope) | 1, 2, 3 | Host model weights + Hugging Face Space demo/API |
| `KAGGLE_USERNAME`, `KAGGLE_KEY` | 2 | Download the 6-class panel image dataset (or upload the zip manually) |
| Vercel account (optional) | 3 | Host the frontend |
| `NEXT_PUBLIC_MAPBOX_TOKEN` (optional) | 2 | Satellite tiles on the map (free tiles work without it) |

## Source repositories referenced (all verified on 3–4 Nov 2026)

| Repo | Licence | Role in SolarDoctor |
|---|---|---|
| https://github.com/Parakh20/AxalonSystems | MIT (YOLO weights trained with AGPL Ultralytics) | **Base repo**: FastAPI platform, DB + Alembic, fault workflow, work orders, reports, auth, map, thermal YOLO, deploy |
| https://github.com/anugrahpatil-creator/SolarPulseAI | MIT | **UI cloned exactly**; physics/forecast backend ported (pvlib features, LightGBM, soiling, clipping, anomaly, diagnosis taxonomy) |
| https://github.com/VisionExpo/solar-panel-fault-detection | Apache-2.0 | Same 6 classes; LIME/SHAP explainer + inference API structure (code reusable with NOTICE) |
| https://github.com/dunglt69/solar-anomaly-detection | Apache-2.0 | Incident/ticket workflow, RBAC, live WebSocket patterns (code reusable with NOTICE) |
| https://github.com/rohanmurala/solarsight-ai | MIT (LICENSE file) | Grad-CAM + "manual review when uncertain" pattern (EL images) |
| https://github.com/rithvik123/solar-panel-defect-detection | **No licence** | Study only: inspection UX, priority queue, maintenance guidance, review reasons |
| https://github.com/VishnuBhaiya/solarvision-inspection | **No licence** | Study only: work-order lifecycle, schedule, reports pages |
| https://github.com/mcomuniello/Apollo9 | **No licence** | Study only: LIME (SLIC) + multi-XAI tabs |
| https://github.com/jkumarr10/veris-hackathon | **No licence** | Study only: clean / wait / alert decision logic |
| https://github.com/Princeg1204/solar-panel-defect-classifier | **No licence** | Study only: accuracy ladder + out-of-distribution guard |
| https://github.com/pvlib/pvlib-python | BSD-3 | Solar position, clear-sky, PVWatts, NASA POWER fetcher, soiling (Kimber) |
| https://github.com/NatLabRockies/rdtools (formerly NREL/rdtools) | MIT | Soiling ratio (SRR/CODS), degradation, normalisation |
| https://github.com/pvlib/pvanalytics | MIT | Data QA, clear-sky period detection, clipping, performance ratio |
| https://github.com/NatLabRockies/solar-data-tools | BSD-2 | Power-only soiling/loss analysis fallback |
| https://github.com/NatLabRockies/pvdaq_access | BSD-3 | Real public PV telemetry (OEDI PVDAQ S3) |
| https://github.com/marcotcr/lime | BSD-2 | LIME image explanations |
| https://github.com/jacobgil/pytorch-grad-cam | MIT | Grad-CAM / Grad-CAM++ / EigenCAM |
| https://github.com/huggingface/pytorch-image-models (timm) | Apache-2.0 | ConvNeXt / EfficientNet backbones from the HF Hub |
| https://github.com/hackingmaterials/pv-vision | BSD-3 | Optional: EL crack segmentation (future module) |
| https://github.com/RaptorMaps/InfraredSolarModules | MIT | Optional: thermal anomaly dataset |

"No licence" means all rights reserved: **read for ideas, never copy code, text or assets.**
