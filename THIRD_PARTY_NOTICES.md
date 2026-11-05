# Third-party notices

SolarDoctor is MIT-licensed (see `LICENSE`). It incorporates the following. Repositories **without** a licence
are study-only references: no code, text, images or CSS from them is used.

## Code incorporated

| Source | Licence | What we use |
|---|---|---|
| [Parakh20/AxalonSystems](https://github.com/Parakh20/AxalonSystems) | MIT (copyright notice retained in `LICENSE`, as MIT requires) | Starting codebase (FastAPI platform, DB, reporting, park localisation, drone, legacy Next.js site). Imported as a single commit. |
| [anugrahpatil-creator/SolarPulseAI](https://github.com/anugrahpatil-creator/SolarPulseAI) | MIT, © anugrahpatil-creator | `frontend/` (UI clone) and, in Phase E, the pvlib/ML modules ported into `backend/solardoctor/physics/` and `ml/forecast/`. |
| [VisionExpo/solar-panel-fault-detection](https://github.com/VisionExpo/solar-panel-fault-detection) | Apache-2.0 | Reference for 6-class inference + explainer API (add NOTICE entries per file when code is reused). |
| [dunglt69/solar-anomaly-detection](https://github.com/dunglt69/solar-anomaly-detection) | Apache-2.0 | Reference for incident lifecycle / RBAC / WebSocket patterns (add NOTICE entries per file when code is reused). |

### SolarPulseAI backend modules (Phase E, MIT, (c) 2026 anugrahpatil-creator)

Each ported file carries an attribution header. Mapping (SolarPulseAI `backend/` -> SolarDoctor):

| Source | Destination | Changes |
|---|---|---|
| `ml/{config,features,models,postprocessing,serving,training}` | `ml/forecast/` (+ new `ml/forecast/artifacts/README.md`, not ported) | import paths only (+ artifact dir env override) |
| `app/services/{forecast,anomaly,diagnosis,weather,scada,plant,clipping,soiling}_service.py`, `app/workers/*`, `app/api/websockets/scada_ws.py` | `backend/solardoctor/physics/` | async SQLAlchemy/asyncpg -> sync SQLAlchemy 2.0 session; new table names |
| `app/schemas/*`, `app/api/v1/routes/*` | `backend/solardoctor/physics/schemas/` (package), `backend/solardoctor/api/routers/{plants,forecast,diagnosis,weather,scada,physics_alerts}.py` | sync routes, Axalon session pattern |

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

## Frontend (Phase D)

- **SolarPulseAI frontend** (MIT, Copyright (c) 2026 anugrahpatil-creator): `frontend/` is derived file-by-file from
  https://github.com/anugrahpatil-creator/SolarPulseAI (`frontend/` at the commit referenced in DESIGN.md).
  `src/app/globals.css` and `src/app/dashboard/dashboard.css` are byte-identical to upstream; the dashboard, plant,
  alert and performance (formerly Forecasts) pages, the SVG chart components and the diagnosis modal are copied and
  modified (rebrand, nav, API client, source badges).
- **Fonts** (SIL OFL 1.1, fetched and self-hosted at build time by `next/font/google`): Bricolage Grotesque, Geist,
  Geist Mono, Instrument Serif; Syne and Source Sans 3 for `NEXT_PUBLIC_FONT_MODE=clone`.
- **Photography**: Unsplash License, per-photo credits in `docs/IMAGE_CREDITS.md`.
- **Dev tooling** (MIT/Apache-2.0): openapi-typescript, Vitest, jsdom, Playwright (Apache-2.0), pixelmatch (ISC), pngjs (MIT), sharp (Apache-2.0).

## Datasets (seed and PVDAQ import)

- **PVDAQ Public Datasets** (used by `scripts/import_pvdaq.py`; imported rows carry `source="PVDAQ"`): Deline, C.,
  Perry, K., Deceglie, M., Muller, M., Sekulic, W., Jordan, D. (NREL), "Photovoltaic Data Acquisition (PVDAQ) Public
  Datasets", Open Energy Data Initiative (OEDI), DOI [10.25984/1846021](https://doi.org/10.25984/1846021), licensed
  [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/). We use system 9068 (DOE 2023 Solar Data Prize prefix
  `pvdaq/2023-solar-data-prize/9068_OEDI/`). **Changes made:** subset of dates; 5-minute samples averaged to 15 minutes
  (>= 2 of 3 samples); timestamps converted from the logger's local wall clock (America/Denver, DST-aware) to UTC with
  ambiguous DST rows dropped; negative night readings clipped to 0; plant AC = sum of the inverter AC channels.
  Licence check (2026-11-05): the OEDI submission page data.openei.org/submissions/4568 lists the "2023 DOE Solar Data
  Prize" prefix as a resource of the same CC BY 4.0 submission and shows no additional terms; no separate Solar Data
  Prize licence page was reviewed, so absence of extra terms there is not independently confirmed. Display attribution
  wherever PVDAQ data is shown.
- **NASA POWER** (used by `scripts/seed.py` through `pvlib.iotools.get_nasa_power`): hourly irradiance, temperature and
  wind from the NASA Langley Research Center POWER Project, funded through the NASA Earth Science Applied Sciences
  Program (https://power.larc.nasa.gov). Open data; NASA asks users to acknowledge POWER. Seeded rows derived from it are
  simulations (`source="SIMULATED"`), not NASA measurements.
- **pvdaq_access** (BSD 3-Clause, NREL; `pip install pvdaq_access`): optional dependency; we reuse its anonymous-S3
  access pattern (boto3) but not its code.

## Dev-only tooling under MPL-2.0

- **axe-core** 4.14.0 and **@axe-core/playwright** 4.14.0 (MPL-2.0, Deque Systems; https://github.com/dequelabs/axe-core,
  https://github.com/dequelabs/axe-core-npm). Used only by `frontend/tests/a11y/run.mjs` as `devDependencies`. They are
  unmodified, installed from npm, not copied into this repository and not shipped in the production bundle.
