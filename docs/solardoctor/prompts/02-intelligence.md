# PROMPT 2 / 3 — Intelligence: deficit engine, best RGB model on Hugging Face, explainability, fusion, ROI, work orders, new screens

> Paste everything below this line into a fresh Claude Code session with push access to
> https://github.com/madhavzanwar/solar-doctor. Prompt 1 must already be merged (tag `v0.1.0-foundation`).

---

You are the **lead engineer and coordinator** for **SolarDoctor** (team Photosphere, PCCoE Pune). Prompt 1 built
the foundation: AxalonSystems-based FastAPI backend (package `solardoctor`, or `axalon` if the rename was
reverted — check `docs/solardoctor/DECISIONS.md`), the pixel-exact SolarPulseAI frontend clone in `frontend/`,
ported SolarPulse physics, unified auth, seeded plants, CI, and subagents in `.claude/agents/`.
**Read first:** `CLAUDE.md`, `docs/solardoctor/BUILD_LOG.md`, `docs/solardoctor/design/DESIGN.md` (§8 defines
every screen you build now), `docs/solardoctor/research/landscape-report.md` (sections 5, 8, 9, 13).

Your job now: build the four pillars to production quality and wire them into one loop.
**Detect (physics) → Diagnose (vision) → Explain (XAI + telemetry cross-check) → Act (₹ ROI + work order + verify).**

Use the subagents `sd-physics`, `sd-ml`, `sd-backend`, `sd-frontend`, `sd-qa` (definitions in `.claude/agents/`).
Run independent workstreams in parallel in separate git worktrees/branches; `sd-qa` independently verifies each
before you merge. Log decisions in `docs/solardoctor/DECISIONS.md` and progress in `BUILD_LOG.md`.

## Reference repositories (open the README / relevant files before using)

- Physics: https://github.com/pvlib/pvlib-python (BSD-3), https://github.com/NatLabRockies/rdtools (MIT),
  https://github.com/pvlib/pvanalytics (MIT), https://github.com/NatLabRockies/solar-data-tools,
  https://github.com/NatLabRockies/pvdaq_access, NASA POWER API docs https://power.larc.nasa.gov/docs/services/api/
- Vision/XAI: https://github.com/huggingface/pytorch-image-models (timm, Apache-2.0),
  https://huggingface.co/facebook/dinov2-small, https://huggingface.co/openai/clip-vit-base-patch32,
  https://github.com/marcotcr/lime (BSD-2), https://github.com/jacobgil/pytorch-grad-cam (MIT),
  https://github.com/VisionExpo/solar-panel-fault-detection (Apache-2.0, same 6 classes, LIME/SHAP explainer),
  https://github.com/rohanmurala/solarsight-ai (MIT, Grad-CAM + "manual review when uncertain"),
  https://github.com/hackingmaterials/pv-vision (BSD-3, optional EL module),
  https://github.com/Parakh20/AxalonSystems (thermal YOLO11x, already in our repo under `ml/thermal/`).
- Workflow/UX ideas (no licence → study only, never copy): https://github.com/rithvik123/solar-panel-defect-detection,
  https://github.com/VishnuBhaiya/solarvision-inspection, https://github.com/mcomuniello/Apollo9,
  https://github.com/jkumarr10/veris-hackathon, https://github.com/Princeg1204/solar-panel-defect-classifier.
- Ticketing/RBAC/live (Apache-2.0, reusable with NOTICE): https://github.com/dunglt69/solar-anomaly-detection.
- Dataset: Kaggle "Solar Panel Images Clean and Faulty" https://www.kaggle.com/datasets/pythonafroz/solar-panel-images
  (6 classes, ≈875 raw images, licence listed as **Unknown** → train privately, never redistribute images, say so in
  the model card).

---

## Workstream 1 — Physics deficit engine (`sd-physics`) → `backend/solardoctor/physics/`

1. **Irradiance & weather providers** (pluggable, cached in `weather_cache`, provenance stored on every row):
   site sensor (if telemetry has POA/GHI) → NASA POWER hourly via `pvlib.iotools.get_nasa_power`
   (ALLSKY_SFC_SW_DWN, CLRSKY_SFC_SW_DWN, T2M, WS10M, PRECTOTCORR; ≤ 15 params/request) → Open-Meteo for the
   next 3 days (official `openmeteo-requests` client, MIT). Handle NASA POWER latency (recent days missing) gracefully.
2. **Expected power model:** solar position → POA transposition (Perez/Hay-Davies via `pvlib.irradiance.get_total_irradiance`)
   → cell temperature (`pvlib.temperature.sapm_cell` or Faiman) → `pvlib.pvsystem.pvwatts_dc` (γ from plant config)
   → `pvlib.inverter.pvwatts` with AC clipping. Also a **clear-sky potential** using `pvlib.clearsky.ineichen` with
   `lookup_linke_turbidity`. Keep the ported SolarPulse LightGBM hybrid as a third baseline option
   ("Hybrid ML"). Expose `baseline=clearsky|pvwatts|hybrid`.
3. **Data QA** with pvanalytics: gaps, stuck/flat values, `quality.outliers.hampel`, clipping
   (`features.clipping`), day/night, clear-sky periods (`features.clearsky.reno`), plus irradiance > 200 W/m²,
   zenith < 75°. Every deficit computation uses only QC-passed, clear-sky-flagged, non-clipped samples.
4. **Deficit detector:** performance index PI = actual / expected per string and per plant; rolling median over
   N clear hours; WARNING when PI < 0.95 for ≥ 3 clear hours, CRITICAL when PI < 0.90 (thresholds per plant in
   settings). Distinguish **plant-wide** deficits (soiling/haze/curtailment) from **string-level** deficits via
   **peer comparison** (string normalised yield vs plant median; z-score) — this localises the problem the drone
   should inspect. Suppress during curtailment flags and cloudy periods. Persist alerts in the existing `alerts`
   table with `expected_power_kw`, `actual_power_kw`, `deviation_percent`, `scope` (plant/inverter/string),
   `evidence` JSON (samples used, baseline, QC stats).
5. **Soiling analytics:** `rdtools.soiling.soiling_srr` on daily normalised energy when ≥ 60 days of data exist
   (report soiling ratio, soiling rate %/day, cleaning events); otherwise `pvlib.soiling.kimber` with NASA POWER
   rain as a model-based estimate (label it "modelled"). Solar Data Tools (`DataHandler.run_pipeline`,
   `run_loss_factor_analysis`) as a power-only fallback when no irradiance exists.
6. **Background jobs:** hourly ingest + deficit scan per plant; daily soiling + degradation
   (`rdtools.degradation.degradation_year_on_year` when ≥ 2 years). Use the existing job/worker system from
   Axalon; make jobs idempotent.
7. **Tests:** synthetic telemetry with known injected losses (5 %, 10 %, 20 % on one string; 7 % plant-wide
   soiling; a cloudy day) → detector must find exactly the injected events (precision/recall reported), no alerts on
   the cloudy day, correct string localisation. Golden tests vs the pvlib gallery example for PVDAQ system 9068.

## Workstream 2 — Best RGB defect classifier on Hugging Face (`sd-ml`) → `ml/rgb/` + `backend/solardoctor/vision/`

Our original model (team slides): autoencoder + fine-tuned VGG16, 100×100 grayscale input, 91.46 % accuracy.
Research benchmark on the same 6 classes (arXiv 2601.02928, HybridSolarNet): EfficientNet-B0 90.84 %,
HybridSolarNet 92.37 %, VGG19 87.79 %. Many public repos claim higher numbers because near-duplicate images leak
across splits. **Our goal is an honest, leak-free number and a model that generalises to real phone/drone photos.**

1. **Data pipeline (`ml/rgb/data/`):** download with the Kaggle API (`KAGGLE_USERNAME`/`KAGGLE_KEY`; if blocked,
   ask me to upload the zip). Normalise class names to `clean, dusty, bird_drop, snow_covered, electrical_damage,
   physical_damage`. Remove corrupt/non-image files. **Deduplicate** with perceptual hashing (`imagehash` pHash +
   dHash, Hamming ≤ 6) and group near-duplicates so a group never spans splits. Stratified group split: 70/15/15
   + 5-fold CV on train+val. Write `ml/rgb/DATA_CARD.md` (counts per class before/after dedupe, examples of removed
   duplicates, licence caveat).
2. **Augmentation** (albumentations): RandomResizedCrop(224, scale 0.6–1.0), flips, ±20° rotate, perspective,
   brightness/contrast ±0.2, *mild* hue/saturation (colour carries the dust/snow/bird signal — keep it subtle),
   Gaussian/motion blur, JPEG 40–95, random glare/sun-flare. Class-balanced sampling or weighted loss.
3. **Model bake-off** (same splits, same seeds, report mean ± std over 5 folds; macro-F1 is the selection metric,
   then latency and size):
   - **B0 — reproduce ours:** VGG16 + autoencoder, 100×100 gray (Keras, our original) and a 224×224 RGB variant.
   - **B1:** `timm` `efficientnet_b0.ra_in1k` fine-tune.
   - **B2:** `timm` `convnext_tiny.fb_in22k_ft_in1k` fine-tune (layer-wise LR decay, AdamW, cosine, label
     smoothing 0.1, EMA).
   - **B3:** **DINOv2** `facebook/dinov2-small` — (a) frozen features + logistic regression, (b) fine-tune last
     4 blocks. Strong with small datasets.
   - **B4 (optional):** `openai/clip-vit-base-patch32` linear probe.
   - Verify every Hugging Face model ID resolves with `huggingface_hub.model_info` before training; if one does not,
     pick the closest available checkpoint and log it.
   Train on GPU if available (CUDA/MPS); otherwise produce a ready-to-run Kaggle/Colab notebook
   `ml/rgb/notebooks/train_bakeoff.ipynb` and train the cheapest strong option (B3a, then B1) on CPU.
4. **Calibration & uncertainty:** temperature scaling on val; report ECE before/after. Expose top-3 probabilities.
5. **Out-of-distribution guard ("is this a solar panel photo?"):** implement and compare (i) CLIP zero-shot
   ("a photo of a solar panel" vs negatives: "a photo of a roof", "a person", "a document", "a car", "a tree")
   and (ii) Mahalanobis distance on DINOv2 embeddings of the training set, plus (iii) our autoencoder
   reconstruction error (keeps the team's original idea). Pick by AUROC on a held-out OOD set (collect ~100 non-panel
   images from a permissive source, e.g. COCO val subset). Low-confidence (< 0.6) or OOD → **"Needs field check"**.
6. **Explainability (`backend/solardoctor/vision/xai.py`):**
   - **Grad-CAM** via `pytorch-grad-cam` (use `reshape_transform` for ViT/DINOv2; last stage for ConvNeXt).
   - **LIME** via `lime.lime_image` with SLIC/quickshift segmentation, `num_samples` configurable (default 600 for
     interactive, 2000 for reports), top-k superpixels, cached per image hash.
   - **Faithfulness check:** deletion/insertion AUC for both methods on the test set; report which is more faithful
     for our model in the model card. (Our research found **no** solar project that measures explanation quality —
     this is a differentiator; do it properly.)
   - Return PNG overlays (viridis for Grad-CAM, sun-outlined superpixels for LIME — colours per DESIGN.md §2.2)
     plus raw masks as arrays for the frontend slider.
7. **Serving:** PyTorch CPU in the API (needed for Grad-CAM) + ONNX export (opset 17, verified with
   onnxruntime parity test ≤ 1e-4) for the HF Space and edge use. Load once at startup; `GET /api/v1/vision/model`
   reports name, version, metrics, sha256. Inference p95 < 400 ms on CPU for 224×224 (measure).
8. **Hugging Face:**
   - Model repo `madhavzanwar/solar-doctor-rgb` with weights (safetensors + ONNX), `config.json`, label map,
     preprocessing, and a **model card** (intended use, data caveats, leak-free metrics with std, per-class
     recall, confusion matrix image, calibration, OOD AUROC, XAI faithfulness, limitations: RGB cannot see
     hot-spots/diode faults → use thermal/IV).
   - Space `madhavzanwar/solar-doctor-demo` (Gradio, CPU basic) — upload a photo → class, confidence, LIME + Grad-CAM
     overlays, recommended action, "needs field check" state. Styled with the SolarDoctor palette/fonts.
   - Download weights in the backend via `hf_hub_download` at startup (cached), pinned by revision.
9. **Thermal (optional, flagged):** keep Axalon's YOLO11x thermal pipeline under `ENABLE_THERMAL`, mapped into the
   same diagnosis schema (hot-spot / bypass-diode / string-outage → `electrical_damage` family), with its AGPL note.
10. **Multi-panel drone frames (stretch):** if a frame contains many modules, localise panels first (try an
    Apache/MIT detector such as RT-DETR from `transformers` fine-tuned on a permissively licensed Roboflow Universe
    solar-panel dataset; avoid adding new AGPL dependencies), then classify each crop and map to panel IDs with
    Axalon's park/grid localisation.

## Workstream 3 — Fusion, ROI and work orders (`sd-backend` + `sd-physics`)

1. **Inspection entity:** `inspections` (id, plant_id, string_id?, alert_id?, image_uri, image_sha256,
   captured_at, gps, source=phone|drone|thermal, model_version, predicted_class, probs JSON, confidence, ood_score,
   needs_field_check, xai_uri_gradcam, xai_uri_lime, status). Store images via Axalon's object store abstraction
   (local disk dev, S3-compatible prod). Validate uploads: MIME sniffing, ≤ 15 MB, EXIF orientation fix, strip GPS
   from public URLs, HEIC → JPEG.
2. **Fusion engine (`backend/solardoctor/fusion/`)** — reconcile telemetry with the photo and produce a verdict +
   action + confidence + plain-language reason. Encode this decision table as data (YAML) with tests for every row:

   | Telemetry (clear-sky QC'd) | Photo class | Verdict | Action |
   |---|---|---|---|
   | Deficit ≥ threshold | dusty / bird_drop | Soiling confirmed | ROI check → CLEAN NOW or WAIT |
   | Deficit ≥ threshold | snow_covered | Snow loss | WAIT (melt forecast) or clear if safe |
   | Deficit ≥ threshold | clean | Not visible in RGB → electrical/inverter suspected | FIELD CHECK (IV curve / thermal), inverter error codes from diagnosis taxonomy |
   | Deficit ≥ threshold | electrical_damage / physical_damage | Hardware fault | REPLACE / warranty claim, safety warning |
   | No deficit | dusty / bird_drop | Cosmetic / early soiling | WAIT, re-check in N days |
   | No deficit | physical_damage | Latent damage | FIELD CHECK (safety) |
   | Cloudy / no QC data | any | Inconclusive | Re-check on next clear day |
   | Any | OOD or confidence < 0.6 | Unclear photo | NEEDS FIELD CHECK |

3. **ROI engine (`backend/solardoctor/roi/`)** — all inputs from plant settings (DESIGN.md §8.4):
   recoverable kWh/day = expected kWh/day × attributable deficit fraction; ₹/day = kWh × tariff (presets: utility PPA
   ₹2.6, C&I ₹6.5, residential ₹8 — editable, **label as user assumptions**); cleaning cost = modules × ₹/module +
   water L × ₹/L + labour; payback days = cost / ₹/day; rain-aware **WAIT** when Open-Meteo precipitation probability
   ≥ 60 % within 72 h; optimal cleaning interval heuristic T* = √(2·C / (r·V)) where r = soiling rate (fraction/day,
   from RdTools or model) and V = ₹/day of clean production — document it as a heuristic with its derivation in
   `docs/solardoctor/ROI_METHOD.md`; water saved vs a calendar schedule (default every 15 days). Unit-test with
   hand-computed examples.
4. **Work orders:** extend Axalon's `PanelFault` + `work_orders` router and `core/fault_workflow.py` (keep its
   status machine: open → assigned → in_progress → resolved / stale). Add: link to alert, inspection, ROI decision;
   SLA due date from priority (urgent 24 h, high 72 h, medium 7 d, low 30 d); assignee (technician role);
   checklist from the diagnosis taxonomy's technician steps; before/after photos (Axalon `FaultPhoto`); comments;
   **auto-create** a work order from a CRITICAL fused verdict (configurable); **Verify fix**: after resolution,
   compare PI over the 3 clear days before vs after; mark `verified` or reopen. Notify via Axalon's alert channels
   (webhook/SMTP) and an in-app bell (WebSocket, pattern from dunglt69/solar-anomaly-detection, Apache-2.0).
5. **Reports:** extend Axalon reporting (PDF via WeasyPrint templates, Excel, GeoJSON) with: plant health summary,
   deficit timeline, inspection evidence pages (photo + LIME + Grad-CAM + verdict), ROI table, open work orders.
   Styled with DESIGN.md tokens/fonts.
6. **API:** `/api/v1/inspections` (POST multipart, GET list/detail, POST `/{id}/explain?method=lime|gradcam`),
   `/api/v1/performance/{plant_id}` (series + deficit + clear-sky flags + soiling), `/api/v1/strings/{id}/peers`,
   `/api/v1/roi/{plant_id}` (+ settings), `/api/v1/work-orders` (CRUD, transitions, verify), `/api/v1/reports`,
   `/api/v1/notifications` (WS). Pydantic v2 schemas, pagination, RBAC checks, OpenAPI examples. Regenerate the
   frontend client.

## Workstream 4 — New screens (`sd-frontend`), exactly as DESIGN.md §8 specifies

Build in the cloned SolarPulse visual language (hairlines, 2 px radius, numbered nav, tracked labels, display
numbers, advisories). No new UI kit. Charts stay hand-written SVG (extend `ForecastActualChart` with the deficit
ribbon, clear-sky strip, rain ticks and cleaning flags).

1. **Performance** (§8.2) — evolve Forecasts: baseline selector, KPI strip (PR, deficit kWh, soiling ratio,
   recoverable ₹/month), main chart, string peer table with sparklines, soiling chart. Keep the existing
   probabilistic/online-learning tabs as secondary tabs.
2. **Inspections** (§8.1) — list, upload (drag-drop + mobile camera), result page with the **Evidence viewer**
   (Original · LIME · Grad-CAM · Side-by-side, opacity slider, press-and-hold original, LIME k selector),
   Diagnosis card (class chip, calibrated confidence, top-3, reversible badge, action advisory, needs-field-check
   state with reason), **Cross-check with performance** card (signature component), actions.
3. **Alerts** — add "Inspect" action (opens upload pre-linked to the alert/string) and show fused verdicts.
4. **Work orders** (§8.3) — list + board, drawer with stepper, checklist, photos, comments, Verify fix chart.
5. **ROI** (§8.4) — settings strip, decision table, summary advisory, water-saved counter. Currency `en-IN`.
6. **Map** (§8.5) — port Leaflet map/grid components from `legacy/axalon-nextjs/components/Platform/`
   (`AnomalyMap`, `ParkMapGrid`, `ParkPanelDetail`, `FaultWorkflowPanel` — MIT) and restyle to DESIGN.md.
7. **Reports** (§8.6) and **Settings** (tariffs, cleaning cost, thresholds, users/roles).
8. Overview: add KPIs "Energy at risk (₹/month)", "Open work orders", "Inspections needing review".
9. Every view: loading, empty (line illustration), error states; keyboard + screen-reader support; 390 px mobile.

## Workstream 5 — Continuous verification (`sd-qa`, independent)

- After each workstream: read the diff cold, run all suites, try to break it (bad uploads, huge images, non-panel
  photos, empty telemetry, timezone edges at midnight IST, DST-free tz, NaNs, plants with no strings, 0 tariff).
- ML audit: re-run evaluation from a clean checkout on the frozen test split; confirm no duplicate leakage
  (re-hash test vs train); confirm reported metrics match `ml/rgb/reports/*.json`.
- Physics audit: confirm deficit alerts on the synthetic suite and zero alerts on the cloudy day.
- UI audit: visual check of every new screen at 1440 and 390 against DESIGN.md (screenshots saved to
  `docs/solardoctor/qa/screens/`), axe-core accessibility scan with zero serious/critical issues.
- File findings in `docs/solardoctor/qa/FINDINGS.md`; you fix; `sd-qa` re-verifies. Merge only on sign-off.

## End-to-end acceptance scenario (must pass, automated as a Playwright test)

1. Seeded "PCCoE Rooftop" shows a CRITICAL string-level deficit on S-04 (−10 to −15 % on clear hours).
2. Operator clicks **Inspect** on the alert → uploads a dusty-panel test image → result shows **Dusty**,
   calibrated confidence, LIME + Grad-CAM overlays, telemetry cross-check "agrees".
3. Fusion verdict "Soiling confirmed"; ROI shows ₹/day recoverable and **CLEAN NOW** (or WAIT if rain forecast is
   mocked) with payback days.
4. Operator creates a work order → technician user sees it, completes checklist, uploads after-photo, resolves.
5. Simulated post-clean telemetry → **Verify fix** marks it verified with the PI recovery chart.
6. Report PDF contains all of the above. A non-panel photo yields **Needs field check**.

## Definition of done for Prompt 2

- [ ] All five workstreams merged with `sd-qa` sign-off; CI green.
- [ ] Model bake-off table (mean ± std, 5-fold + held-out test, leak-free) in `ml/rgb/reports/BAKEOFF.md`;
      winning model on HF Hub with a complete model card; Space demo live (or exact blocker logged).
- [ ] XAI faithfulness numbers reported; OOD guard AUROC reported.
- [ ] Deficit detector precision/recall on the synthetic suite reported; PVDAQ import works.
- [ ] Fusion table and ROI method documented and fully unit-tested.
- [ ] All new screens match DESIGN.md at desktop + mobile; e2e acceptance scenario passes.
- [ ] Docs updated (README features, ARCHITECTURE.md with data-flow diagram, API reference from OpenAPI).
- [ ] Everything committed (Conventional Commits) and **pushed to `origin main`**; tag `v0.2.0-intelligence`.

Finish with a report: metrics table, screenshots list, what is simulated vs real, open risks for Prompt 3.
