# AxalonSystems — Claude Code Project Context

## Repository Structure

```
AxalonSystems/
├── website/                         ← Company website
│   ├── nextjs/                      ← Next.js 14 site — single R3F canvas, scroll-driven 3D
│   │   ├── scrollStore.ts           ← Module singleton: scrollStore.{progress,raw}, zero re-renders
│   │   ├── app/
│   │   │   ├── layout.tsx           ← Minimal root shell (html/body only, no canvas)
│   │   │   ├── globals.css          ← Design tokens, fonts, responsive breakpoints
│   │   │   ├── (site)/              ← Route group for marketing site
│   │   │   │   ├── layout.tsx       ← (site) layout
│   │   │   │   └── page.tsx         ← 700vh scroll container; Hero→Split→CTA zones; mobile-responsive
│   │   │   └── platform/            ← /platform route — standalone platform demo UI
│   │   │       ├── layout.tsx
│   │   │       └── page.tsx         ← Full platform UI: file upload, batch job queue, fault reports
│   │   ├── components/
│   │   │   ├── Scene/               ← R3F components (all inside Canvas)
│   │   │   │   ├── MainScene.tsx    ← Root Canvas: lighting, Stars, SolarField, Drone, CameraRig, Bloom
│   │   │   │   ├── SceneController.tsx ← Inside Canvas; maps scroll→per-scene progress, no re-renders
│   │   │   │   ├── SolarField.tsx   ← 396 instanced panels + terrain + grid (1 draw call)
│   │   │   │   ├── Drone.tsx        ← Primitive drone: body+arms+rotors+gimbal, teal PointLight, sine hover
│   │   │   │   ├── CameraRig.tsx    ← CatmullRomCurve3 path (6 waypoints), scroll→camera, FOV breathing
│   │   │   │   ├── ThermalScan.tsx  ← Scene 2: scan line + scanning drone, scroll-driven
│   │   │   │   ├── DetectionBoxes.tsx ← Scene 3: instanced fault boxes + Html fault labels
│   │   │   │   ├── DroneFleet.tsx   ← Scene 4: 3-drone formation sweep across field
│   │   │   │   ├── HologramPanel.tsx ← Scene 5: rotating chip ring + canvas-texture metrics
│   │   │   │   └── CTAEffect.tsx    ← Scene 6: particle burst + animated rings + spotlight
│   │   │   ├── UI/                  ← HTML overlays (rendered outside Canvas via DOM)
│   │   │   │   ├── LeftPanel.tsx    ← Scroll-driven left panel: 4 content sections × 100vh
│   │   │   │   ├── HeroOverlay.tsx  ← Scene 1 HTML: headline, stats, telemetry badge (legacy)
│   │   │   │   ├── ThermalOverlay.tsx ← Scene 2 HTML: live fault counter, scan bar, class list
│   │   │   │   ├── DetectionOverlay.tsx ← Scene 3 HTML: mAP stats, sensor mode badges
│   │   │   │   ├── FleetOverlay.tsx ← Scene 4 HTML: 3-drone status cards with live telemetry
│   │   │   │   ├── ReportOverlay.tsx ← Scene 5 HTML: fault severity summary, export buttons
│   │   │   │   ├── CTAOverlay.tsx   ← Scene 6 HTML: stats + contact form card
│   │   │   │   └── Cursor.tsx       ← Custom teal crosshair cursor
│   │   │   ├── Platform/            ← Platform route components
│   │   │   │   ├── PlatformScene.tsx ← R3F scene for /platform page
│   │   │   │   ├── PlatformHUD.tsx  ← HUD overlay for platform scene
│   │   │   │   └── DynamicPlatformScene.tsx ← ssr:false wrapper
│   │   │   ├── Layout/
│   │   │   │   └── SplitLayout.tsx  ← Split layout primitive
│   │   │   ├── Navbar.tsx           ← Glass navbar, scroll-aware
│   │   │   ├── DynamicMainScene.tsx ← ssr:false wrapper for MainScene
│   │   │   └── DynamicCursor.tsx    ← ssr:false wrapper for Cursor
│   ├── frontend/                    ← OLD: CRA + Tailwind + shadcn/ui (deprecated)
│   ├── backend/                     ← Python/Flask API (contact form, etc.)
│   ├── design_guidelines.json       ← Brand colours, typography
│   └── render.yaml                  ← Render.com deployment config
│
├── ml/                              ← YOLO11x Solar Anomaly Detection model
│   ├── checkpoints/best.pt          ← PRIMARY MODEL WEIGHTS (YOLO11x, 109 MB)
│   ├── src/utils.py                 ← CANONICAL classes, severity map, drawing utils
│   ├── src/dataset.py               ← Dataset utilities, class remapping
│   ├── src/augmentation.py          ← Thermal augmentation pipeline
│   ├── configs/thermal.yaml         ← Training configuration
│   ├── thermal_dataset.yaml         ← Class names YAML (11 classes)
│   ├── notebooks/                   ← Training & inference notebooks
│   ├── output/                      ← Inference results (results.csv, report JSON)
│   └── runs/                        ← Training run metadata
│
├── platform/                        ← Axalon Analysis Platform (in development)
│   ├── api/app.py                   ← FastAPI REST endpoints
│   ├── core/                        ← detector.py, fusion.py, geo.py
│   ├── park/                        ← Panel localization (OCR + auto-grid)
│   ├── pipeline/                    ← Ingest → detect → report orchestration
│   ├── reporting/                   ← PDF, Excel, GeoJSON outputs
│   ├── db/                          ← SQLAlchemy models + SQLite
│   └── config/settings.yaml         ← Platform configuration
│
├── docs/                            ← Specs and reference documents
│   ├── AXALON_PLATFORM_SPEC.md      ← FULL platform design spec (READ THIS FIRST)
│   └── 2026_Global_Solar_Report_Raptor_Maps.pdf
│
├── tests/                           ← Test suite
├── main.py                          ← CLI entrypoint
├── requirements_platform.txt        ← Platform Python dependencies
└── ml/requirements.txt              ← ML Python dependencies
```

---

## Website Architecture — Scroll Layout

The marketing site (`app/(site)/page.tsx`) uses a **700vh scroll container** with three layout zones:

| Zone | Scroll range | Layout | What's shown |
|------|-------------|--------|-------------|
| Hero | 0–100vh | Full-width canvas | HeroContent overlay centered on canvas |
| Split | 100–500vh | 40% left panel / 60% canvas | LeftPanel scrolls through 4 content sections |
| CTA | 500–700vh | Full-width canvas | CTAContent overlay (headline + contact form) |

**Mobile** (`≤900px`): single-column, no split, all content flows in DOM order.

### Scroll wiring

- `scrollStore.progress` (0→1) and `scrollStore.raw` (px) are set by `window.scroll` in `page.tsx`
- R3F reads `scrollStore` inside `useFrame` (zero re-renders)
- `SceneController` inside the Canvas maps `progress` to per-scene `[0,1]` values for each of the 6 scenes
- `LeftPanel` is translated with `translateY(-${clamped}px)` driven by scroll position (no RAF/state)

### Progress bar

Far-left 2px bar, teal→purple gradient fill, moving dot with section number label.

### Split-line flash

On first entry into the Split zone from Hero, a vertical line snaps to 50%, slides to 40%, then fades out.

---

## 6-Scene Breakdown

| # | Scroll | 3D component | UI overlay |
|---|--------|-------------|------------|
| 1 | 0/6–1/6 | SolarField + Drone flyover | HeroContent (in page.tsx) |
| 2 | 1/6–2/6 | ThermalScan (scan line + drone) | ThermalOverlay |
| 3 | 2/6–3/6 | DetectionBoxes (fault boxes + labels) | DetectionOverlay |
| 4 | 3/6–4/6 | DroneFleet (3-drone formation sweep) | FleetOverlay |
| 5 | 4/6–5/6 | HologramPanel (chip ring + metrics) | ReportOverlay |
| 6 | 5/6–6/6 | CTAEffect (particles + rings) | CTAContent (in page.tsx) |

All scenes share the same fixed Canvas. `SceneController` fades components in/out; `CameraRig` moves the camera along a `CatmullRomCurve3` path.

---

## Critical Rules — Read Before Making Changes

### 1. Never Redefine These — Import from `ml/src/utils.py`

```python
from ml.src.utils import (
    CANONICAL_CLASSES,       # list of 11 class names, indices matter
    CLASS2ID,                # {"cell": 0, "cell-multi": 1, ...}
    ID2CLASS,                # {0: "cell", 1: "cell-multi", ...}
    SEVERITY_MAP,            # class → severity level
    SEVERITY_COLOR_BGR,      # severity → BGR color tuple
    draw_detections_severity,
    read_yolo_label,
    write_yolo_label,
    yolo_to_pixel,
    load_bgr,
    get_logger,
)
```

> In older code (AxalonPIPE era) this was `solar_thermal_detection.src.utils` — the canonical path is now `ml.src.utils`.

### 2. Primary Model

- Path: `ml/checkpoints/best.pt` (109 MB, sha256 prefix `fabb41c88f9d`)
- Framework: **Ultralytics YOLO11x** (`yolo11x.yaml`, 11 classes, trained with Ultralytics 8.4.84, checkpoint dated 2026-07-02) — the bake-off winner; the previous `best.pt` was YOLOv8s (see `docs/MODEL_COMPARISON_YOLOV8_VS_YOLO11X.md`). Verified from the checkpoint metadata, not assumed.
- Don't trust docs for which model is live: `GET /health` reads `model` / `model_info` (architecture, size, sha256 prefix) from the weights file actually on disk (`platform/core/model_info.py`).
- Input size: **640×640** (resize handled by Ultralytics automatically)
- Confidence threshold: **0.25**
- Trained on thermal IR images — do NOT run on RGB directly

### 3. Class Order Is Fixed (IDs 0–10)

| ID | Class | Severity |
|----|-------|----------|
| 0 | cell | MEDIUM |
| 1 | cell-multi | MEDIUM |
| 2 | module | MEDIUM |
| 3 | string | CRITICAL |
| 4 | bypass-diode | CRITICAL |
| 5 | offline-module | HIGH |
| 6 | vegetation-shading | LOW |
| 7 | soiling | LOW |
| 8 | short-circuit | HIGH |
| 9 | hot-spot-low | HIGH |
| 10 | hot-spot-high | CRITICAL |

### 4. Detection Dict Format

```python
{
    "class": str,           # from CANONICAL_CLASSES
    "class_id": int,        # 0-10
    "confidence": float,
    "bbox": [x1, y1, x2, y2],    # pixel coords
    "bbox_norm": [cx, cy, w, h],  # YOLO normalized
    "severity": str,        # CRITICAL/HIGH/MEDIUM/LOW
    "color_bgr": tuple,     # BGR tuple
}
```

### 5. Module Structure

- **Website code** → `website/` only
- **ML/model code** → `ml/` only
- **Platform code** → `platform/` only
- **Do not cross-import** between website and platform
- Platform imports ML utils: `from ml.src.utils import ...`

### 6. Don't Touch Training Code

`ml/src/augmentation.py`, `ml/src/dataset.py`, and notebooks are stable.
Only modify if explicitly asked to retrain.

---

## Common Commands

```bash
# Run Next.js website (dev)
cd website/nextjs && npm run dev

# Start platform API
uvicorn platform.api.app:app --host 0.0.0.0 --port 8000

# Or start API + Next.js platform UI together
./run.sh all

# Quick model test
python -c "
from ultralytics import YOLO
model = YOLO('ml/checkpoints/best.pt')
results = model('ml/data/images/test/', conf=0.25)
print(f'Detected {sum(len(r.boxes) for r in results)} anomalies')
"

# Install ML deps
pip install -r ml/requirements.txt

# Install platform deps
pip install -r requirements_platform.txt
```

---

## Development Context

- **ML Framework:** PyTorch 2.1+ with Ultralytics YOLO11
- **Python:** 3.13 compatible
- **GPU:** CUDA supported (device=0), CPU fallback available
- **Dataset:** 20,000 thermal IR images (24×40px) — stored outside repo (large)
- **Training results:** 2,236 detections across 2,000 test images
  - 222 CRITICAL, 233 HIGH, 1,444 MEDIUM, 337 LOW

## Key Design Decisions

1. **Thermal-only detection:** the YOLO11x detector runs ONLY on thermal images.
2. **Two park modes:** "Numbered" parks use OCR; "Unnumbered" parks get synthetic R{row}-C{col} IDs.
3. **Severity from utils.py:** Single source of truth — never hardcode elsewhere.
4. **GPS-anchored localization:** Every anomaly carries GPS coordinates from EXIF or orthomosaic.
5. **Zero-rerender scroll:** `scrollStore` is a plain module object mutated by scroll events; R3F reads it in `useFrame`. No useState/useEffect in the hot path.
6. **Single Canvas:** All 6 scenes share one `<Canvas>`. `SceneController` drives visibility; `CameraRig` drives position. No canvas teardown/remount between scenes.
