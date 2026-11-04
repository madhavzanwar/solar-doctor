"""Unit tests for the panel-grid aggregator."""
from types import SimpleNamespace

from axalon.park.grid import build_grid


def _det(panel_id, severity, class_="hot-spot-low", confidence=0.5, image_id="img_001", bbox=None, gps=None):
    return {
        "panel_id": panel_id,
        "severity": severity,
        "class": class_,
        "confidence": confidence,
        "image_id": image_id,
        "thermal_filename": f"{image_id}.jpg",
        "bbox": bbox or [0, 0, 10, 10],
        "gps": gps,
    }


def test_build_grid_returns_park_metadata():
    park = SimpleNamespace(id="P1", rows=2, cols=3)
    grid = build_grid(detections=[], park=park, inspection_id="batch-1")
    assert grid["park_id"] == "P1"
    assert grid["inspection_id"] == "batch-1"
    assert grid["rows"] == 2 and grid["cols"] == 3
    assert grid["panels"] == []


def test_build_grid_aggregates_worst_severity():
    park = SimpleNamespace(id="P1", rows=2, cols=3)
    detections = [
        _det("R1-C1", "MEDIUM"),
        _det("R1-C1", "CRITICAL"),
        _det("R2-C3", "LOW"),
    ]
    grid = build_grid(detections=detections, park=park, inspection_id="batch-1")
    cells = {p["panel_id"]: p for p in grid["panels"]}
    assert cells["R1-C1"]["worst_severity"] == "CRITICAL"
    assert cells["R1-C1"]["detection_count"] == 2
    assert cells["R2-C3"]["worst_severity"] == "LOW"
    assert cells["R2-C3"]["detection_count"] == 1


def test_build_grid_includes_first_gps_when_available():
    park = SimpleNamespace(id="P1", rows=1, cols=1)
    detections = [
        _det("R1-C1", "LOW", gps={"lat": 19.0, "lon": 72.0}),
        _det("R1-C1", "MEDIUM", gps=None),
    ]
    grid = build_grid(detections=detections, park=park, inspection_id="batch-1")
    cell = grid["panels"][0]
    assert cell["gps"] == {"lat": 19.0, "lon": 72.0}


def test_build_grid_falls_back_to_panel_id_regex_when_rows_cols_zero():
    park = SimpleNamespace(id="P1", rows=0, cols=0)
    detections = [_det("R3-C7", "HIGH"), _det("R1-C2", "LOW")]
    grid = build_grid(detections=detections, park=park, inspection_id="batch-1")
    assert grid["rows"] == 3
    assert grid["cols"] == 7


def test_build_grid_handles_unparseable_panel_ids():
    park = SimpleNamespace(id="P1", rows=0, cols=0)
    detections = [_det("UNKNOWN", "LOW"), _det(None, "HIGH")]
    grid = build_grid(detections=detections, park=park, inspection_id="batch-1")
    assert grid["rows"] == 0 and grid["cols"] == 0
    # detections with no parseable panel_id are skipped from the panels list
    assert all(p["panel_id"] for p in grid["panels"])
