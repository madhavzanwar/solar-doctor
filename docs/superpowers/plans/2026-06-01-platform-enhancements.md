# Platform Enhancements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Download and prepare training datasets, train YOLO11m on combined aerial thermal solar data at 20-25m deployment altitude, export to TensorRT for Jetson, then add temperature extraction, inspection metadata persistence, IEC compliance warnings, revenue loss estimation, and fault comment threads to the platform.

**Architecture:** Training pipeline combines PV-Hawk (drone-captured) + Roboflow solar thermal datasets remapped to the 11-class canonical schema, then fine-tunes YOLO11m. The trained checkpoint exports to TensorRT for the Jetson Orin Nano. Platform pipeline adds RAW16 temperature extraction, IEC-compliant metadata persistence, and a fault comment thread.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy, Alembic, NumPy, Ultralytics YOLO11m, TensorRT, pytest, Roboflow SDK

---

## Context — What is Already Done

These changes were made before this plan and do NOT need to be redone:
- `ml/requirements.txt` — `ultralytics>=8.3.0`
- `ml/configs/thermal.yaml` — `model: yolo11m.pt`
- `platform/core/detector.py` — docstrings updated to YOLO11m
- `platform/api/app.py` — health endpoint and description updated to YOLO11m
- `platform/reporting/templates/report.html` — footer updated to YOLO11m
- `platform/config/settings.yaml` — `default_altitude_m: 20`, sensor dimensions corrected, camera section cleaned up
- `CLAUDE.md` — all YOLOv8s references updated to YOLO11m

---

## File Map

### New Files
| File | Responsibility |
|---|---|
| `platform/core/temp_extractor.py` | Load RAW16 temp matrix, extract per-bbox min/max/avg/delta_T |
| `tests/backend/test_temp_extractor.py` | Unit tests for temp_extractor |
| `alembic/versions/0002_inspection_metadata.py` | Migration: add 8 columns to inspections table |
| `alembic/versions/0003_fault_comments.py` | Migration: create fault_comments table |
| `tests/backend/test_fault_comments.py` | Tests for comment endpoints |

### Modified Files
| File | What changes |
|---|---|
| `platform/pipeline/ingest.py` | `find_image_pairs` adds `temp_raw` field per pair |
| `platform/pipeline/orchestrator.py` | `inspect_pair` accepts `temp_raw_path` + irradiance; `inspect_folder` accepts `site_meta` |
| `platform/db/models.py` | 8 new columns on `Inspection`; new `FaultComment` model |
| `platform/api/app.py` | `inspection_type` + `inspection_level` form params; IEC warning; comment endpoints; altitude default 20m |
| `platform/reporting/report.py` | Populate delta_t + revenue_loss columns in Excel/PDF |
| `platform/config/settings.yaml` | Add `economics` section |

---

## Task 1: temp_extractor.py — Core Temperature Module

**Files:**
- Create: `platform/core/temp_extractor.py`
- Create: `tests/backend/test_temp_extractor.py`

### Background
The iTL612R Pro saves a `img_NNN_temp.raw` companion alongside each thermal JPEG when configured in MATRIX-TEMP mode. The file is a flat 640×512 array of `uint16` values. Conversion to °C: `temp = raw * scale - offset` where Sensmart's default is `scale=0.04`, `offset=273.15` (raw is in units of ~0.04 K, offset from ~0 K). These values are configurable in `settings.yaml` for field calibration.

- [ ] **Step 1: Write the failing tests**

```python
# tests/backend/test_temp_extractor.py
import numpy as np
import pytest
from pathlib import Path
from platform.core.temp_extractor import (
    load_temp_matrix,
    extract_bbox_temps,
    compute_delta_t,
    normalize_delta_t,
    find_temp_companion,
)


def _write_raw(path: Path, value: int, width=640, height=512):
    data = np.full(width * height, value, dtype=np.uint16)
    path.write_bytes(data.tobytes())


def test_load_temp_matrix_shape_and_value(tmp_path):
    raw = tmp_path / "img_001_temp.raw"
    # scale=0.04, offset=273.15 → (7500 * 0.04) - 273.15 = 300 - 273.15 = 26.85
    _write_raw(raw, 7500)
    matrix = load_temp_matrix(raw)
    assert matrix.shape == (512, 640)
    assert abs(matrix[0, 0] - 26.85) < 0.01


def test_load_temp_matrix_wrong_size(tmp_path):
    bad = tmp_path / "bad_temp.raw"
    bad.write_bytes(b"\x00" * 100)
    with pytest.raises(ValueError, match="Expected"):
        load_temp_matrix(bad)


def test_load_temp_matrix_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_temp_matrix(tmp_path / "missing_temp.raw")


def test_extract_bbox_temps_hotspot():
    matrix = np.full((512, 640), 25.0, dtype=np.float32)
    matrix[10:20, 10:20] = 55.0
    result = extract_bbox_temps(matrix, [10, 10, 20, 20])
    assert result["min_temp"] == pytest.approx(55.0)
    assert result["max_temp"] == pytest.approx(55.0)
    assert result["avg_temp"] == pytest.approx(55.0)


def test_extract_bbox_temps_clips_to_frame():
    matrix = np.full((512, 640), 30.0, dtype=np.float32)
    # bbox extends beyond frame — should clip, not crash
    result = extract_bbox_temps(matrix, [630, 505, 650, 520])
    assert result["max_temp"] == pytest.approx(30.0)


def test_compute_delta_t():
    matrix = np.full((512, 640), 25.0, dtype=np.float32)
    matrix[100:120, 100:120] = 45.0
    result = compute_delta_t(matrix, [100, 100, 120, 120])
    assert result["delta_t_measured"] == pytest.approx(20.0, abs=0.5)
    assert result["reference_temp"] == pytest.approx(25.0, abs=0.5)


def test_normalize_delta_t():
    assert normalize_delta_t(10.0, 800.0) == pytest.approx(12.5)


def test_normalize_delta_t_zero_irradiance():
    assert normalize_delta_t(10.0, 0.0) is None


def test_find_temp_companion_exists(tmp_path):
    jpg = tmp_path / "img_001.jpg"
    raw = tmp_path / "img_001_temp.raw"
    jpg.touch()
    raw.touch()
    assert find_temp_companion(jpg) == raw


def test_find_temp_companion_missing(tmp_path):
    jpg = tmp_path / "img_001.jpg"
    jpg.touch()
    assert find_temp_companion(jpg) is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/parakh/Desktop/AxalonSystems
python -m pytest tests/backend/test_temp_extractor.py -v 2>&1 | head -20
```
Expected: `ImportError: cannot import name 'load_temp_matrix'`

- [ ] **Step 3: Create temp_extractor.py**

```python
# platform/core/temp_extractor.py
"""
temp_extractor.py — RAW16 temperature matrix extraction for iTL612R Pro.

The iTL612R Pro saves a companion _temp.raw file alongside each thermal JPEG
when operating in MATRIX-TEMP mode. The file is a flat 640×512 uint16 array.

Conversion: temp_celsius = (raw_value * scale) - offset
iTL612R Pro defaults: scale=0.04, offset=273.15

Calibrate scale/offset in settings.yaml:
  camera:
    temp_scale: 0.04
    temp_offset: 273.15
"""
from __future__ import annotations

import numpy as np
from pathlib import Path

_DEFAULT_SCALE = 0.04
_DEFAULT_OFFSET = 273.15


def load_temp_matrix(
    raw_path: str | Path,
    width: int = 640,
    height: int = 512,
    scale: float = _DEFAULT_SCALE,
    offset: float = _DEFAULT_OFFSET,
) -> np.ndarray:
    """Load a RAW16 temperature matrix and return float32 array in °C."""
    raw_path = Path(raw_path)
    if not raw_path.exists():
        raise FileNotFoundError(f"Temperature matrix not found: {raw_path}")
    raw = np.frombuffer(raw_path.read_bytes(), dtype=np.uint16)
    if raw.size != width * height:
        raise ValueError(
            f"Expected {width * height} pixels, got {raw.size} in {raw_path.name}"
        )
    return (raw.reshape(height, width).astype(np.float32) * scale) - offset


def extract_bbox_temps(
    temp_matrix: np.ndarray,
    bbox: list[int],
) -> dict:
    """Return min/max/avg temperature (°C) inside a detection bounding box."""
    x1, y1, x2, y2 = bbox
    h, w = temp_matrix.shape
    x1, y1 = max(0, x1), max(0, y1)
    x2, y2 = min(w, x2), min(h, y2)
    region = temp_matrix[y1:y2, x1:x2]
    if region.size == 0:
        return {"min_temp": None, "max_temp": None, "avg_temp": None}
    return {
        "min_temp": round(float(np.min(region)), 2),
        "max_temp": round(float(np.max(region)), 2),
        "avg_temp": round(float(np.mean(region)), 2),
    }


def compute_delta_t(
    temp_matrix: np.ndarray,
    bbox: list[int],
) -> dict:
    """Compute delta_T = max bbox temp minus median frame temp.

    The median of the whole frame approximates the healthy-panel background.
    Returns all bbox_temps fields plus delta_t_measured and reference_temp.
    """
    bbox_temps = extract_bbox_temps(temp_matrix, bbox)
    if bbox_temps["max_temp"] is None:
        return {**bbox_temps, "delta_t_measured": None, "reference_temp": None}
    reference_temp = round(float(np.median(temp_matrix)), 2)
    return {
        **bbox_temps,
        "reference_temp": reference_temp,
        "delta_t_measured": round(bbox_temps["max_temp"] - reference_temp, 2),
    }


def normalize_delta_t(delta_t: float, irradiance_wm2: float) -> float | None:
    """Normalise delta_T to 1000 W/m² per IEC 62446-3 Annex C.

    Formula: ΔT_norm = ΔT_measured × (1000 / G)
    """
    if irradiance_wm2 and irradiance_wm2 > 0:
        return round(delta_t * (1000.0 / irradiance_wm2), 2)
    return None


def find_temp_companion(image_path: Path) -> Path | None:
    """Return the _temp.raw companion for a thermal image, or None if absent."""
    candidate = image_path.with_name(image_path.stem + "_temp.raw")
    return candidate if candidate.exists() else None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/backend/test_temp_extractor.py -v
```
Expected: `10 passed`

- [ ] **Step 5: Commit**

```bash
git add platform/core/temp_extractor.py tests/backend/test_temp_extractor.py
git commit -m "feat(temp): add RAW16 temperature extractor for iTL612R Pro"
```

---

## Task 2: Wire Temperature into Ingest Pipeline

**Files:**
- Modify: `platform/pipeline/ingest.py`
- Modify: `platform/pipeline/orchestrator.py:90-187`

### What changes
`find_image_pairs` adds a `temp_raw` key to each pair dict. `inspect_pair` accepts `temp_raw_path` and `irradiance_wm2`, loads the matrix once, and enriches every detection with `delta_t_measured`, `delta_t_normalized`, `min_temp`, `max_temp`. `inspect_folder` passes `irradiance_wm2` from `site_meta` through.

- [ ] **Step 1: Write the failing test**

```python
# Add to tests/backend/test_temp_extractor.py

import numpy as np
from pathlib import Path
from platform.pipeline.ingest import find_image_pairs


def test_find_image_pairs_includes_temp_raw(tmp_path):
    thermal_dir = tmp_path / "thermal"
    thermal_dir.mkdir()
    img = thermal_dir / "img_001.jpg"
    # Write minimal valid JPEG (1x1 white pixel)
    import cv2
    cv2.imwrite(str(img), np.ones((1, 1, 3), dtype=np.uint8) * 255)
    raw = thermal_dir / "img_001_temp.raw"
    raw.write_bytes(b"\x00" * (640 * 512 * 2))

    pairs = find_image_pairs(tmp_path)
    assert len(pairs) == 1
    assert pairs[0]["temp_raw"] == raw


def test_find_image_pairs_temp_raw_none_when_absent(tmp_path):
    thermal_dir = tmp_path / "thermal"
    thermal_dir.mkdir()
    import cv2
    cv2.imwrite(str(thermal_dir / "img_001.jpg"), np.ones((1, 1, 3), dtype=np.uint8) * 255)

    pairs = find_image_pairs(tmp_path)
    assert pairs[0]["temp_raw"] is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/backend/test_temp_extractor.py::test_find_image_pairs_includes_temp_raw -v
```
Expected: `AssertionError` — `temp_raw` key missing from pair dict

- [ ] **Step 3: Update find_image_pairs in ingest.py**

In `platform/pipeline/ingest.py`, add the import at the top and update the pair dict inside `find_image_pairs`:

```python
# Add at top of file, after existing imports:
from axalon.core.temp_extractor import find_temp_companion
```

Replace the `pairs.append({...})` block (lines 71-78) with:

```python
        pairs.append({
            "id": thermal_path.stem,
            "thermal": thermal_path,
            "rgb": rgb_path,
            "temp_raw": find_temp_companion(thermal_path),
            "thermal_gps": extract_gps_exif(thermal_path),
            "rgb_gps": extract_gps_exif(rgb_path) if rgb_path else None,
            "thermal_size": (w, h),
        })
```

- [ ] **Step 4: Update inspect_pair in orchestrator.py**

Add the import after existing imports at the top of `platform/pipeline/orchestrator.py`:

```python
from axalon.core.temp_extractor import load_temp_matrix, compute_delta_t, normalize_delta_t
```

Change `inspect_pair` signature (line 90):

```python
    def inspect_pair(
        self,
        thermal_path: str | Path,
        rgb_path: str | Path | None = None,
        park_id: str = "unknown",
        altitude_m: float = 20.0,
        panel_map: dict | None = None,
        inspection_id: str | None = None,
        temp_raw_path: str | Path | None = None,
        irradiance_wm2: float | None = None,
    ) -> dict:
```

Add temperature enrichment block immediately after the GPS enrichment block (after line 120 `det["gps"] = detection_to_gps(...)`):

```python
        # Temperature enrichment — requires _temp.raw companion from iTL612R Pro
        if temp_raw_path is not None:
            try:
                temp_matrix = load_temp_matrix(temp_raw_path)
                for det in detections:
                    temps = compute_delta_t(temp_matrix, det["bbox"])
                    det["min_temp"] = temps["min_temp"]
                    det["max_temp"] = temps["max_temp"]
                    det["avg_temp"] = temps["avg_temp"]
                    det["delta_t_measured"] = temps["delta_t_measured"]
                    det["irradiance_wm2"] = irradiance_wm2
                    if temps["delta_t_measured"] is not None and irradiance_wm2:
                        det["delta_t_normalized"] = normalize_delta_t(
                            temps["delta_t_measured"], irradiance_wm2
                        )
            except Exception:
                logger.warning("Temperature extraction failed for %s", thermal_path.name)
```

- [ ] **Step 5: Pass temp_raw and irradiance through inspect_folder**

In `inspect_folder`, change the signature (line 189):

```python
    def inspect_folder(
        self,
        folder: str | Path,
        park_id: str = "unknown",
        altitude_m: float = 20.0,
        progress_callback=None,
        site_meta: dict | None = None,
    ) -> dict:
```

Add this line after `mission_meta = load_mission_metadata(folder)`:

```python
        site_meta = site_meta or {}
        irradiance_wm2 = site_meta.get("irradiance_wm2")
        try:
            irradiance_wm2 = float(irradiance_wm2) if irradiance_wm2 else None
        except (TypeError, ValueError):
            irradiance_wm2 = None
```

Update the `self.inspect_pair(...)` call (inside the Phase 2 loop) to pass the new params:

```python
            result = self.inspect_pair(
                thermal_path=pair["thermal"],
                rgb_path=pair.get("rgb"),
                park_id=park_id,
                altitude_m=mission_meta.get("altitude_m", altitude_m),
                panel_map=panel_map,
                inspection_id=batch_id,
                temp_raw_path=pair.get("temp_raw"),
                irradiance_wm2=irradiance_wm2,
            )
```

- [ ] **Step 6: Run tests to verify they pass**

```bash
python -m pytest tests/backend/test_temp_extractor.py -v
```
Expected: `12 passed`

- [ ] **Step 7: Smoke test — confirm pipeline imports cleanly**

```bash
python -c "from platform.pipeline.orchestrator import InspectionOrchestrator; print('OK')"
```
Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add platform/pipeline/ingest.py platform/pipeline/orchestrator.py
git commit -m "feat(temp): wire RAW16 temperature into ingest pipeline and inspect_pair"
```

---

## Task 3: DB Model Changes + Alembic Migrations

**Files:**
- Modify: `platform/db/models.py`
- Create: `alembic/versions/0002_inspection_metadata.py`
- Create: `alembic/versions/0003_fault_comments.py`

### What changes
`Inspection` gets 8 new nullable columns for site metadata. A new `FaultComment` model replaces the overloaded `notes` text field for multi-actor comment threads.

- [ ] **Step 1: Write the failing test**

```python
# Add to tests/backend/test_job_persistence.py (already exists — append these)

from platform.db.models import Inspection, FaultComment


def test_inspection_has_metadata_columns(db_session):
    insp = Inspection(
        id="TEST-META-01",
        park_id="PARK_01",
        flight_date="2026-06-01",
        client="Tata Solar",
        location="Rajasthan, India",
        capacity_mw=5.0,
        inspection_type="commissioning",
        inspection_level="standard",
        irradiance_wm2=850.0,
        wind_speed_bft=2.0,
        cloud_coverage_okta=1.0,
    )
    db_session.add(insp)
    db_session.commit()
    fetched = db_session.query(Inspection).filter_by(id="TEST-META-01").first()
    assert fetched.client == "Tata Solar"
    assert fetched.inspection_type == "commissioning"
    assert fetched.irradiance_wm2 == 850.0


def test_fault_comment_create_and_list(db_session):
    from platform.db.models import Park, PanelFault, FAULT_OPEN
    park = Park(id="PARK_COMMENT", name="Comment Park")
    db_session.add(park)
    db_session.flush()
    fault = PanelFault(
        park_id="PARK_COMMENT",
        panel_id="R1-C1",
        class_="cell",
        class_id=0,
        severity="MEDIUM",
        status=FAULT_OPEN,
    )
    db_session.add(fault)
    db_session.flush()
    c1 = FaultComment(fault_id=fault.id, author="pilot", body="Anomaly detected")
    c2 = FaultComment(fault_id=fault.id, author="ground_crew", body="Physically confirmed")
    db_session.add_all([c1, c2])
    db_session.commit()
    comments = db_session.query(FaultComment).filter_by(fault_id=fault.id).all()
    assert len(comments) == 2
    assert comments[0].author == "pilot"
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/backend/test_job_persistence.py::test_inspection_has_metadata_columns -v
```
Expected: `sqlalchemy.exc.InvalidRequestError` or `AttributeError` — columns don't exist yet

- [ ] **Step 3: Update models.py**

Replace the `Inspection` class in `platform/db/models.py`:

```python
class Inspection(Base):
    __tablename__ = "inspections"
    id = Column(String, primary_key=True)
    park_id = Column(String, ForeignKey("parks.id"), nullable=False)
    flight_date = Column(String, nullable=True)
    total_images = Column(Integer, default=0)
    total_detections = Column(Integer, default=0)
    summary = Column(Text, nullable=True)
    # Site metadata — written at job creation from API form params
    client = Column(String, nullable=True)
    location = Column(String, nullable=True)
    capacity_mw = Column(Float, nullable=True)
    inspection_type = Column(String, default="maintenance")  # commissioning | maintenance | rapid
    inspection_level = Column(String, default="simplified")  # simplified | standard | detailed
    irradiance_wm2 = Column(Float, nullable=True)
    wind_speed_bft = Column(Float, nullable=True)
    cloud_coverage_okta = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
```

Add the `FaultComment` class after the `Correction` class:

```python
class FaultComment(Base):
    """Append-only comment thread on a PanelFault — supports multi-actor workflow.

    Actors: drone pilot (initial annotation), ground crew (field verification),
    maintenance team (repair confirmation).
    """
    __tablename__ = "fault_comments"
    id = Column(Integer, primary_key=True, autoincrement=True)
    fault_id = Column(Integer, ForeignKey("panel_faults.id"), nullable=False, index=True)
    author = Column(String(128), nullable=True)
    body = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
```

- [ ] **Step 4: Create Alembic migration for inspection metadata**

```bash
cd /home/parakh/Desktop/AxalonSystems
alembic revision --rev-id 0002 -m "inspection_metadata"
```

Open the generated file in `alembic/versions/0002_inspection_metadata.py` and fill in `upgrade` and `downgrade`:

```python
"""inspection_metadata

Revision ID: 0002
"""
from alembic import op
import sqlalchemy as sa

revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('inspections', sa.Column('client', sa.String(), nullable=True))
    op.add_column('inspections', sa.Column('location', sa.String(), nullable=True))
    op.add_column('inspections', sa.Column('capacity_mw', sa.Float(), nullable=True))
    op.add_column('inspections', sa.Column('inspection_type', sa.String(), nullable=True))
    op.add_column('inspections', sa.Column('inspection_level', sa.String(), nullable=True))
    op.add_column('inspections', sa.Column('irradiance_wm2', sa.Float(), nullable=True))
    op.add_column('inspections', sa.Column('wind_speed_bft', sa.Float(), nullable=True))
    op.add_column('inspections', sa.Column('cloud_coverage_okta', sa.Float(), nullable=True))


def downgrade():
    for col in ['cloud_coverage_okta', 'wind_speed_bft', 'irradiance_wm2',
                'inspection_level', 'inspection_type', 'capacity_mw', 'location', 'client']:
        op.drop_column('inspections', col)
```

- [ ] **Step 5: Create Alembic migration for fault_comments**

```bash
alembic revision --rev-id 0003 -m "fault_comments"
```

Fill in `alembic/versions/0003_fault_comments.py`:

```python
"""fault_comments

Revision ID: 0003
"""
from alembic import op
import sqlalchemy as sa

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'fault_comments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('fault_id', sa.Integer(), sa.ForeignKey('panel_faults.id'), nullable=False),
        sa.Column('author', sa.String(128), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_fault_comments_fault_id', 'fault_comments', ['fault_id'])


def downgrade():
    op.drop_index('ix_fault_comments_fault_id', 'fault_comments')
    op.drop_table('fault_comments')
```

- [ ] **Step 6: Check down_revision is correct**

```bash
alembic history
```

The `down_revision` in `0002` must match the ID of the previous migration in the chain. If it's different, update `down_revision` in both files to match. The chain must be linear: `0001 → 0002 → 0003`.

- [ ] **Step 7: Run the migration to verify it applies cleanly**

```bash
alembic upgrade head
```
Expected: no errors, `INFO  [alembic.runtime.migration] Running upgrade ... -> 0003`

- [ ] **Step 8: Run the tests**

```bash
python -m pytest tests/backend/test_job_persistence.py -v
```
Expected: all tests pass including the two new ones

- [ ] **Step 9: Commit**

```bash
git add platform/db/models.py alembic/versions/0002_inspection_metadata.py alembic/versions/0003_fault_comments.py
git commit -m "feat(db): add inspection metadata columns and fault_comments table"
```

---

## Task 4: Persist Site Metadata from API to DB

**Files:**
- Modify: `platform/api/app.py`
- Modify: `platform/pipeline/orchestrator.py`

### What changes
`/inspect` and `/batch` gain `inspection_type` and `inspection_level` form params. `_run_batch_job` passes `site_meta` to `inspect_folder`. The `Inspection` record created inside `inspect_folder` is populated with site metadata columns. The `/inspect` endpoint also writes metadata to the Job's associated Inspection record.

- [ ] **Step 1: Write the failing test**

```python
# Add to tests/backend/test_api_contract.py

def test_batch_inspection_type_stored(client, sample_zip):
    resp = client.post("/batch", data={
        "park_id": "PARK_META",
        "inspection_type": "commissioning",
        "inspection_level": "standard",
        "irradiance_wm2": "875",
        "client": "Acme Solar",
    }, files={"images": ("batch.zip", sample_zip, "application/zip")})
    assert resp.status_code == 202
    # After job completes, check park summary includes inspection with type
    import time
    job_id = resp.json()["job_id"]
    for _ in range(30):
        status = client.get(f"/status/{job_id}").json()
        if status["status"] == "completed":
            break
        time.sleep(0.5)
    park_resp = client.get("/park/PARK_META").json()
    insp = park_resp["inspections"][0]
    assert insp["inspection_type"] == "commissioning"
    assert insp["irradiance_wm2"] == 875.0
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/backend/test_api_contract.py::test_batch_inspection_type_stored -v
```
Expected: `KeyError: 'inspection_type'` in the park response

- [ ] **Step 3: Add form params to /inspect and /batch in app.py**

In the `inspect_pair` endpoint function (around line 322), add two new `Form` params after `drone_model`:

```python
    inspection_type: str = Form("maintenance"),
    inspection_level: str = Form("simplified"),
```

Do the same in the `inspect_batch` endpoint (around line 423).

Update `site_meta` dict in both endpoints to include the new fields:

```python
    site_meta = {
        "site_name":        site_name or park_id,
        "client":           client,
        "location":         location,
        "capacity_mw":      capacity_mw,
        "lat":              lat,
        "lon":              lon,
        "irradiance_wm2":   irradiance_wm2,
        "inspection_time":  inspection_time,
        "drone_model":      drone_model,
        "inspection_type":  inspection_type,
        "inspection_level": inspection_level,
    }
```

- [ ] **Step 4: Pass site_meta to _run_batch_job and inspect_folder**

In `_run_batch_job` (around line 556), the call to `orch.inspect_folder` already passes `site_meta`. Confirm the signature now accepts it (done in Task 2). If not yet updated, change:

```python
        result = orch.inspect_folder(
            folder=mission_root, park_id=park_id,
            altitude_m=altitude_m, progress_callback=progress_cb,
            site_meta=site_meta,
        )
```

- [ ] **Step 5: Write site_meta to Inspection record in orchestrator.py**

Inside `inspect_folder`, find where the `Inspection` record is created (around line 241). Replace:

```python
            insp = Inspection(
                id=batch_id,
                park_id=park_id,
                flight_date=flight_date,
                total_images=total,
                total_detections=0,
                summary="{}",
            )
```

With:

```python
            def _safe_float(val):
                try:
                    return float(val) if val not in (None, "") else None
                except (TypeError, ValueError):
                    return None

            insp = Inspection(
                id=batch_id,
                park_id=park_id,
                flight_date=flight_date,
                total_images=total,
                total_detections=0,
                summary="{}",
                client=site_meta.get("client") or None,
                location=site_meta.get("location") or None,
                capacity_mw=_safe_float(site_meta.get("capacity_mw")),
                inspection_type=site_meta.get("inspection_type", "maintenance"),
                inspection_level=site_meta.get("inspection_level", "simplified"),
                irradiance_wm2=_safe_float(site_meta.get("irradiance_wm2")),
                wind_speed_bft=_safe_float(site_meta.get("wind_speed_bft")),
                cloud_coverage_okta=_safe_float(site_meta.get("cloud_coverage_okta")),
            )
```

- [ ] **Step 6: Expose new columns in /park/{park_id} response**

In `get_park_summary` (around line 1178), update the inspection serialization to include new fields:

```python
                {
                    "id": insp.id,
                    "flight_date": insp.flight_date,
                    "total_images": insp.total_images,
                    "total_detections": insp.total_detections,
                    "summary": json.loads(insp.summary) if insp.summary else {},
                    "inspection_type": insp.inspection_type,
                    "inspection_level": insp.inspection_level,
                    "client": insp.client,
                    "location": insp.location,
                    "capacity_mw": insp.capacity_mw,
                    "irradiance_wm2": insp.irradiance_wm2,
                    "wind_speed_bft": insp.wind_speed_bft,
                    "cloud_coverage_okta": insp.cloud_coverage_okta,
                }
```

- [ ] **Step 7: Update altitude default in both endpoints**

In `/inspect` (line ~329) and `/batch` (line ~430), change:

```python
    altitude_m: float = Form(40.0),
```
to:
```python
    altitude_m: float = Form(20.0),
```

- [ ] **Step 8: Run tests**

```bash
python -m pytest tests/backend/test_api_contract.py -v
```
Expected: all pass

- [ ] **Step 9: Commit**

```bash
git add platform/api/app.py platform/pipeline/orchestrator.py
git commit -m "feat(api): persist inspection_type/metadata to DB, update altitude default to 20m"
```

---

## Task 5: IEC Irradiance Compliance Warning

**Files:**
- Modify: `platform/api/app.py`

### What changes
If `irradiance_wm2` is submitted and is below 600 W/m² (IEC 62446-3 minimum), the response includes a `warnings` list. This is a non-blocking warning — the job still runs.

- [ ] **Step 1: Write the failing test**

```python
# Add to tests/backend/test_api_contract.py

def test_inspect_warns_on_low_irradiance(client, sample_thermal_image):
    resp = client.post("/inspect", data={
        "park_id": "PARK_IEC",
        "irradiance_wm2": "450",
    }, files={"thermal_image": ("t.jpg", sample_thermal_image, "image/jpeg")})
    assert resp.status_code == 200
    body = resp.json()
    assert "warnings" in body
    assert any("600" in w for w in body["warnings"])


def test_inspect_no_warning_on_sufficient_irradiance(client, sample_thermal_image):
    resp = client.post("/inspect", data={
        "park_id": "PARK_IEC2",
        "irradiance_wm2": "850",
    }, files={"thermal_image": ("t.jpg", sample_thermal_image, "image/jpeg")})
    assert resp.status_code == 200
    assert resp.json().get("warnings", []) == []


def test_inspect_no_warning_when_irradiance_omitted(client, sample_thermal_image):
    resp = client.post("/inspect", data={"park_id": "PARK_IEC3"},
                       files={"thermal_image": ("t.jpg", sample_thermal_image, "image/jpeg")})
    assert resp.status_code == 200
    assert resp.json().get("warnings", []) == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/backend/test_api_contract.py::test_inspect_warns_on_low_irradiance -v
```
Expected: `AssertionError` — `warnings` key absent from response

- [ ] **Step 3: Add _check_iec_warnings helper in app.py**

Add this function near the other helper functions (after `_validate_job_id`):

```python
def _check_iec_warnings(site_meta: dict) -> list[str]:
    """Return IEC compliance warnings for the given site metadata."""
    warnings = []
    try:
        irr = float(site_meta.get("irradiance_wm2") or 0)
        if 0 < irr < 600:
            warnings.append(
                f"Irradiance {irr:.0f} W/m² is below the IEC 62446-3 "
                "minimum of 600 W/m². Results may not meet standard requirements."
            )
    except (TypeError, ValueError):
        pass
    return warnings
```

- [ ] **Step 4: Add warnings to /inspect response**

In the `inspect_pair` endpoint, find the `return JSONResponse(content={...})` block and add `"warnings"`:

```python
    return JSONResponse(content={
        "job_id": result["job_id"],
        "status": "completed",
        "total_detections": result["total_detections"],
        "summary": result["summary"],
        "detections": result["detections"],
        "rgb_filename": Path(result.get("annotated_rgb") or "").name,
        "warnings": _check_iec_warnings(site_meta),
    })
```

- [ ] **Step 5: Add warnings to /batch response**

In the `inspect_batch` endpoint, find the `return {...}` dict and add:

```python
    return {
        "job_id": job_id,
        "state": "queued",
        "status": "queued",
        "message": "Batch job queued. Poll GET /status/{job_id} for progress.",
        "warnings": _check_iec_warnings(site_meta),
    }
```

- [ ] **Step 6: Run tests**

```bash
python -m pytest tests/backend/test_api_contract.py -k "irradiance" -v
```
Expected: `3 passed`

- [ ] **Step 7: Commit**

```bash
git add platform/api/app.py
git commit -m "feat(api): add IEC 62446-3 irradiance compliance warning on job submission"
```

---

## Task 6: Revenue Loss Estimation in Reports

**Files:**
- Modify: `platform/config/settings.yaml`
- Modify: `platform/reporting/report.py`

### What changes
Add an `economics` section to `settings.yaml`. The Excel and PDF reports compute `estimated_daily_loss_usd` per fault: `affected_panels × panel_capacity_kw × peak_sun_hours × cost_per_kwh` for CRITICAL and HIGH severity faults. A summary row in Excel and a summary line in the PDF footer show total estimated daily revenue at risk.

- [ ] **Step 1: Write the failing test**

```python
# Add to tests/backend/test_corrections_in_report.py (already exists)

from platform.reporting.report import compute_revenue_loss


def test_compute_revenue_loss_critical_faults():
    detections = [
        {"panel_id": "R1-C1", "severity": "CRITICAL"},
        {"panel_id": "R1-C2", "severity": "CRITICAL"},
        {"panel_id": "R2-C1", "severity": "HIGH"},
        {"panel_id": "R3-C1", "severity": "LOW"},   # excluded
        {"panel_id": "R?-C?", "severity": "CRITICAL"},  # unknown panel excluded
    ]
    economics = {"cost_per_kwh_usd": 0.08, "panel_capacity_kw": 0.4, "peak_sun_hours_per_day": 5.0}
    # 3 affected known panels (R1-C1, R1-C2, R2-C1)
    # 3 × 0.4 × 5.0 × 0.08 = 0.48
    result = compute_revenue_loss(detections, economics)
    assert result == pytest.approx(0.48)


def test_compute_revenue_loss_no_critical():
    detections = [{"panel_id": "R1-C1", "severity": "LOW"}]
    economics = {"cost_per_kwh_usd": 0.08, "panel_capacity_kw": 0.4, "peak_sun_hours_per_day": 5.0}
    assert compute_revenue_loss(detections, economics) == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/backend/test_corrections_in_report.py::test_compute_revenue_loss_critical_faults -v
```
Expected: `ImportError: cannot import name 'compute_revenue_loss'`

- [ ] **Step 3: Add economics to settings.yaml**

```yaml
economics:
  cost_per_kwh_usd: 0.08        # adjust per site/region
  panel_capacity_kw: 0.4        # typical 400W panel
  peak_sun_hours_per_day: 5.0   # adjust per location
```

- [ ] **Step 4: Add compute_revenue_loss to report.py**

Add this function near the top of `platform/reporting/report.py` (after the display-name helpers):

```python
def compute_revenue_loss(detections: list[dict], economics: dict) -> float:
    """Estimate daily revenue loss (USD) from CRITICAL and HIGH faults.

    Counts unique known panels (excludes R?-C?) with CRITICAL or HIGH severity.
    Formula: affected_panels × panel_capacity_kw × peak_sun_hours × cost_per_kwh
    """
    cost = float(economics.get("cost_per_kwh_usd", 0.08))
    capacity = float(economics.get("panel_capacity_kw", 0.4))
    hours = float(economics.get("peak_sun_hours_per_day", 5.0))
    affected = {
        d["panel_id"] for d in detections
        if d.get("severity") in ("CRITICAL", "HIGH")
        and d.get("panel_id") not in (None, "R?-C?")
    }
    return round(len(affected) * capacity * hours * cost, 2)
```

- [ ] **Step 5: Wire revenue loss into generate_excel_report**

In `generate_excel_report`, load economics from `site_meta` and add a revenue loss row after the Grand Total row in the Summary sheet:

```python
    # After the Grand Total row (around line 184):
    economics = {
        "cost_per_kwh_usd": site_meta.get("cost_per_kwh_usd", 0.08),
        "panel_capacity_kw": site_meta.get("panel_capacity_kw", 0.4),
        "peak_sun_hours_per_day": site_meta.get("peak_sun_hours_per_day", 5.0),
    }
    rev_loss = compute_revenue_loss(all_dets, economics)
    rev_row = total_row + 1
    ws_sum.cell(row=rev_row, column=1, value="Est. Daily Revenue at Risk (USD)").font = hdr_font
    ws_sum.cell(row=rev_row, column=2, value=f"${rev_loss:.2f}").font = hdr_font
```

- [ ] **Step 6: Wire revenue loss into generate_pdf_report**

In `generate_pdf_report`, add to the `context` dict:

```python
        "economics": {
            "cost_per_kwh_usd": site_meta.get("cost_per_kwh_usd", 0.08),
            "panel_capacity_kw": site_meta.get("panel_capacity_kw", 0.4),
            "peak_sun_hours_per_day": site_meta.get("peak_sun_hours_per_day", 5.0),
        },
        "revenue_loss_usd": compute_revenue_loss(all_detections, {
            "cost_per_kwh_usd": site_meta.get("cost_per_kwh_usd", 0.08),
            "panel_capacity_kw": site_meta.get("panel_capacity_kw", 0.4),
            "peak_sun_hours_per_day": site_meta.get("peak_sun_hours_per_day", 5.0),
        }),
```

In `platform/reporting/templates/report.html`, find the fault summary section and add after the CoA counts table:

```html
<p style="margin-top:12px; font-size:11px; color:#dc2626; font-weight:600;">
  Estimated daily revenue at risk (CRITICAL + HIGH faults):
  <strong>${{ "%.2f"|format(revenue_loss_usd) }} USD</strong>
  <span style="font-weight:400; color:#666;">({{ economics.panel_capacity_kw }}kW panels,
  {{ economics.peak_sun_hours_per_day }}h/day peak sun,
  ${{ economics.cost_per_kwh_usd }}/kWh)</span>
</p>
```

- [ ] **Step 7: Run tests**

```bash
python -m pytest tests/backend/test_corrections_in_report.py -v
```
Expected: all pass

- [ ] **Step 8: Commit**

```bash
git add platform/config/settings.yaml platform/reporting/report.py platform/reporting/templates/report.html
git commit -m "feat(report): add revenue loss estimation for CRITICAL/HIGH faults"
```

---

## Task 7: Fault Comment API Endpoints

**Files:**
- Modify: `platform/api/app.py`
- Modify: `platform/db/models.py` (import FaultComment in app.py)
- Create: `tests/backend/test_fault_comments.py`

### What changes
Two new endpoints: `POST /faults/{fault_id}/comments` to append a comment, `GET /faults/{fault_id}/comments` to list all comments in chronological order. The existing `GET /parks/{park_id}/faults` response adds a `comment_count` field per fault.

- [ ] **Step 1: Write the failing tests**

```python
# tests/backend/test_fault_comments.py
import pytest
from fastapi.testclient import TestClient
from platform.api.app import app
from platform.db.session import get_session
from platform.db.models import Park, Inspection, Detection as DbDetection, PanelFault, FAULT_OPEN


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def existing_fault(db_session):
    park = Park(id="PARK_CMT", name="Comment Park")
    db_session.add(park)
    db_session.flush()
    fault = PanelFault(
        park_id="PARK_CMT",
        panel_id="R1-C1",
        class_="bypass-diode",
        class_id=4,
        severity="CRITICAL",
        status=FAULT_OPEN,
    )
    db_session.add(fault)
    db_session.commit()
    return fault.id


def test_create_comment(client, existing_fault):
    resp = client.post(f"/faults/{existing_fault}/comments", json={
        "author": "pilot",
        "body": "Bypass diode failure confirmed from thermal image",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["fault_id"] == existing_fault
    assert data["author"] == "pilot"
    assert data["body"] == "Bypass diode failure confirmed from thermal image"
    assert "id" in data
    assert "created_at" in data


def test_create_comment_requires_body(client, existing_fault):
    resp = client.post(f"/faults/{existing_fault}/comments", json={"author": "pilot"})
    assert resp.status_code == 400


def test_create_comment_invalid_fault(client):
    resp = client.post("/faults/99999/comments", json={"body": "test"})
    assert resp.status_code == 404


def test_list_comments_chronological(client, existing_fault):
    for body in ["First note", "Second note", "Third note"]:
        client.post(f"/faults/{existing_fault}/comments", json={"body": body})
    resp = client.get(f"/faults/{existing_fault}/comments")
    assert resp.status_code == 200
    comments = resp.json()
    assert len(comments) == 3
    assert comments[0]["body"] == "First note"
    assert comments[2]["body"] == "Third note"


def test_list_comments_empty(client, existing_fault):
    resp = client.get(f"/faults/{existing_fault}/comments")
    assert resp.status_code == 200
    assert resp.json() == []


def test_fault_list_includes_comment_count(client, existing_fault):
    client.post(f"/faults/{existing_fault}/comments", json={"body": "note 1"})
    client.post(f"/faults/{existing_fault}/comments", json={"body": "note 2"})
    resp = client.get("/parks/PARK_CMT/faults")
    assert resp.status_code == 200
    fault = resp.json()["faults"][0]
    assert fault["comment_count"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/backend/test_fault_comments.py -v 2>&1 | head -30
```
Expected: `404 Not Found` — endpoints don't exist yet

- [ ] **Step 3: Add FaultComment import to app.py**

In `platform/api/app.py`, find the models import line and add `FaultComment`:

```python
from axalon.db.models import (
    Park, Inspection, PanelFault, Detection as DbDetection,
    FAULT_OPEN, FAULT_STALE, FAULT_RESOLVED, Correction, Job as DbJob, FaultComment
)
```

- [ ] **Step 4: Add comment serializer helper in app.py**

Add after `_serialize_fault`:

```python
def _serialize_comment(c: FaultComment) -> dict:
    return {
        "id": c.id,
        "fault_id": c.fault_id,
        "author": c.author,
        "body": c.body,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }
```

- [ ] **Step 5: Add comment_count to _serialize_fault**

Update `_serialize_fault` to accept an optional `comment_count` arg:

```python
def _serialize_fault(f: PanelFault, comment_count: int = 0) -> dict:
    return {
        "id": f.id,
        "park_id": f.park_id,
        "panel_id": f.panel_id,
        "class": f.class_,
        "class_id": f.class_id,
        "severity": f.severity,
        "status": f.status,
        "occurrences": f.occurrences,
        "max_confidence": f.max_confidence,
        "first_seen_inspection_id": f.first_seen_inspection_id,
        "last_seen_inspection_id": f.last_seen_inspection_id,
        "first_seen_date": f.first_seen_date,
        "last_seen_date": f.last_seen_date,
        "last_bbox": json.loads(f.last_bbox) if f.last_bbox else None,
        "last_gps": json.loads(f.last_gps) if f.last_gps else None,
        "notes": f.notes,
        "comment_count": comment_count,
    }
```

- [ ] **Step 6: Update list_park_faults to include comment counts**

Replace the return statement in `list_park_faults`:

```python
        from sqlalchemy import func
        # Get comment counts per fault in one query
        comment_counts = dict(
            session.query(FaultComment.fault_id, func.count(FaultComment.id))
            .filter(FaultComment.fault_id.in_([f.id for f in faults]))
            .group_by(FaultComment.fault_id)
            .all()
        )
        return {
            "park_id": park_id,
            "total": len(faults),
            "counts_by_status": counts,
            "faults": [_serialize_fault(f, comment_counts.get(f.id, 0)) for f in faults],
        }
```

- [ ] **Step 7: Add the two comment endpoints to app.py**

Add after the `update_fault` endpoint (after line ~1733):

```python
@app.post("/faults/{fault_id}/comments", status_code=201)
def create_fault_comment(fault_id: int, body: dict):
    """Append a comment to a fault's thread."""
    if fault_id <= 0:
        raise HTTPException(status_code=400, detail="fault_id must be positive")
    comment_body = str(body.get("body", "")).strip()
    if not comment_body:
        raise HTTPException(status_code=400, detail="body is required")
    author = str(body.get("author", ""))[:128] if body.get("author") else None
    session = get_session()
    try:
        fault = session.query(PanelFault).filter_by(id=fault_id).first()
        if fault is None:
            raise HTTPException(status_code=404, detail="Fault not found")
        comment = FaultComment(
            fault_id=fault_id,
            author=author,
            body=comment_body[:4000],
        )
        session.add(comment)
        session.commit()
        session.refresh(comment)
        return JSONResponse(content=_serialize_comment(comment), status_code=201)
    finally:
        session.close()


@app.get("/faults/{fault_id}/comments")
def list_fault_comments(fault_id: int):
    """List all comments on a fault in chronological order."""
    if fault_id <= 0:
        raise HTTPException(status_code=400, detail="fault_id must be positive")
    session = get_session()
    try:
        comments = (
            session.query(FaultComment)
            .filter(FaultComment.fault_id == fault_id)
            .order_by(FaultComment.created_at.asc(), FaultComment.id.asc())
            .all()
        )
        return [_serialize_comment(c) for c in comments]
    finally:
        session.close()
```

- [ ] **Step 8: Run all tests**

```bash
python -m pytest tests/backend/test_fault_comments.py tests/backend/test_api_contract.py -v
```
Expected: all pass

- [ ] **Step 9: Commit**

```bash
git add platform/api/app.py tests/backend/test_fault_comments.py
git commit -m "feat(api): add fault comment thread endpoints (POST/GET /faults/{id}/comments)"
```

---

## Task 8: Full Test Suite + Final Verification

- [ ] **Step 1: Run full backend test suite**

```bash
cd /home/parakh/Desktop/AxalonSystems
python -m pytest tests/ -v --tb=short 2>&1 | tail -30
```
Expected: all tests pass, no regressions

- [ ] **Step 2: Verify API starts cleanly**

```bash
uvicorn platform.api.app:app --host 0.0.0.0 --port 8000 &
sleep 3
curl -s http://localhost:8000/health | python -m json.tool
kill %1
```
Expected output includes:
```json
{
  "status": "ok",
  "model": "YOLO11m",
  "db": "ok"
}
```

- [ ] **Step 3: Verify Alembic is at head**

```bash
alembic current
```
Expected: `0003 (head)`

- [ ] **Step 4: Verify settings.yaml is coherent**

```bash
python -c "
import yaml
with open('platform/config/settings.yaml') as f:
    s = yaml.safe_load(f)
assert s['drone']['default_altitude_m'] == 20
assert s['drone']['thermal_sensor_width_mm'] == 7.68
assert s['model']['weights'] == 'ml/checkpoints/best.pt'
assert 'economics' in s
print('settings.yaml OK')
"
```
Expected: `settings.yaml OK`

- [ ] **Step 5: Final commit**

```bash
git add -u
git commit -m "chore: final verification pass — all tests green, API starts cleanly"
```

---

---

## Task 9: Download and Prepare Training Datasets

**Files:**
- Create: `ml/data/combined/` — merged dataset root
- Modify: `ml/thermal_dataset.yaml` — point to combined dataset
- Create: `ml/scripts/prepare_dataset.py` — download + remap + merge script

### Background

Three dataset sources are combined:

| Dataset | Source | Notes |
|---|---|---|
| **InfraredSolarModules** (existing) | Already in repo | 24×40px module crops, 11 classes |
| **PV-Hawk** | GitHub: LukasBommes/PV-Hawk | Drone-captured thermal at altitude, needs class remapping |
| **Roboflow Solar Thermal** | roboflow.com/universe | Search "solar thermal defect", YOLO format available |

**Class remapping** is needed because PV-Hawk and Roboflow datasets use different label names. The canonical 11-class schema in `ml/src/utils.py` is the target.

PV-Hawk → canonical mapping:
```
"cell"           → "cell"          (ID 0)
"multi-cell"     → "cell-multi"    (ID 1)
"module"         → "module"        (ID 2)
"string"         → "string"        (ID 3)
"diode"          → "bypass-diode"  (ID 4)
"offline"        → "offline-module"(ID 5)
"vegetation"     → "vegetation-shading" (ID 6)
"soiling"        → "soiling"       (ID 7)
"short"          → "short-circuit" (ID 8)
"hotspot"        → "hot-spot-low"  (ID 9)  ← mild hotspots
"severe-hotspot" → "hot-spot-high" (ID 10) ← severe hotspots
```
Roboflow datasets vary — inspect labels and map manually using the same table. Any unmapped classes are dropped.

- [ ] **Step 1: Install roboflow SDK**

```bash
pip install roboflow
```

- [ ] **Step 2: Download PV-Hawk dataset**

```bash
git clone https://github.com/LukasBommes/PV-Hawk.git /tmp/pv-hawk
# Follow PV-Hawk README to download the dataset — requires Google Drive link
# The dataset downloads to /tmp/pv-hawk/data/
# Verify structure: /tmp/pv-hawk/data/images/ and /tmp/pv-hawk/data/labels/
ls /tmp/pv-hawk/data/
```

- [ ] **Step 3: Download Roboflow solar thermal dataset**

Sign up at roboflow.com, find the best-rated "solar panel thermal" dataset, and download:

```python
# Run this script once to download — save your API key securely
from roboflow import Roboflow
rf = Roboflow(api_key="YOUR_ROBOFLOW_API_KEY")
# Search roboflow.com/universe for "solar thermal" — use the dataset with most images
project = rf.workspace("YOUR_WORKSPACE").project("solar-panel-thermal-defect")
dataset = project.version(1).download("yolov8", location="ml/data/roboflow_solar")
```

Expected: `ml/data/roboflow_solar/train/`, `ml/data/roboflow_solar/valid/`, `ml/data/roboflow_solar/test/`

- [ ] **Step 4: Create the dataset preparation script**

```python
# ml/scripts/prepare_dataset.py
"""
Merge InfraredSolarModules + PV-Hawk + Roboflow into a single YOLO dataset.

Usage:
    python ml/scripts/prepare_dataset.py \
        --infrared  ml/Datasets/InfraredSolarModules \
        --pvhawk    /tmp/pv-hawk/data \
        --roboflow  ml/data/roboflow_solar \
        --out       ml/data/combined

Outputs:
    ml/data/combined/
        train/images/   train/labels/
        val/images/     val/labels/
        test/images/    test/labels/
"""
from __future__ import annotations

import argparse
import shutil
import random
from pathlib import Path

# Canonical class IDs from ml/src/utils.py
CLASS2ID = {
    "cell": 0, "cell-multi": 1, "module": 2, "string": 3,
    "bypass-diode": 4, "offline-module": 5, "vegetation-shading": 6,
    "soiling": 7, "short-circuit": 8, "hot-spot-low": 9, "hot-spot-high": 10,
}

# PV-Hawk label name → canonical name
PVHAWK_REMAP = {
    "cell": "cell", "multi-cell": "cell-multi", "module": "module",
    "string": "string", "diode": "bypass-diode", "offline": "offline-module",
    "vegetation": "vegetation-shading", "soiling": "soiling",
    "short": "short-circuit", "hotspot": "hot-spot-low",
    "severe-hotspot": "hot-spot-high",
}

# Roboflow label name → canonical name (UPDATE after inspecting the downloaded dataset)
ROBOFLOW_REMAP = {
    "cell": "cell", "cell_multi": "cell-multi", "module": "module",
    "string": "string", "bypass_diode": "bypass-diode",
    "offline_module": "offline-module", "vegetation": "vegetation-shading",
    "soiling": "soiling", "short_circuit": "short-circuit",
    "hot_spot_low": "hot-spot-low", "hot_spot_high": "hot-spot-high",
}


def remap_label_file(src: Path, dst: Path, remap: dict[str, str], src_names: list[str]) -> int:
    """Rewrite a YOLO .txt label file with remapped class IDs. Returns lines written."""
    lines = src.read_text().strip().split("\n") if src.stat().st_size > 0 else []
    out_lines = []
    for line in lines:
        if not line.strip():
            continue
        parts = line.split()
        old_id = int(parts[0])
        if old_id >= len(src_names):
            continue
        src_name = src_names[old_id]
        canonical = remap.get(src_name)
        if canonical is None or canonical not in CLASS2ID:
            continue  # drop unmapped classes
        new_id = CLASS2ID[canonical]
        out_lines.append(f"{new_id} {' '.join(parts[1:])}")
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("\n".join(out_lines))
    return len(out_lines)


def copy_split(
    img_dir: Path,
    lbl_dir: Path,
    out_root: Path,
    split: str,
    remap: dict[str, str],
    src_names: list[str],
    prefix: str,
) -> int:
    """Copy images and remapped labels into out_root/split/."""
    count = 0
    for img_path in sorted(img_dir.glob("*")):
        if img_path.suffix.lower() not in {".jpg", ".jpeg", ".png"}:
            continue
        lbl_path = lbl_dir / (img_path.stem + ".txt")
        if not lbl_path.exists():
            continue
        dst_img = out_root / split / "images" / f"{prefix}_{img_path.name}"
        dst_lbl = out_root / split / "labels" / f"{prefix}_{img_path.stem}.txt"
        dst_img.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(img_path, dst_img)
        written = remap_label_file(lbl_path, dst_lbl, remap, src_names)
        if written > 0:
            count += 1
    return count


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--infrared", required=True)
    parser.add_argument("--pvhawk", required=True)
    parser.add_argument("--roboflow", required=True)
    parser.add_argument("--out", default="ml/data/combined")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    # InfraredSolarModules — already uses canonical class IDs, identity remap
    infrared_names = list(CLASS2ID.keys())
    identity_remap = {n: n for n in infrared_names}
    for split in ("train", "val", "test"):
        img_dir = Path(args.infrared) / split / "images"
        lbl_dir = Path(args.infrared) / split / "labels"
        if img_dir.exists():
            n = copy_split(img_dir, lbl_dir, out, split, identity_remap, infrared_names, "ism")
            print(f"InfraredSolarModules {split}: {n} images")

    # PV-Hawk — read class names from data.yaml in the PV-Hawk repo
    pvhawk_yaml = Path(args.pvhawk) / "data.yaml"
    if pvhawk_yaml.exists():
        import yaml
        pvhawk_cfg = yaml.safe_load(pvhawk_yaml.read_text())
        pvhawk_names = pvhawk_cfg.get("names", list(PVHAWK_REMAP.keys()))
    else:
        pvhawk_names = list(PVHAWK_REMAP.keys())

    for split in ("train", "val", "test"):
        img_dir = Path(args.pvhawk) / split / "images"
        lbl_dir = Path(args.pvhawk) / split / "labels"
        if img_dir.exists():
            n = copy_split(img_dir, lbl_dir, out, split, PVHAWK_REMAP, pvhawk_names, "pvh")
            print(f"PV-Hawk {split}: {n} images")

    # Roboflow — read class names from data.yaml
    rf_yaml = Path(args.roboflow) / "data.yaml"
    if rf_yaml.exists():
        import yaml
        rf_cfg = yaml.safe_load(rf_yaml.read_text())
        rf_names = rf_cfg.get("names", list(ROBOFLOW_REMAP.keys()))
    else:
        rf_names = list(ROBOFLOW_REMAP.keys())

    for split_src, split_dst in [("train", "train"), ("valid", "val"), ("test", "test")]:
        img_dir = Path(args.roboflow) / split_src / "images"
        lbl_dir = Path(args.roboflow) / split_src / "labels"
        if img_dir.exists():
            n = copy_split(img_dir, lbl_dir, out, split_dst, ROBOFLOW_REMAP, rf_names, "rf")
            print(f"Roboflow {split_src}: {n} images")

    # Print dataset summary
    for split in ("train", "val", "test"):
        imgs = list((out / split / "images").glob("*")) if (out / split / "images").exists() else []
        print(f"Combined {split}: {len(imgs)} images")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run the preparation script**

```bash
cd /home/parakh/Desktop/AxalonSystems
python ml/scripts/prepare_dataset.py \
    --infrared ml/Datasets/InfraredSolarModules \
    --pvhawk   /tmp/pv-hawk/data \
    --roboflow ml/data/roboflow_solar \
    --out      ml/data/combined
```

Expected output (exact counts vary by downloaded datasets):
```
InfraredSolarModules train: XXXX images
PV-Hawk train: XXXX images
Roboflow train: XXXX images
Combined train: XXXX images
Combined val:   XXXX images
Combined test:  XXXX images
```

- [ ] **Step 6: Verify class distribution**

```python
# Run inline to check no class is severely underrepresented
from pathlib import Path
from collections import Counter

counts = Counter()
for lbl in (Path("ml/data/combined") / "train" / "labels").glob("*.txt"):
    for line in lbl.read_text().strip().split("\n"):
        if line.strip():
            counts[int(line.split()[0])] += 1

names = ["cell","cell-multi","module","string","bypass-diode","offline-module",
         "vegetation-shading","soiling","short-circuit","hot-spot-low","hot-spot-high"]
for i, name in enumerate(names):
    print(f"  {i:2d} {name:25s}: {counts.get(i, 0):6d}")
```

Any class with fewer than 200 instances in train may not train well — note which ones for evaluation.

- [ ] **Step 7: Update thermal_dataset.yaml**

```yaml
# ml/thermal_dataset.yaml
path: ml/data/combined
train: train/images
val:   val/images
test:  test/images
nc: 11
names:
  - cell
  - cell-multi
  - module
  - string
  - bypass-diode
  - offline-module
  - vegetation-shading
  - soiling
  - short-circuit
  - hot-spot-low
  - hot-spot-high
```

- [ ] **Step 8: Commit**

```bash
git add ml/scripts/prepare_dataset.py ml/thermal_dataset.yaml
git commit -m "feat(ml): dataset preparation script + update thermal_dataset.yaml for combined dataset"
```

---

## Task 10: Configure and Run YOLO11m Training

**Files:**
- Modify: `ml/configs/thermal.yaml`

### Key parameters for YOLO11m on thermal solar data

| Parameter | Value | Reason |
|---|---|---|
| `model` | `yolo11m.pt` | COCO pretrained backbone (auto-downloads) |
| `imgsz` | `640` | Matches iTL612R Pro 640×512 output |
| `epochs` | `150` | More than v8s needed for YOLO11m to converge; early stopping at patience=20 |
| `batch` | `16` | Adjust down to `8` if GPU OOM |
| `lr0` | `0.001` | Lower than default (0.01) — YOLO11m is larger, benefits from slower start |
| `lrf` | `0.0001` | Final LR = lr0 × lrf |
| `warmup_epochs` | `5` | More warmup for larger model |
| `hsv_h` | `0.0` | Thermal images have no meaningful hue |
| `hsv_s` | `0.0` | No saturation — thermal is grayscale-like |
| `hsv_v` | `0.4` | Brightness jitter simulates emissivity variation |
| `mosaic` | `1.0` | Critical — creates synthetic full-scene images from crops |
| `mixup` | `0.15` | Slightly more mixup than v8s for regularization |
| `degrees` | `5.0` | Small rotation — drones don't roll much at 20m |
| `scale` | `0.3` | Scale jitter simulates altitude variation 15-25m |
| `fliplr` | `0.5` | Horizontal flip — solar rows are symmetric |
| `flipud` | `0.0` | No vertical flip — sky/ground orientation matters |

- [ ] **Step 1: Update thermal.yaml with YOLO11m parameters**

Replace the full contents of `ml/configs/thermal.yaml`:

```yaml
# ── YOLO11m Thermal Solar Training Config ────────────────────────────────────
# Dataset
dataset_yaml: ml/thermal_dataset.yaml
imgsz: 640

# Model — YOLO11m, auto-downloads COCO pretrained weights on first run
model: yolo11m.pt

# Training
epochs: 150
batch: 16                  # reduce to 8 if GPU OOM
device: 0                  # GPU; 'cpu' as fallback
lr0: 0.001                 # lower than YOLO default — YOLO11m is larger
lrf: 0.0001                # final LR = lr0 × lrf
cos_lr: true
warmup_epochs: 5
warmup_momentum: 0.8
patience: 20               # early stopping — more generous for larger model
optimizer: AdamW           # AdamW outperforms SGD for YOLO11m fine-tuning
weight_decay: 0.0005

# Augmentation — thermal-specific
hsv_h: 0.0                 # no hue — thermal is not RGB
hsv_s: 0.0                 # no saturation
hsv_v: 0.4                 # brightness jitter simulates emissivity variation
degrees: 5.0               # small rotation (drone roll at 20m)
scale: 0.3                 # ±30% scale jitter → simulates 15-25m altitude range
fliplr: 0.5                # horizontal flip — solar rows are symmetric
flipud: 0.0                # no vertical flip
mosaic: 1.0                # critical for creating full-scene context from crops
mixup: 0.15
copy_paste: 0.1
close_mosaic: 15           # disable mosaic in last 15 epochs for stable convergence

# Output
project: ml/runs/thermal
name: yolo11m_solar
save_period: 10
plots: true                # save precision/recall/confusion matrix plots
```

- [ ] **Step 2: Verify dataset path is correct**

```bash
python -c "
import yaml
cfg = yaml.safe_load(open('ml/thermal_dataset.yaml'))
from pathlib import Path
root = Path(cfg['path'])
for split in ('train', 'val', 'test'):
    imgs = list((root / cfg[split]).glob('*'))
    print(f'{split}: {len(imgs)} images at {root / cfg[split]}')
assert (root / cfg['train']).exists(), 'train split not found'
"
```
Expected: all three paths exist with image counts

- [ ] **Step 3: Run training**

```bash
cd /home/parakh/Desktop/AxalonSystems
yolo train cfg=ml/configs/thermal.yaml
```

Training logs appear in `ml/runs/thermal/yolo11m_solar/`. Monitor:
- `mAP50` should exceed 0.70 by epoch 50
- `mAP50-95` is the harder metric — aim for > 0.45 after full training
- Watch per-class AP in the final summary — flag any class < 0.30

**If GPU OOM:** Set `batch: 8` in thermal.yaml and rerun.

**Expected training time:**
- RTX 3090/4090: ~3-5 hours for 150 epochs
- RTX 3060: ~6-10 hours

- [ ] **Step 4: Evaluate on test set**

```bash
yolo val model=ml/runs/thermal/yolo11m_solar/weights/best.pt \
          data=ml/thermal_dataset.yaml \
          split=test \
          device=0
```

Expected output includes per-class AP table. Save this output — it's your baseline benchmark.

- [ ] **Step 5: Copy best weights to canonical location**

```bash
cp ml/runs/thermal/yolo11m_solar/weights/best.pt ml/checkpoints/best.pt
```

- [ ] **Step 6: Quick inference sanity check**

```bash
python -c "
from ultralytics import YOLO
model = YOLO('ml/checkpoints/best.pt')
# Use any thermal test image you have
results = model('ml/data/combined/test/images/', conf=0.25, save=True)
total = sum(len(r.boxes) for r in results)
print(f'Detected {total} anomalies across test images')
print('Results saved to runs/detect/')
"
```

- [ ] **Step 7: Commit**

```bash
git add ml/configs/thermal.yaml
git commit -m "feat(ml): YOLO11m training config — combined dataset, AdamW, altitude-aware augmentation"
```

---

## Task 11: Export YOLO11m to TensorRT for Jetson Orin Nano

**Files:**
- Create: `ml/scripts/export_tensorrt.py`
- Modify: `platform/config/settings.yaml`

### Why TensorRT
The Jetson Orin Nano has a dedicated DLA (Deep Learning Accelerator) and CUDA cores. TensorRT compiles the YOLO11m graph into a hardware-optimised engine that runs 3-5× faster than the raw PyTorch model — critical for processing 500+ images post-flight in under 5 minutes.

**Important:** TensorRT export MUST be run on the Jetson itself (or a machine with the same CUDA/TensorRT version as the Jetson). Do NOT export on a desktop with a different GPU and copy the `.engine` file — it will not work.

- [ ] **Step 1: Verify TensorRT is available on Jetson**

Run this on the Jetson Orin Nano:

```bash
python -c "import tensorrt; print(tensorrt.__version__)"
# Expected: 8.x.x or 10.x.x
dpkg -l | grep tensorrt
```

If not installed: `sudo apt-get install tensorrt` (JetPack 6.x includes it)

- [ ] **Step 2: Create the export script**

```python
# ml/scripts/export_tensorrt.py
"""
Export YOLO11m to TensorRT engine for Jetson Orin Nano.

Run this ON THE JETSON, not on a desktop GPU.
Usage:
    python ml/scripts/export_tensorrt.py \
        --weights ml/checkpoints/best.pt \
        --out     ml/checkpoints/best.engine
"""
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", default="ml/checkpoints/best.pt")
    parser.add_argument("--out", default="ml/checkpoints/best.engine")
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--half", action="store_true", default=True,
                        help="FP16 — halves memory, 2x speed on Jetson")
    parser.add_argument("--batch", type=int, default=1,
                        help="Batch size for engine — use 1 for sequential inference")
    args = parser.parse_args()

    from ultralytics import YOLO
    model = YOLO(args.weights)
    model.export(
        format="engine",
        imgsz=args.imgsz,
        half=args.half,
        batch=args.batch,
        device=0,
        workspace=4,       # GB of TensorRT workspace
        verbose=True,
    )
    # Ultralytics saves as best.engine in same dir as best.pt
    engine_src = Path(args.weights).with_suffix(".engine")
    engine_dst = Path(args.out)
    if engine_src != engine_dst and engine_src.exists():
        engine_src.rename(engine_dst)
    print(f"TensorRT engine saved: {engine_dst}")
    print(f"Size: {engine_dst.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run export ON THE JETSON**

Transfer `best.pt` to the Jetson, then:

```bash
cd /path/to/AxalonSystems
python ml/scripts/export_tensorrt.py \
    --weights ml/checkpoints/best.pt \
    --out     ml/checkpoints/best.engine \
    --half    --batch 1
```

Expected: `TensorRT engine saved: ml/checkpoints/best.engine` (~15-25 MB)

- [ ] **Step 4: Benchmark engine vs PyTorch on Jetson**

```bash
python -c "
import time
from ultralytics import YOLO

# Benchmark PyTorch
pt = YOLO('ml/checkpoints/best.pt')
t0 = time.perf_counter()
for _ in range(50):
    pt('ml/data/combined/test/images/', conf=0.25, verbose=False)
pt_ms = (time.perf_counter() - t0) / 50 * 1000
print(f'PyTorch: {pt_ms:.1f} ms/image')

# Benchmark TensorRT
trt = YOLO('ml/checkpoints/best.engine')
t0 = time.perf_counter()
for _ in range(50):
    trt('ml/data/combined/test/images/', conf=0.25, verbose=False)
trt_ms = (time.perf_counter() - t0) / 50 * 1000
print(f'TensorRT: {trt_ms:.1f} ms/image')
print(f'Speedup: {pt_ms/trt_ms:.1f}x')
"
```

Expected: TensorRT 2-4× faster. If < 1.5× speedup, check JetPack version.

- [ ] **Step 5: Update settings.yaml to support engine path**

Add to the `model` section:

```yaml
model:
  weights: ml/checkpoints/best.pt        # PyTorch — for training and desktop use
  engine: ml/checkpoints/best.engine     # TensorRT — for Jetson deployment
  use_engine: false                       # set true on Jetson after export
  confidence: 0.25
  iou_threshold: 0.45
  imgsz: 640
  device: '0'
  batch_size: 8
```

- [ ] **Step 6: Update detector.py to use engine when configured**

In `platform/core/detector.py`, update `__init__` to support engine loading:

```python
    def __init__(
        self,
        weights_path: str | Path = DEFAULT_WEIGHTS,
        conf: float = 0.25,
        iou: float = 0.45,
        device: str = "0",
    ) -> None:
        from ultralytics import YOLO

        self.weights_path = Path(weights_path)
        self.conf = conf
        self.iou = iou

        # Prefer .engine file if it exists alongside the .pt and use_engine is true
        engine_path = self.weights_path.with_suffix(".engine")
        if engine_path.exists() and os.environ.get("AXALON_USE_ENGINE", "").lower() == "true":
            logger.info("TensorRT engine found — using %s", engine_path)
            self.weights_path = engine_path
        
        if str(device).lower() != "cpu":
            try:
                import torch
                if not torch.cuda.is_available():
                    logger.warning("CUDA device %s requested but unavailable; falling back to CPU", device)
                    device = "cpu"
            except Exception:
                logger.warning("Could not inspect CUDA availability; falling back to CPU")
                device = "cpu"
        self.device = device

        if not self.weights_path.exists():
            raise FileNotFoundError(f"Model weights not found: {self.weights_path}")

        logger.info("Loading model from %s (device=%s)", self.weights_path, device)
        self.model = YOLO(str(self.weights_path))
        logger.info("Model loaded — %d classes", len(CANONICAL_CLASSES))
```

Also add `import os` at the top of detector.py if not already present.

On the Jetson, set `export AXALON_USE_ENGINE=true` before starting the API.

- [ ] **Step 7: Commit**

```bash
git add ml/scripts/export_tensorrt.py platform/core/detector.py platform/config/settings.yaml
git commit -m "feat(ml): TensorRT export script + AXALON_USE_ENGINE env flag for Jetson"
```

---

## Summary of All Changes

| Area | What was built |
|---|---|
| **ML — Dataset** | `ml/scripts/prepare_dataset.py` merges InfraredSolarModules + PV-Hawk + Roboflow into 11-class canonical schema |
| **ML — Training** | `ml/configs/thermal.yaml` tuned for YOLO11m — AdamW, scale jitter for 15-25m altitude, 150 epochs |
| **ML — Export** | `ml/scripts/export_tensorrt.py` compiles TensorRT engine for Jetson; `AXALON_USE_ENGINE` env flag |
| **ML — Weights** | `ml/checkpoints/best.pt` (PyTorch) + `best.engine` (Jetson TensorRT) |
| `platform/core/temp_extractor.py` | RAW16 → °C matrix loader, per-bbox min/max/delta_T, IEC normalization |
| `platform/pipeline/ingest.py` | Auto-discovers `_temp.raw` companions per image |
| `platform/pipeline/orchestrator.py` | Temperature enrichment per detection, site_meta persistence |
| `platform/db/models.py` | 8 new Inspection columns, FaultComment table |
| `alembic/versions/0002 + 0003` | DB migrations, zero-downtime |
| `platform/api/app.py` | `inspection_type`, IEC warning, comment endpoints, altitude default 20m |
| `platform/reporting/report.py` | Revenue loss computation, populated Delta_T columns |
| `platform/config/settings.yaml` | `economics` section, engine path, use_engine flag |

**IEC 62446-3 compliance after this plan:**
- ✅ Delta_T measured (from RAW16 matrix)
- ✅ Delta_T normalized to 1000 W/m² (from irradiance input)
- ✅ Irradiance logged per inspection
- ✅ Inspection type (commissioning vs maintenance)
- ✅ Environmental conditions persisted
- ✅ Estimated revenue at risk in report

**Deployment path after this plan:**
1. Desktop: `best.pt` for development and testing
2. Jetson: `best.engine` (TensorRT FP16) via `AXALON_USE_ENGINE=true` — 3-5× faster inference
