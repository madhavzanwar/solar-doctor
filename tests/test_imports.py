"""Verify that both registered packages are importable after pip install -e ."""


def test_ml_utils_importable():
    from ml.src.utils import (
        CANONICAL_CLASSES, CLASS2ID, ID2CLASS,
        SEVERITY_MAP, SEVERITY_COLOR_BGR,
        draw_detections_severity, read_yolo_label, write_yolo_label,
        yolo_to_pixel, load_bgr, get_logger,
    )
    assert len(CANONICAL_CLASSES) == 11
    assert CLASS2ID["cell"] == 0
    assert SEVERITY_MAP["hot-spot-high"] == "CRITICAL"


def test_axalon_core_importable():
    from axalon.core.detector import SolarDetector
    from axalon.core.fusion import ImageFusion
    from axalon.core.geo import extract_gps_exif


def test_axalon_pipeline_importable():
    from axalon.pipeline.ingest import find_image_pairs
    from axalon.pipeline.orchestrator import InspectionOrchestrator


def test_axalon_reporting_importable():
    from axalon.reporting.report import generate_json_report, generate_excel_report
    from axalon.reporting.geojson_writer import write_geojson


def test_axalon_park_importable():
    from axalon.park.layout import ParkLayoutDetector
