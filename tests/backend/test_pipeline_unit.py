"""Unit tests for orchestrator and ParkLayoutDetector (no API layer)."""
from pathlib import Path
import numpy as np
import pytest


# ── ParkLayoutDetector ────────────────────────────────────────────────────────

def test_park_layout_detector_assigns_grid_ids():
    from axalon.park.layout import ParkLayoutDetector
    # assign_grid_ids expects panels with a "center" key [cx, cy], not x/y/w/h.
    # The plan had x/y/w/h format (raw detect_panels input) and assumed 2 rows,
    # but ParkLayoutDetector.row_cluster_tolerance_px defaults to 30px, so rows
    # must be spaced > 30px apart. We use Y=20 and Y=100 (80px gap) to ensure
    # two distinct rows are detected, which matches the one-indexed R{r}-C{c} format.
    panels = [
        {"center": [20,  20], "bbox": [10, 10, 30,  30], "area": 400},
        {"center": [80,  20], "bbox": [70, 10, 90,  30], "area": 400},
        {"center": [20, 100], "bbox": [10, 90, 30, 110], "area": 400},
        {"center": [80, 100], "bbox": [70, 90, 90, 110], "area": 400},
    ]
    out = ParkLayoutDetector().assign_grid_ids(panels)
    ids = sorted([p["panel_id"] for p in out])
    assert ids == ["R1-C1", "R1-C2", "R2-C1", "R2-C2"]


def test_park_layout_detector_handles_empty_panel_list():
    from axalon.park.layout import ParkLayoutDetector
    out = ParkLayoutDetector().assign_grid_ids([])
    assert out == []


# ── Orchestrator (batch end-to-end without HTTP) ──────────────────────────────

@pytest.fixture
def fixture_dir():
    return Path(__file__).resolve().parents[1] / "fixtures" / "sample_mission"


def test_orchestrator_processes_a_batch_directly(fixture_dir, tmp_path):
    """Run the orchestrator's inspect_folder against the synthetic mission.

    This is slow (~30-90s on CPU) but verifies the pipeline outside the API.
    Marker: this is the only unit test that actually runs YOLO inference.
    """
    from axalon.pipeline.orchestrator import InspectionOrchestrator
    orch = InspectionOrchestrator(conf=0.25, device="cpu", output_dir=str(tmp_path))
    result = orch.inspect_folder(
        folder=str(fixture_dir),
        park_id="ORCH_UNIT_TEST",
        altitude_m=42.0,
    )
    assert result.get("total_images") == 20
    assert "summary" in result
    assert result.get("batch_id")


# ── Grid aggregator: extra integration shape ──────────────────────────────────

def test_grid_aggregator_with_realistic_payload():
    from types import SimpleNamespace
    from axalon.park.grid import build_grid

    park = SimpleNamespace(id="REALISTIC", rows=3, cols=4)
    detections = [
        {"panel_id": "R1-C1", "severity": "CRITICAL", "class": "hot-spot-high",
         "confidence": 0.91, "image_id": "img_001",
         "thermal_filename": "img_001.jpg",
         "bbox": [10, 10, 50, 50], "gps": {"lat": 19.0, "lon": 72.0}},
        {"panel_id": "R3-C4", "severity": "LOW", "class": "soiling",
         "confidence": 0.31, "image_id": "img_017",
         "thermal_filename": "img_017.jpg",
         "bbox": [5, 5, 30, 30], "gps": None},
    ]
    grid = build_grid(detections=detections, park=park, inspection_id="batch-X")
    assert grid["rows"] == 3 and grid["cols"] == 4
    assert len(grid["panels"]) == 2
    cell = next(p for p in grid["panels"] if p["panel_id"] == "R1-C1")
    assert cell["worst_severity"] == "CRITICAL"
    assert cell["gps"] == {"lat": 19.0, "lon": 72.0}
    assert cell["detections"][0]["class"] == "hot-spot-high"
