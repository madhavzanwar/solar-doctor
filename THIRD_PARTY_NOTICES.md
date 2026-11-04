# Third-party notices

SolarDoctor is MIT-licensed (see `LICENSE`). It incorporates the following. Repositories **without** a licence
are study-only references: no code, text, images or CSS from them is used.

## Code incorporated

| Source | Licence | What we use |
|---|---|---|
| [Parakh20/AxalonSystems](https://github.com/Parakh20/AxalonSystems) | MIT, © Parakh Sharma | Entire starting codebase (FastAPI platform, DB, reporting, park localisation, drone, legacy Next.js site). Imported with history. |
| [anugrahpatil-creator/SolarPulseAI](https://github.com/anugrahpatil-creator/SolarPulseAI) | MIT, © anugrahpatil-creator | `frontend/` (UI clone) and, in Phase E, the pvlib/ML modules ported into `backend/solardoctor/physics/` and `ml/forecast/`. |
| [VisionExpo/solar-panel-fault-detection](https://github.com/VisionExpo/solar-panel-fault-detection) | Apache-2.0 | Reference for 6-class inference + explainer API (add NOTICE entries per file when code is reused). |
| [dunglt69/solar-anomaly-detection](https://github.com/dunglt69/solar-anomaly-detection) | Apache-2.0 | Reference for incident lifecycle / RBAC / WebSocket patterns (add NOTICE entries per file when code is reused). |

## Model weights

| Asset | Licence | Note |
|---|---|---|
| Thermal YOLO11x `best.pt` (from AxalonSystems) | **AGPL-3.0** (Ultralytics-trained) | Not stored in this repo; served from Hugging Face `madhavzanwar/solar-doctor-thermal-yolo11x`. Network use of the weights has AGPL implications. mAP@0.5 0.792 is AxalonSystems' own figure on their split. |

## Study-only (no licence, nothing copied)

rithvik123/solar-panel-defect-detection, VishnuBhaiya/solarvision-inspection, mcomuniello/Apollo9.

## Runtime libraries (selection; full lists in `requirements_platform.txt`, `frontend/package.json`)

FastAPI (MIT), SQLAlchemy (MIT), Alembic (MIT), Pydantic (MIT), Ultralytics (AGPL-3.0), PyTorch (BSD-3),
OpenCV (Apache-2.0), pvlib (BSD-3), Next.js (MIT), React (MIT), Tailwind CSS (MIT).

## Fonts and images

Listed in `docs/IMAGE_CREDITS.md` and `frontend/` font packages (Bricolage Grotesque, Geist, Geist Mono,
Instrument Serif: SIL OFL 1.1).
