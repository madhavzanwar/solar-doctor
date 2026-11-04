# Plan 03 — Implement `park/locator.py`
**Priority:** P1 | **Effort:** Medium
**Goal:** Implement the missing anomaly-to-panel mapping module referenced in the platform spec.

---

## Why

The platform spec (Phase 3) describes `park/locator.py` as the module that maps each detected anomaly to a specific panel ID. Without it, fault reports cannot say "Panel R3-C7 has a hot-spot-high anomaly" — only raw GPS coordinates. This is the core differentiator of the platform.

---

## What It Does

Given:
- A list of detections (from `detector.py`) with GPS coordinates
- A park layout (from `park/layout.py` or `park/numbering.py`)

Return:
- Each detection annotated with a `panel_id` (e.g. `"R3-C7"` for unnumbered parks, `"A-042"` for numbered parks)

---

## Module Interface

```python
# platform/park/locator.py

from dataclasses import dataclass
from typing import Literal

@dataclass
class LocatedFault:
    detection: dict           # original detection dict from detector.py
    panel_id: str             # e.g. "R3-C7" or "A-042"
    panel_index: tuple[int, int] | None   # (row, col) for grid parks
    confidence: float         # 0–1, how confident the assignment is


def locate_faults(
    detections: list[dict],
    park_layout: dict,
    mode: Literal["grid", "numbered"] = "grid",
) -> list[LocatedFault]:
    """
    Map each detection to the closest panel in the park layout.

    Args:
        detections: list of detection dicts from detector.py
                    Each has: class, class_id, confidence, bbox, bbox_norm, severity, color_bgr
                    and optionally: gps (lat, lon from geo.py)
        park_layout: dict from layout.py or numbering.py
                     Grid mode: {"rows": int, "cols": int, "origin_gps": (lat,lon),
                                  "panel_size_m": (w,h), "orientation_deg": float}
                     Numbered mode: {"panels": [{"id": str, "gps": (lat,lon)}, ...]}
        mode: "grid" for auto-grid parks, "numbered" for OCR-numbered parks

    Returns:
        list of LocatedFault, one per detection
    """
    ...
```

---

## Implementation

### Grid mode (unnumbered parks)

```python
def _locate_grid(detection: dict, layout: dict) -> LocatedFault:
    """
    1. Get detection GPS from detection["gps"] (lat, lon)
    2. Compute vector from park origin to detection GPS in meters
       (use pyproj or simple haversine for small distances)
    3. Rotate by -orientation_deg to get panel-local (x, y)
    4. row = int(y / panel_height_m), col = int(x / panel_width_m)
    5. Clamp to [0, rows-1] and [0, cols-1]
    6. panel_id = f"R{row+1}-C{col+1}"
    7. confidence = 1.0 if GPS present, 0.5 if synthetic GPS
    """
```

**Haversine helper** (if pyproj not available):
```python
def _haversine_offset_m(origin: tuple, point: tuple) -> tuple[float, float]:
    """Return (delta_x_m, delta_y_m) from origin to point."""
    import math
    R = 6_371_000
    dlat = math.radians(point[0] - origin[0])
    dlon = math.radians(point[1] - origin[1])
    lat_m = dlat * R
    lon_m = dlon * R * math.cos(math.radians(origin[0]))
    return lon_m, lat_m
```

### Numbered mode

```python
def _locate_numbered(detection: dict, layout: dict) -> LocatedFault:
    """
    1. Get detection GPS
    2. For each panel in layout["panels"], compute distance to detection GPS
    3. Assign to nearest panel
    4. confidence = 1.0 if distance < 1m, scale down to 0.0 at 5m
    """
```

### Fallback (no GPS)

If a detection has no GPS coordinates (e.g., image had no EXIF), assign `panel_id = "UNKNOWN"` and `confidence = 0.0`.

---

## Integration Points

After implementing `locator.py`, update:

1. **`pipeline/orchestrator.py`** — call `locate_faults()` after detection step, attach `panel_id` to each fault before DB write.
2. **`db/models.py` `PanelFault`** — ensure `panel_id` column exists (check migration).
3. **`reporting/report.py`** — include `panel_id` in PDF and Excel outputs.

---

## Tests to Write

Create `tests/backend/test_locator.py`:

```python
def test_grid_locate_origin():
    """Detection at park origin → R1-C1."""

def test_grid_locate_far_corner():
    """Detection near (rows-1, cols-1) → correct row/col."""

def test_numbered_locate_nearest():
    """Detection GPS closest to panel A-042 → panel_id='A-042'."""

def test_no_gps_returns_unknown():
    """Detection without GPS → panel_id='UNKNOWN', confidence=0.0."""

def test_locate_faults_returns_one_per_detection():
    """Output list length == input detections length."""
```

---

## Done When

- [ ] `platform/park/locator.py` exists with `locate_faults()` implemented
- [ ] Grid mode tested with at least 4 unit tests
- [ ] Numbered mode tested with at least 2 unit tests
- [ ] `orchestrator.py` calls `locate_faults()` and writes `panel_id` to DB
- [ ] Report PDF/Excel shows panel IDs
