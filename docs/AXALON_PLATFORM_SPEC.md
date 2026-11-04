# Axalon Systems — Solar Anomaly Detection Platform
## Complete Software Specification

> **Version:** 1.0 | **Date:** 2026-04-11 | **Author:** Axalon Systems  
> **Status:** Design Specification — Ready for Implementation

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Existing Assets](#2-existing-assets)
3. [System Architecture](#3-system-architecture)
4. [Module Specifications](#4-module-specifications)
5. [Detection & AI Pipeline](#5-detection--ai-pipeline)
6. [Panel Localization Strategy](#6-panel-localization-strategy)
7. [Reporting & Outputs](#7-reporting--outputs)
8. [REST API Design](#8-rest-api-design)
9. [Dashboard / UI](#9-dashboard--ui)
10. [Configuration Reference](#10-configuration-reference)
11. [Database Schema](#11-database-schema)
12. [Installation & Dependencies](#12-installation--dependencies)
13. [Project Structure](#13-project-structure)
14. [Development Roadmap](#14-development-roadmap)
15. [Verification & Testing](#15-verification--testing)

---

## 1. Executive Summary

The **Axalon Solar Inspection Platform** is a complete end-to-end software system for drone-based solar farm anomaly detection. It processes paired **thermal infrared (IR) + RGB image** data captured by drones, runs AI-powered anomaly detection using a pre-trained YOLOv8s model, localizes faulty panels within the solar park, and generates structured inspection reports.

### Core Capabilities

| Capability | Description |
|---|---|
| **Dual-modality input** | Paired thermal + RGB image processing per flight position |
| **AI Detection** | YOLOv8s detecting 11 anomaly classes in thermal imagery |
| **Severity Triage** | Automatic CRITICAL / HIGH / MEDIUM / LOW classification |
| **Panel Localization** | Works with numbered parks (OCR) AND unnumbered parks (auto-grid) |
| **Geospatial** | GPS/EXIF extraction → real-world coordinates per anomaly |
| **Reports** | PDF, Excel, GeoJSON, annotated image outputs |
| **REST API** | FastAPI backend for integration into larger workflows |
| **Dashboard** | Streamlit web UI for inspection operators |

### Inspiration

The platform is modeled after industry tools like [Raptor Maps](https://raptormaps.com/) but purpose-built for Axalon Systems' drone fleet and custom-trained model.

---

## 2. Existing Assets

### 2.1 Trained Model

| Asset | Path | Details |
|---|---|---|
| **Best checkpoint** | `solar_thermal_detection/checkpoints/best.pt` | YOLOv8s, 22 MB, primary model |
| Last epoch | `solar_thermal_detection/runs/thermal/train/weights/last.pt` | 22 MB |
| Epoch checkpoints | `runs/thermal/train/weights/epoch{0,10,...,70}.pt` | For ablation / rollback |
| Nano base weights | `yolo26n.pt` (stock Ultralytics, COCO-pretrained) | 5.3 MB — auto-downloaded by ultralytics, not committed |

The best checkpoint was trained for **100 epochs** on a merged dataset of 20,000 thermal IR images (InfraredSolarModules) + PV archive data, with thermal-specific augmentation (no hue/saturation shifts).

### 2.2 Detection Classes (11 classes)

From `solar_thermal_detection/src/utils.py` — `CANONICAL_CLASSES`:

| ID | Class Name | Severity | Color | Description |
|---|---|---|---|---|
| 0 | `cell` | MEDIUM | Yellow | Single cell anomaly |
| 1 | `cell-multi` | MEDIUM | Yellow | Multiple cell anomaly |
| 2 | `module` | MEDIUM | Yellow | Full module thermal deviation |
| 3 | `string` | CRITICAL | Red | Entire string offline/faulty |
| 4 | `bypass-diode` | CRITICAL | Red | Diode failure (single or multi) |
| 5 | `offline-module` | HIGH | Orange | Module completely offline |
| 6 | `vegetation-shading` | LOW | Blue | Vegetation shadow on panels |
| 7 | `soiling` | LOW | Blue | Dust / dirt accumulation |
| 8 | `short-circuit` | HIGH | Orange | Short-circuit thermal signature |
| 9 | `hot-spot-low` | HIGH | Orange | Moderate thermal hot-spot |
| 10 | `hot-spot-high` | CRITICAL | Red | Severe thermal hot-spot |

> **Note:** Severity mapping is defined in `src/utils.py::SEVERITY_MAP` — use this as the single source of truth. Do NOT redefine severity in new modules.

### 2.3 Reusable Code

| File | Functions to Reuse |
|---|---|
| `src/utils.py` | `CANONICAL_CLASSES`, `SEVERITY_MAP`, `SEVERITY_COLOR_BGR`, `draw_detections_severity()`, `read_yolo_label()`, `write_yolo_label()`, `yolo_to_pixel()`, `load_bgr()`, `get_logger()` |
| `src/dataset.py` | `ISM_CLASSES_MAP`, `PV_CLASSES_MAP`, `_majority_class()`, `read_yolo_label()` |
| `src/augmentation.py` | Thermal augmentation pipeline (for future fine-tuning) |
| `output/inspection_report.json` | Output format reference (2,236 detections across 2,000 images) |

### 2.4 Training Configuration

From `configs/thermal.yaml`:
- Input size: **640×640**
- Batch: 16, Epochs: 100, Early stopping: patience=15
- No hue/saturation augmentation (thermal grayscale-like)
- Confidence threshold: **0.25** (recommended for inference)

---

## 3. System Architecture

### 3.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DRONE FLEET                                  │
│              [Thermal Camera]  +  [RGB Camera]                      │
└──────────────────────┬─────────────────────────┬────────────────────┘
                       │                         │
              thermal_001.jpg              rgb_001.jpg
                       │                         │
                       └──────────┬──────────────┘
                                  │  Image Pairs
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                     AXALON PLATFORM                                 │
│                                                                     │
│  ┌──────────────┐    ┌──────────────┐    ┌────────────────────┐    │
│  │   INGEST     │───▶│  DETECTION   │───▶│   LOCALIZATION     │    │
│  │              │    │              │    │                    │    │
│  │ • Validate   │    │ • YOLOv8s    │    │ • GPS extraction   │    │
│  │ • Pair match │    │ • best.pt    │    │ • Park mode detect │    │
│  │ • GPS EXIF   │    │ • 11 classes │    │ • Panel ID lookup  │    │
│  │ • Metadata   │    │ • Severity   │    │ • Grid synthesis   │    │
│  └──────────────┘    └──────────────┘    └────────────────────┘    │
│                                                  │                  │
│  ┌──────────────┐    ┌──────────────┐            │                  │
│  │   REPORTS    │◀───│   FUSION     │◀───────────┘                  │
│  │              │    │              │                                │
│  │ • PDF        │    │ • Overlay    │                                │
│  │ • Excel      │    │ • RGB+Thermal│                                │
│  │ • GeoJSON    │    │ • Annotated  │                                │
│  │ • JSON       │    │   output     │                                │
│  └──────────────┘    └──────────────┘                               │
│                                                                     │
│  ┌─────────────────┐    ┌────────────────────────────────────────┐  │
│  │   FastAPI REST  │    │         Streamlit Dashboard            │  │
│  │   (batch jobs)  │    │         (operator UI)                  │  │
│  └─────────────────┘    └────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────┘
```

### 3.2 Park Operation Modes

```
                    ┌─────────────────┐
                    │  Input Images   │
                    └────────┬────────┘
                             │
                    ┌────────▼────────┐
                    │  Mode Detection │
                    │  (auto/manual)  │
                    └────────┬────────┘
                             │
             ┌───────────────┼───────────────┐
             │                               │
    ┌────────▼────────┐             ┌────────▼────────┐
    │  NUMBERED PARK  │             │ UNNUMBERED PARK  │
    │                 │             │                  │
    │ • OCR on RGB    │             │ • Grid detection │
    │ • Parse IDs     │             │ • Synthetic IDs  │
    │   (C4-28, S3)   │             │   (R3-C7 format) │
    │ • Exact panel   │             │ • GPS-anchored   │
    │   location map  │             │   coordinates    │
    └────────┬────────┘             └────────┬─────────┘
             │                               │
             └───────────────┬───────────────┘
                             │
                    ┌────────▼────────┐
                    │  Unified Output │
                    │ Panel_ID | GPS  │
                    │ Anomaly | Sev.  │
                    └─────────────────┘
```

---

## 4. Module Specifications

### 4.1 Complete Project Structure

```
axalon_platform/
├── core/
│   ├── __init__.py
│   ├── detector.py          # YOLOv8 inference wrapper
│   ├── fusion.py            # Thermal ↔ RGB spatial alignment & overlay
│   ├── severity.py          # Re-exports from src/utils.py (do not duplicate)
│   └── geo.py               # GPS/EXIF extraction, GeoTIFF orthomosaic support
│
├── park/
│   ├── __init__.py
│   ├── numbering.py         # Panel ID OCR and parsing (C4-28, String-3, Row-Col)
│   ├── locator.py           # Map anomaly bbox → panel ID in park
│   └── layout.py            # Auto-detect park grid structure from image series
│
├── pipeline/
│   ├── __init__.py
│   ├── ingest.py            # Image pair ingestion, validation, metadata extraction
│   ├── batch.py             # Multi-image batch processing with progress tracking
│   └── orchestrator.py      # Full pipeline: ingest → detect → localize → report
│
├── reporting/
│   ├── __init__.py
│   ├── report.py            # PDF and Excel report generator
│   ├── map_renderer.py      # Annotated park map image output
│   ├── geojson_writer.py    # GeoJSON export (panel locations + anomalies)
│   └── templates/
│       ├── report.html      # Jinja2 PDF template
│       └── styles.css       # Report styling
│
├── api/
│   ├── __init__.py
│   ├── app.py               # FastAPI application
│   ├── schemas.py           # Pydantic request/response models
│   └── dependencies.py      # Shared FastAPI dependencies (DB session, etc.)
│
├── ui/
│   ├── dashboard.py         # Streamlit dashboard entry point
│   └── components/
│       ├── upload.py        # Image upload widget
│       ├── results.py       # Detection results display
│       └── park_map.py      # Interactive park map visualization
│
├── db/
│   ├── __init__.py
│   ├── models.py            # SQLAlchemy ORM models
│   └── session.py           # Database session management
│
├── config/
│   └── settings.yaml        # Global platform configuration
│
├── main.py                  # CLI entry point
├── requirements_platform.txt # New dependencies (beyond existing requirements.txt)
└── README_platform.md       # Quick-start guide
```

---

## 5. Detection & AI Pipeline

### 5.1 `core/detector.py` — YOLOv8 Inference Wrapper

**Responsibility:** Load the trained model once, run inference on thermal images, return structured detection dicts.

```python
# Interface specification (implement this exactly)

class SolarDetector:
    def __init__(self, weights_path: str, conf: float = 0.25, iou: float = 0.45, device: str = "0"):
        """
        Load YOLOv8s model from checkpoints/best.pt.
        - weights_path: path to best.pt
        - conf: confidence threshold (0.25 recommended from training config)
        - iou: NMS IoU threshold
        - device: "0" for GPU, "cpu" for CPU
        """
        ...

    def predict(self, thermal_image_path: str) -> list[dict]:
        """
        Run inference on a single thermal image.

        Returns list of detection dicts:
        [
            {
                "class": "hot-spot-high",        # from CANONICAL_CLASSES
                "class_id": 10,
                "confidence": 0.87,
                "bbox": [x1, y1, x2, y2],        # pixel coords in original image
                "bbox_norm": [cx, cy, w, h],      # YOLO normalized format
                "severity": "CRITICAL",           # from SEVERITY_MAP
                "color_bgr": (0, 0, 255),         # from SEVERITY_COLOR_BGR
            },
            ...
        ]
        """
        ...

    def predict_batch(self, image_paths: list[str]) -> list[list[dict]]:
        """Batch inference for efficiency. Returns one detection list per image."""
        ...
```

**Key implementation notes:**
- Use `from ultralytics import YOLO` — same framework used in training
- Import `CANONICAL_CLASSES`, `SEVERITY_MAP`, `SEVERITY_COLOR_BGR` from `src/utils.py` — do NOT redefine them
- Model should be loaded once at `__init__`, not per-call (heavy operation)
- The model was trained at `imgsz=640` — Ultralytics handles resize automatically

### 5.2 `core/fusion.py` — Thermal + RGB Alignment

**Responsibility:** Project thermal bounding boxes onto the corresponding RGB image for combined visualization.

**The alignment problem:** Thermal and RGB cameras have different fields of view, lens distortions, and mounting offsets on the drone. They are NOT pixel-aligned by default.

**Approach (3 tiers by available data):**

```
TIER 1 — GPS + Altitude (preferred):
  Both images have GPS EXIF → compute homography from ground sampling distance
  → project thermal bbox into RGB coordinate space

TIER 2 — Feature matching (fallback):
  Use ORB/SIFT keypoint matching between thermal (converted to grayscale)
  and RGB image to estimate homography H
  → cv2.perspectiveTransform(thermal_bbox_corners, H) → RGB coords

TIER 3 — Fixed offset (fast approximation):
  If camera rig has known fixed offset (e.g., 50px horizontal shift),
  apply a translation-only transform
  → configurable in settings.yaml as camera_offset: [dx, dy]
```

**Interface:**

```python
class ImageFusion:
    def __init__(self, mode: str = "auto", camera_offset: list[int] = [0, 0]):
        """
        mode: "gps" | "feature" | "offset" | "auto" (tries GPS → feature → offset)
        """
        ...

    def align_and_overlay(
        self,
        thermal_bgr: np.ndarray,
        rgb_bgr: np.ndarray,
        detections: list[dict],
        thermal_gps: dict | None = None,
        rgb_gps: dict | None = None,
    ) -> np.ndarray:
        """
        Returns RGB image with thermal detection bboxes projected and drawn.
        Uses draw_detections_severity() from src/utils.py for consistent coloring.
        """
        ...
```

### 5.3 `core/geo.py` — Geospatial Processing

**Responsibility:** Extract GPS metadata from images, compute real-world coordinates for detections.

```python
def extract_gps_exif(image_path: str) -> dict | None:
    """
    Extract GPS data from JPEG EXIF using Pillow + piexif.
    Returns: {"lat": float, "lon": float, "alt": float} or None if no GPS.
    """
    ...

def detection_to_gps(
    detection_bbox: list[int],   # [x1, y1, x2, y2] in image pixels
    image_gps: dict,             # {"lat", "lon", "alt"}
    image_size: tuple[int, int], # (width, height) in pixels
    gsd: float,                  # ground sampling distance in cm/pixel (from altitude)
) -> dict:
    """
    Convert pixel bbox center to GPS coordinate.
    GSD = (altitude_m * sensor_width_mm) / (focal_length_mm * image_width_px)
    Returns: {"lat": float, "lon": float}
    """
    ...

def compute_gsd(altitude_m: float, focal_length_mm: float = 13.0,
                sensor_width_mm: float = 17.3, image_width_px: int = 1920) -> float:
    """Ground Sampling Distance in cm/pixel."""
    return (altitude_m * 100 * sensor_width_mm) / (focal_length_mm * image_width_px)
```

**GeoTIFF / Orthomosaic support:**
- If drone outputs orthomosaics (GeoTIFF with embedded CRS), use `rasterio` to read geotransform
- Map pixel → world coordinate directly via `rasterio.transform.xy()`
- This is more accurate than EXIF-based estimation for large parks

---

## 6. Panel Localization Strategy

### 6.1 `park/numbering.py` — Panel ID OCR (Numbered Parks)

Solar parks often label inverter strings, rows, and panels. Example schemes:
- `C4-28` (cell row 4, panel 28)
- `String-3 / Panel-12`
- `INV-02 / STR-05 / MOD-11`
- `A-103`, `B-27`

**OCR Pipeline:**

```python
import easyocr

class PanelNumberOCR:
    def __init__(self, languages: list[str] = ["en"]):
        self.reader = easyocr.Reader(languages, gpu=True)

    def extract_ids_from_rgb(self, rgb_image: np.ndarray) -> list[dict]:
        """
        Run OCR on full RGB image, filter results matching panel ID patterns.

        Returns:
        [
            {
                "text": "C4-28",
                "bbox": [[x1,y1],[x2,y1],[x2,y2],[x1,y2]],  # EasyOCR quad format
                "center": [cx, cy],
                "confidence": 0.94,
                "parsed": {"type": "cell", "row": 4, "number": 28}
            },
            ...
        ]
        """
        ...

    def parse_panel_id(self, text: str) -> dict | None:
        """
        Parse a panel ID string into structured components.

        Handles patterns:
        - C{row}-{num}     → {"type": "cell", "row": int, "number": int}
        - S{row}-{num}     → {"type": "string", "row": int, "number": int}
        - INV-{n}/STR-{n}  → {"type": "inverter_string", "inv": int, "str": int}
        - R{n}-C{n}        → {"type": "grid", "row": int, "col": int}
        Returns None if pattern not recognized.
        """
        import re
        # Example patterns — extend as needed for specific park
        patterns = [
            (r'^C(\d+)-(\d+)$',       lambda m: {"type": "cell", "row": int(m[1]), "number": int(m[2])}),
            (r'^S(\d+)-(\d+)$',       lambda m: {"type": "string", "row": int(m[1]), "number": int(m[2])}),
            (r'^R(\d+)-C(\d+)$',      lambda m: {"type": "grid", "row": int(m[1]), "col": int(m[2])}),
            (r'^INV-(\d+)/STR-(\d+)$',lambda m: {"type": "inv_string", "inv": int(m[1]), "str": int(m[2])}),
        ]
        ...
```

### 6.2 `park/layout.py` — Auto-Grid Detection (Unnumbered Parks)

When panels have no visible numbering, infer the grid layout from image content.

**Algorithm:**

```
Step 1: Panel Detection
  → Run YOLOv8s on RGB image (not just thermal)
  → Or use contour detection:
     gray = cv2.cvtColor(rgb, cv2.COLOR_BGR2GRAY)
     edges = cv2.Canny(gray, 50, 150)
     contours = cv2.findContours(edges, ...)
     panel_rects = [cv2.boundingRect(c) for c in contours if area_in_range(c)]

Step 2: Grid Fitting
  → Cluster panel centers by Y-coordinate → row assignment
  → Within each row, sort by X-coordinate → column assignment
  → Assign synthetic ID: "R{row+1}-C{col+1}"

Step 3: GPS Anchoring
  → Map R1-C1 to the GPS coordinate of the first detected panel
  → Use GSD to compute GPS offset for each subsequent panel
  → Store {panel_id: (lat, lon)} mapping

Step 4: Persistence
  → Save layout to SQLite (park_id + panel grid) for future flights
```

**Interface:**

```python
class ParkLayoutDetector:
    def detect_grid(
        self,
        rgb_images: list[np.ndarray],
        gps_coords: list[dict] | None = None,
    ) -> dict:
        """
        Analyze a series of RGB images from a flight.
        Returns park layout:
        {
            "mode": "auto-grid",
            "total_panels": 247,
            "rows": 13,
            "cols_per_row": [19, 19, 19, ...],
            "panel_map": {
                "R1-C1": {"bbox_image": [...], "gps": {"lat": ..., "lon": ...}},
                "R1-C2": {...},
                ...
            }
        }
        """
        ...
```

### 6.3 `park/locator.py` — Anomaly-to-Panel Mapping

**Responsibility:** Given a detection (bbox in thermal image) and park layout, identify which panel is affected.

```python
class AnomalyLocator:
    def __init__(self, park_layout: dict, mode: str = "auto"):
        """
        mode: "numbered" | "unnumbered" | "auto"
        """
        ...

    def locate(
        self,
        detection: dict,           # from SolarDetector.predict()
        image_gps: dict,           # GPS of the drone at capture
        thermal_image_size: tuple, # (width, height)
    ) -> dict:
        """
        Returns:
        {
            "panel_id": "C4-28",              # or "R3-C7" for synthetic
            "panel_gps": {"lat": ..., "lon": ...},
            "anomaly": "hot-spot-high",
            "severity": "CRITICAL",
            "confidence": 0.87,
            "detection_gps": {"lat": ..., "lon": ...},  # exact anomaly coords
        }
        """
        ...
```

---

## 7. Reporting & Outputs

### 7.1 Output Data Model

Every inspection produces a structured result compatible with the existing `output/inspection_report.json` format:

```json
{
  "inspection_id": "AXL-2024-11-15-001",
  "park_id": "SOLAR_PARK_GUJARAT_01",
  "park_mode": "numbered",
  "flight_date": "2024-11-15",
  "total_images": 450,
  "total_panels_inspected": 1200,
  "total_detections": 87,
  "summary": {
    "CRITICAL": 12,
    "HIGH": 23,
    "MEDIUM": 41,
    "LOW": 11
  },
  "detections": [
    {
      "image_id": "thermal_0042",
      "thermal_path": "flight_01/thermal/thermal_0042.jpg",
      "rgb_path": "flight_01/rgb/rgb_0042.jpg",
      "panel_id": "C4-28",
      "anomaly_class": "hot-spot-high",
      "class_id": 10,
      "severity": "CRITICAL",
      "confidence": 0.91,
      "bbox": [145, 89, 312, 201],
      "gps": {"lat": 23.4521, "lon": 72.8834, "alt": 45.2},
      "detection_gps": {"lat": 23.4521, "lon": 72.8834}
    }
  ]
}
```

### 7.2 `reporting/report.py` — PDF & Excel Reports

**PDF Report Structure (via Jinja2 + WeasyPrint):**

```
┌─────────────────────────────────────┐
│ AXALON SYSTEMS - INSPECTION REPORT  │
│ Park: [Name] | Date: [Date]         │
├─────────────────────────────────────┤
│ EXECUTIVE SUMMARY                   │
│ ● Total panels: 1,200               │
│ ● Anomalies detected: 87            │
│ ● Critical issues: 12               │
│ [Severity pie chart]                │
├─────────────────────────────────────┤
│ ANOMALY MAP                         │
│ [Annotated park overview image]     │
├─────────────────────────────────────┤
│ PANEL-LEVEL FINDINGS                │
│ Panel | Class | Severity | GPS      │
│ C4-28 | Hot-High | CRITICAL | ...   │
│ C4-29 | Bypass | CRITICAL | ...     │
│ ...                                 │
├─────────────────────────────────────┤
│ RECOMMENDATIONS                     │
│ CRITICAL panels → immediate repair  │
│ HIGH panels → repair within 30 days │
│ MEDIUM → next maintenance cycle     │
│ LOW → monitor at next inspection    │
└─────────────────────────────────────┘
```

**Excel Report:** Multi-sheet workbook:
- Sheet 1: Summary (counts per severity, per class)
- Sheet 2: Full detection log (all detections, all metadata)
- Sheet 3: Panel priority list (sorted by severity, actionable)
- Sheet 4: GPS coordinates (for field teams)

### 7.3 `reporting/map_renderer.py` — Park Map

Render an overhead view of the solar park with anomalies plotted:

```python
def render_park_map(
    park_layout: dict,
    detections: list[dict],
    output_path: str,
    background_rgb: np.ndarray | None = None,  # orthomosaic if available
) -> np.ndarray:
    """
    Render a 2D grid map of the park with anomalies color-coded by severity.
    If orthomosaic available, overlay on real imagery.
    Otherwise, render a synthetic grid diagram.

    Each panel cell is colored:
    - Gray: no anomaly
    - Blue: LOW
    - Yellow: MEDIUM
    - Orange: HIGH
    - Red: CRITICAL
    (reuses SEVERITY_COLOR_BGR from src/utils.py)
    """
    ...
```

### 7.4 GeoJSON Export

```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "Point",
        "coordinates": [72.8834, 23.4521]
      },
      "properties": {
        "panel_id": "C4-28",
        "anomaly": "hot-spot-high",
        "severity": "CRITICAL",
        "confidence": 0.91,
        "inspection_date": "2024-11-15"
      }
    }
  ]
}
```

Compatible with QGIS, Google Earth, ArcGIS for field navigation.

---

## 8. REST API Design

### 8.1 FastAPI Application (`api/app.py`)

```python
from fastapi import FastAPI, UploadFile, BackgroundTasks
from fastapi.responses import FileResponse

app = FastAPI(
    title="Axalon Solar Inspection API",
    version="1.0.0",
    description="Solar anomaly detection for drone-captured thermal + RGB imagery"
)
```

### 8.2 Endpoints

#### `POST /inspect` — Single Image Pair
```
Request:
  multipart/form-data:
    thermal_image: file (JPEG/PNG)
    rgb_image: file (JPEG/PNG, optional)
    park_id: string (optional, for panel lookup)
    park_mode: "numbered" | "unnumbered" | "auto" (default: "auto")

Response 200:
{
  "job_id": "job_abc123",
  "status": "completed",
  "detections": [...],           # list of detection dicts
  "panel_locations": [...],      # list of localized panels
  "annotated_thermal_url": "/results/job_abc123/thermal_annotated.jpg",
  "annotated_rgb_url": "/results/job_abc123/rgb_annotated.jpg",
  "processing_time_ms": 234
}
```

#### `POST /batch` — Folder Submission
```
Request:
  multipart/form-data:
    images: file[] (zip archive of thermal+rgb pairs)
    park_id: string
    park_mode: string
    naming_convention: "thermal_XXX / rgb_XXX" | "ir_XXX / vis_XXX" | custom

Response 202:
{
  "job_id": "batch_xyz456",
  "status": "queued",
  "total_pairs": 450,
  "estimated_time_seconds": 180
}
```

#### `GET /status/{job_id}` — Job Status
```
Response 200:
{
  "job_id": "batch_xyz456",
  "status": "processing",   # queued | processing | completed | failed
  "progress": 0.34,         # 0.0 to 1.0
  "processed": 153,
  "total": 450,
  "elapsed_seconds": 61
}
```

#### `GET /report/{job_id}` — Download Report
```
Query params:
  format: "pdf" | "excel" | "json" | "geojson"

Response 200: File download (Content-Disposition: attachment)
```

#### `GET /park/{park_id}` — Park Overview
```
Response 200:
{
  "park_id": "SOLAR_PARK_GUJARAT_01",
  "last_inspection": "2024-11-15",
  "total_panels": 1200,
  "total_inspections": 3,
  "current_anomalies": {
    "CRITICAL": 12,
    "HIGH": 23,
    "MEDIUM": 41,
    "LOW": 11
  },
  "panel_status": [
    {"panel_id": "C4-28", "last_anomaly": "hot-spot-high", "severity": "CRITICAL"},
    ...
  ]
}
```

#### `GET /results/{job_id}/{filename}` — Serve annotated images
```
Response 200: Image file
```

### 8.3 Pydantic Schemas (`api/schemas.py`)

```python
from pydantic import BaseModel

class Detection(BaseModel):
    class_name: str
    class_id: int
    confidence: float
    bbox: list[int]           # [x1, y1, x2, y2]
    severity: str
    panel_id: str | None = None
    gps: dict | None = None

class InspectionResult(BaseModel):
    job_id: str
    status: str
    detections: list[Detection]
    summary: dict[str, int]   # severity → count
    processing_time_ms: int
```

---

## 9. Dashboard / UI

### 9.1 Streamlit Dashboard (`ui/dashboard.py`)

**Page 1 — Upload & Inspect:**
```
┌────────────────────────────────────────────────────┐
│  🛸 Axalon Solar Inspection Dashboard              │
├────────────────────────────────────────────────────┤
│  Park ID: [_______________] Mode: [auto ▼]         │
│                                                    │
│  Upload Thermal Image    Upload RGB Image          │
│  [  Drop file here  ]    [  Drop file here  ]      │
│                                                    │
│  [  RUN INSPECTION  ]                              │
├────────────────────────────────────────────────────┤
│  Results:                                          │
│  ┌─────────────┐  ┌─────────────┐                  │
│  │ Thermal+BB  │  │   RGB+BB    │                  │
│  │ (annotated) │  │ (overlay)   │                  │
│  └─────────────┘  └─────────────┘                  │
│                                                    │
│  Detections:                                       │
│  🔴 CRITICAL: hot-spot-high (C4-28)  conf: 0.91   │
│  🟠 HIGH: offline-module (C4-29)     conf: 0.78   │
│  🟡 MEDIUM: cell-multi (C5-12)       conf: 0.65   │
│                                                    │
│  [Download PDF]  [Download Excel]  [Download JSON] │
└────────────────────────────────────────────────────┘
```

**Page 2 — Batch Processing:**
- Upload zip of image pairs
- Progress bar with live status
- Summary statistics on completion
- Download all reports

**Page 3 — Park Map:**
- Grid visualization of the entire solar park
- Color-coded cells by severity
- Click cell → see detection details
- Export park map as PNG / GeoJSON

**Page 4 — Historical Analysis:**
- Select park → view inspection history
- Trend charts: anomaly count over time per class
- Deterioration tracking: panels with recurring anomalies

---

## 10. Configuration Reference

### `config/settings.yaml`

```yaml
# ── Model Configuration ──────────────────────────────────────────────────────
model:
  weights: solar_thermal_detection/checkpoints/best.pt
  confidence: 0.25          # from training config — do not lower without testing
  iou_threshold: 0.45
  imgsz: 640                # must match training size
  device: "0"               # "0" = first GPU, "cpu" = CPU fallback
  batch_size: 8             # for batch inference

# ── Park Configuration ────────────────────────────────────────────────────────
park:
  mode: auto                # "numbered" | "unnumbered" | "auto"
  ocr_engine: easyocr       # "easyocr" | "tesseract"
  ocr_confidence: 0.7       # minimum OCR confidence to accept a panel ID
  grid_min_panel_area: 500  # minimum contour area (px²) to count as panel
  grid_max_panel_area: 50000

# ── Camera / Drone Configuration ─────────────────────────────────────────────
camera:
  thermal_focal_length_mm: 13.0
  thermal_sensor_width_mm: 17.3
  rgb_focal_length_mm: 24.0
  rgb_sensor_width_mm: 35.9
  offset_px: [0, 0]          # [dx, dy] pixel offset thermal→RGB (for fixed rigs)
  alignment_mode: auto       # "gps" | "feature" | "offset" | "auto"

# ── Output Configuration ──────────────────────────────────────────────────────
output:
  base_dir: output/
  save_annotated_thermal: true
  save_annotated_rgb: true
  save_fused_overlay: true
  report_formats: [pdf, excel, json, geojson]
  annotated_thickness: 2     # bbox line thickness in pixels
  annotated_font_scale: 0.45 # text size (matches existing utils.py default)

# ── Detection Thresholds ──────────────────────────────────────────────────────
thresholds:
  alert_on_critical: true    # flag inspection if any CRITICAL detected
  min_confidence: 0.3        # discard detections below this (post-NMS filter)
  max_detections_per_image: 100

# ── API Configuration ─────────────────────────────────────────────────────────
api:
  host: "0.0.0.0"
  port: 8000
  workers: 1                 # keep at 1 if GPU shared across requests
  max_upload_size_mb: 50
  results_ttl_hours: 24      # auto-delete results after N hours

# ── Database ──────────────────────────────────────────────────────────────────
database:
  url: "sqlite:///axalon_inspections.db"
  # For production: "postgresql://user:pass@host:5432/axalon"

# ── Geospatial ────────────────────────────────────────────────────────────────
geo:
  default_crs: "EPSG:4326"   # WGS84 lat/lon
  default_altitude_m: 40.0   # fallback if no EXIF altitude
```

---

## 11. Database Schema

### `db/models.py` — SQLAlchemy Models

```python
# Park table — one row per solar farm
class Park(Base):
    __tablename__ = "parks"
    id           = Column(String, primary_key=True)  # e.g. "SOLAR_PARK_GUJARAT_01"
    name         = Column(String)
    location_gps = Column(JSON)    # {"lat": ..., "lon": ...}
    total_panels = Column(Integer)
    park_mode    = Column(String)  # "numbered" | "unnumbered"
    panel_layout = Column(JSON)    # full layout dict from ParkLayoutDetector
    created_at   = Column(DateTime)

# Inspection table — one row per flight/inspection session
class Inspection(Base):
    __tablename__ = "inspections"
    id           = Column(String, primary_key=True)  # "AXL-2024-11-15-001"
    park_id      = Column(String, ForeignKey("parks.id"))
    flight_date  = Column(Date)
    total_images = Column(Integer)
    total_detections = Column(Integer)
    summary      = Column(JSON)    # {"CRITICAL": n, "HIGH": n, ...}
    report_path  = Column(String)  # path to generated PDF
    created_at   = Column(DateTime)

# Detection table — one row per anomaly detection
class Detection(Base):
    __tablename__ = "detections"
    id           = Column(Integer, primary_key=True, autoincrement=True)
    inspection_id= Column(String, ForeignKey("inspections.id"))
    panel_id     = Column(String)   # "C4-28" or "R3-C7"
    thermal_path = Column(String)
    rgb_path     = Column(String)
    anomaly_class= Column(String)   # from CANONICAL_CLASSES
    class_id     = Column(Integer)
    severity     = Column(String)   # CRITICAL / HIGH / MEDIUM / LOW
    confidence   = Column(Float)
    bbox         = Column(JSON)     # [x1, y1, x2, y2]
    gps          = Column(JSON)     # {"lat": ..., "lon": ...}
    detection_gps= Column(JSON)
    created_at   = Column(DateTime)
```

---

## 12. Installation & Dependencies

### 12.1 Existing Dependencies (already in `requirements.txt`)
- `ultralytics` (YOLOv8)
- `torch`, `torchvision`
- `opencv-python`
- `albumentations`
- `scikit-learn`
- `matplotlib`, `seaborn`
- `numpy`

### 12.2 New Platform Dependencies (`requirements_platform.txt`)

```txt
# API
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
python-multipart>=0.0.9      # FastAPI file upload support

# Dashboard
streamlit>=1.34.0

# OCR (panel number recognition)
easyocr>=1.7.1
# OR: pytesseract>=0.3.10 + system: sudo apt install tesseract-ocr

# Geospatial
rasterio>=1.3.9
geopandas>=0.14.3
pyproj>=3.6.1
Pillow>=10.3.0               # EXIF GPS extraction
piexif>=1.1.3                # GPS EXIF metadata parsing

# Reporting
jinja2>=3.1.4
weasyprint>=61.2             # PDF generation from HTML
openpyxl>=3.1.2              # Excel export

# Database
sqlalchemy>=2.0.29
alembic>=1.13.1              # DB migrations

# Utilities
pydantic>=2.7.0
python-dotenv>=1.0.1
tqdm>=4.66.2                 # Progress bars for batch processing
```

### 12.3 Installation Script

```bash
#!/bin/bash
# Install platform dependencies (assumes existing AxalonPIPE environment active)

cd /home/parakh/Desktop/AxalonPIPE

# Install new dependencies
pip install -r requirements_platform.txt

# System dependencies for WeasyPrint (PDF)
sudo apt install -y libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0

# Optional: Tesseract OCR (alternative to EasyOCR)
# sudo apt install -y tesseract-ocr tesseract-ocr-eng

# Initialize database
python -c "from db.session import init_db; init_db()"

echo "Installation complete."
```

### 12.4 Quick Start

```bash
# Single image pair inspection (CLI)
python main.py \
  --thermal path/to/thermal_001.jpg \
  --rgb path/to/rgb_001.jpg \
  --park-id SOLAR_PARK_01 \
  --output output/

# Batch inspection
python main.py \
  --batch path/to/flight_folder/ \
  --park-id SOLAR_PARK_01

# Start API server
uvicorn api.app:app --host 0.0.0.0 --port 8000

# Launch dashboard
streamlit run ui/dashboard.py
```

---

## 13. Project Structure

### 13.1 Image Pair Naming Convention

The platform supports multiple naming schemes. Configure in `settings.yaml`:

| Convention | Thermal | RGB | Notes |
|---|---|---|---|
| **default** | `thermal_001.jpg` | `rgb_001.jpg` | Recommended |
| **ir_vis** | `ir_001.jpg` | `vis_001.jpg` | Common in DJI |
| **numeric** | `001_T.jpg` | `001_V.jpg` | Timestamp-based |
| **timestamp** | `20241115_120001_T.jpg` | `20241115_120001_V.jpg` | Preferred for GPS sync |

If only thermal images are provided (no RGB), the platform runs detection-only mode (no fusion overlay, OCR disabled for panel numbering).

### 13.2 Input Folder Structure

```
flight_mission_2024_11_15/
├── thermal/
│   ├── thermal_001.jpg    ← primary detection input
│   ├── thermal_002.jpg
│   └── ...
├── rgb/
│   ├── rgb_001.jpg        ← panel ID OCR + fusion target
│   ├── rgb_002.jpg
│   └── ...
└── mission_metadata.json  ← optional: {park_id, pilot, drone_id, gsd}
```

### 13.3 Output Folder Structure

```
output/
└── AXL-2024-11-15-001/
    ├── inspection_report.json     ← machine-readable (existing format)
    ├── inspection_report.pdf      ← operator PDF
    ├── inspection_report.xlsx     ← Excel for maintenance team
    ├── park_anomaly_map.png       ← overhead park visualization
    ├── park_anomaly_map.geojson   ← GIS-compatible
    └── annotated/
        ├── thermal_001_annotated.jpg   ← thermal with colored bboxes
        ├── rgb_001_annotated.jpg       ← RGB with projected bboxes
        ├── fused_001.jpg               ← side-by-side or overlay
        └── ...
```

---

## 14. Development Roadmap

### Phase 1 — Core Detection Pipeline (Week 1-2)
- [ ] `core/detector.py` — YOLOv8 wrapper using `checkpoints/best.pt`
- [ ] `pipeline/ingest.py` — Image pair validation and loading
- [ ] `pipeline/orchestrator.py` — Basic single-pair pipeline
- [ ] `main.py` — CLI entry point
- [ ] Validate output matches `output/inspection_report.json` format

### Phase 2 — Geospatial & Reporting (Week 3)
- [ ] `core/geo.py` — GPS EXIF extraction
- [ ] `reporting/report.py` — JSON + Excel output
- [ ] `reporting/map_renderer.py` — Park grid visualization
- [ ] `reporting/geojson_writer.py` — GeoJSON export
- [ ] `reporting/report.py` — PDF (Jinja2 + WeasyPrint)

### Phase 3 — Panel Localization (Week 4)
- [ ] `park/numbering.py` — EasyOCR panel ID extraction
- [ ] `park/layout.py` — Auto-grid detection for unnumbered parks
- [ ] `park/locator.py` — Anomaly-to-panel mapping

### Phase 4 — Fusion & RGB Integration (Week 5)
- [ ] `core/fusion.py` — Thermal→RGB projection (Tier 1: GPS, Tier 2: feature matching)
- [ ] Test on actual paired drone images from Axalon fleet

### Phase 5 — API & Dashboard (Week 6)
- [ ] `api/app.py` — FastAPI REST endpoints
- [ ] `db/models.py` — SQLAlchemy + SQLite
- [ ] `ui/dashboard.py` — Streamlit dashboard (upload, results, park map)

### Phase 6 — Testing & Deployment (Week 7)
- [ ] End-to-end test with real flight data
- [ ] Performance benchmarking (target: < 500ms per image pair on GPU)
- [ ] Docker containerization for deployment
- [ ] Documentation finalization

---

## 15. Verification & Testing

### 15.1 Unit Tests

```bash
# Test detector with existing annotated images
python -m pytest tests/test_detector.py -v

# Test with one of the 2000 pre-inspected images
python main.py \
  --thermal solar_thermal_detection/data/images/test/some_test.jpg \
  --compare-with solar_thermal_detection/output/inspection_report.json
```

### 15.2 End-to-End Test Plan

| Test | Expected Output | Pass Criteria |
|---|---|---|
| Single thermal image → detect | Detection JSON with severity | ≥ 1 detection on known anomaly image |
| Numbered park RGB → OCR | Panel ID extracted | Correct panel ID like "C4-28" |
| Unnumbered park series → grid | Synthetic IDs assigned | All panels get unique "R{n}-C{n}" ID |
| GPS image → detection GPS | Lat/lon per anomaly | Coords within 10m of true panel location |
| Batch 10 pairs → batch output | 10 annotated images + 1 report | All 10 processed without error |
| API POST /inspect | JSON response | Status 200, detections list present |
| API GET /report/{id} | PDF file download | Valid PDF, non-empty |
| Dashboard upload | Annotated image display | Detection bboxes visible in correct color |

### 15.3 Performance Targets

| Metric | Target | Measurement Method |
|---|---|---|
| Single image inference | < 100ms (GPU) | `time.perf_counter()` around `detector.predict()` |
| Single pair full pipeline | < 500ms (GPU) | Orchestrator wall time |
| Batch 100 pairs | < 60 seconds (GPU) | Batch orchestrator total time |
| PDF report generation | < 5 seconds | `report.generate()` wall time |
| OCR panel ID extraction | < 2 seconds per image | `numbering.extract_ids_from_rgb()` wall time |

### 15.4 Known Limitations & Future Work

1. **Thermal-RGB alignment** is approximate without camera calibration data. For production, perform a one-time calibration flight to determine the exact homography between cameras.
2. **OCR accuracy** depends on image resolution and label clarity. Low-altitude flights (< 20m) yield better results.
3. **Auto-grid detection** may fail on non-rectangular park layouts (curved arrays, hillside installations). Manual layout definition will be supported via a JSON config file.
4. **Model retraining** with Axalon's own drone imagery is recommended after initial deployment to adapt to specific thermal camera characteristics.
5. **Orthomosaic processing** (full-flight GeoTIFF) is designed but requires `rasterio` and a drone software (DJI Terra, Agisoft Metashape) to generate the orthomosaic.

---

## Appendix A — Severity Reference

Direct copy from `solar_thermal_detection/src/utils.py::SEVERITY_MAP` (canonical truth):

```python
SEVERITY_MAP = {
    "hot-spot-high":      "CRITICAL",   # Severe thermal hot-spot → immediate shutdown
    "bypass-diode":       "CRITICAL",   # Diode failure → fire risk
    "string":             "CRITICAL",   # Entire string failure → major power loss
    "hot-spot-low":       "HIGH",       # Moderate hot-spot → repair within 30 days
    "offline-module":     "HIGH",       # Module completely offline → revenue loss
    "short-circuit":      "HIGH",       # Short circuit → potential damage
    "cell":               "MEDIUM",     # Cell-level anomaly → monitor
    "cell-multi":         "MEDIUM",     # Multi-cell anomaly → schedule maintenance
    "module":             "MEDIUM",     # Module-level thermal deviation → inspect
    "vegetation-shading": "LOW",        # Vegetation → trim/clear
    "soiling":            "LOW",        # Dust/dirt → clean at next service
}
```

## Appendix B — ISM Dataset Class Mapping

From `solar_thermal_detection/src/dataset.py::ISM_CLASSES_MAP`:

| ISM Dataset Class | → Canonical Class | Rationale |
|---|---|---|
| `Cell` | `cell` | Direct mapping |
| `Cell-Multi` | `cell-multi` | Direct mapping |
| `Cracking` | `hot-spot-low` | Physical crack → thermal signature |
| `Hot-Spot` | `hot-spot-low` | Direct mapping |
| `Hot-Spot-Multi` | `hot-spot-high` | Multi-cell → severe |
| `Shadowing` | `vegetation-shading` | Shadow source |
| `Diode` | `bypass-diode` | Direct mapping |
| `Diode-Multi` | `bypass-diode` | Both map to same canonical |
| `Vegetation` | `vegetation-shading` | Direct mapping |
| `Soiling` | `soiling` | Direct mapping |
| `Offline-Module` | `offline-module` | Direct mapping |
| `No-Anomaly` | `module` | Nominal module kept as detection target |

---

*Document prepared for Axalon Systems internal development team.*  
*Model weights, dataset, and source code located at `/home/parakh/Desktop/AxalonPIPE/`*
