"""Tests for InspectionOrchestrator — mocked to avoid real model/GPU dependency."""
import json
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch


@pytest.fixture
def mock_detector():
    """SolarDetector mock that returns one CRITICAL detection per image."""
    det = {
        "class": "hot-spot-high",
        "class_id": 10,
        "severity": "CRITICAL",
        "confidence": 0.91,
        "bbox": [10, 20, 50, 60],
        "bbox_norm": [0.3, 0.4, 0.2, 0.2],
        "color_bgr": (0, 0, 255),
        "gps": None,
    }
    mock = MagicMock()
    mock.predict.return_value = [det]
    mock.detection_summary.return_value = {"CRITICAL": 1, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    return mock


@pytest.fixture
def orchestrator(tmp_path, mock_detector):
    """Orchestrator with mocked detector and in-memory DB. Resets global DB state on teardown."""
    with patch("axalon.pipeline.orchestrator.SolarDetector", return_value=mock_detector):
        from axalon.pipeline.orchestrator import InspectionOrchestrator
        orch = InspectionOrchestrator(
            output_dir=tmp_path / "output",
            db_url="sqlite:///:memory:",
        )
    orch.detector = mock_detector
    yield orch
    # Reset global engine so subsequent tests start with a clean slate
    import axalon.db.session as _sess
    _sess._engine = None
    _sess._SessionLocal = None


def test_match_panel_id_nearest():
    from axalon.pipeline.orchestrator import _match_panel_id
    panel_map = {
        "R1-C1": {"center": [10, 10], "bbox_image": [0, 0, 20, 20], "gps": None},
        "R1-C2": {"center": [100, 10], "bbox_image": [80, 0, 120, 20], "gps": None},
    }
    det = {"bbox": [5, 5, 15, 15]}  # center at (10, 10) — nearest to R1-C1
    assert _match_panel_id(det, panel_map) == "R1-C1"

    det2 = {"bbox": [90, 5, 110, 15]}  # center at (100, 10) — nearest to R1-C2
    assert _match_panel_id(det2, panel_map) == "R1-C2"


def test_match_panel_id_empty_map():
    from axalon.pipeline.orchestrator import _match_panel_id
    assert _match_panel_id({"bbox": [0, 0, 10, 10]}, {}) == "R?-C?"


def test_inspect_pair_assigns_panel_id(orchestrator, tmp_path):
    """inspect_pair assigns panel_id from panel_map."""
    import cv2
    import numpy as np
    # Create a minimal thermal image
    img = np.zeros((100, 100, 3), dtype=np.uint8)
    thermal = tmp_path / "thermal_001.jpg"
    cv2.imwrite(str(thermal), img)

    panel_map = {
        "R1-C1": {"center": [30, 40], "bbox_image": [0, 0, 60, 80], "gps": None},
    }
    result = orchestrator.inspect_pair(
        thermal_path=thermal,
        panel_map=panel_map,
    )
    assert result["detections"][0]["panel_id"] == "R1-C1"


def test_ensure_park_idempotent(orchestrator):
    """_ensure_park must not raise or double-insert when called twice for the same park_id."""
    from axalon.pipeline.orchestrator import _ensure_park
    from axalon.db.session import get_session
    from axalon.db.models import Park

    layout = {"rows": 4, "total_panels": 20, "mode": "auto", "panel_map": {}}
    session = get_session()
    _ensure_park(session, "PARK-IDEM", layout)
    session.close()

    # Second call must not raise (PK violation would propagate as IntegrityError)
    session = get_session()
    _ensure_park(session, "PARK-IDEM", layout)
    count = session.query(Park).filter_by(id="PARK-IDEM").count()
    session.close()
    assert count == 1


def test_inspect_pair_persists_to_db(orchestrator, tmp_path):
    """inspect_pair writes Detection rows when inspection_id is provided."""
    import cv2
    import numpy as np
    from axalon.db.session import get_session
    from axalon.db.models import Park, Inspection, Detection as DbDetection

    img = np.zeros((100, 100, 3), dtype=np.uint8)
    thermal = tmp_path / "thermal_002.jpg"
    cv2.imwrite(str(thermal), img)

    # Pre-insert required Park and Inspection rows (FK deps)
    session = get_session()
    session.add(Park(id="PARK_T", name="Test", mode="auto"))
    session.flush()
    session.add(Inspection(
        id="BATCH-TEST-001",
        park_id="PARK_T",
        flight_date="2026-04-11",
        total_images=1,
        total_detections=0,
        summary="{}",
    ))
    session.commit()
    session.close()

    orchestrator.inspect_pair(
        thermal_path=thermal,
        inspection_id="BATCH-TEST-001",
    )

    session = get_session()
    dets = session.query(DbDetection).filter_by(inspection_id="BATCH-TEST-001").all()
    assert len(dets) == 1
    assert dets[0].severity == "CRITICAL"
    session.close()


def _write_geotagged_thermal(path, heading: float | None) -> None:
    """100x100 JPEG with GPS EXIF (image centre 19.0N 72.0E) and optional GPSImgDirection."""
    import piexif
    from PIL import Image

    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: b"N",
        piexif.GPSIFD.GPSLatitude: ((19, 1), (0, 1), (0, 100)),
        piexif.GPSIFD.GPSLongitudeRef: b"E",
        piexif.GPSIFD.GPSLongitude: ((72, 1), (0, 1), (0, 100)),
        piexif.GPSIFD.GPSAltitude: (4000, 100),
    }
    if heading is not None:
        gps_ifd[piexif.GPSIFD.GPSImgDirectionRef] = b"T"
        gps_ifd[piexif.GPSIFD.GPSImgDirection] = (int(heading * 100), 100)
    Image.new("RGB", (100, 100)).save(str(path), "jpeg", exif=piexif.dump({"GPS": gps_ifd}))


def test_inspect_pair_gps_uses_image_heading(orchestrator, tmp_path):
    """A fault at the top of the frame lands north with no heading, east at heading 90°."""
    import math

    # Arrange — fresh detection dict per call; bbox centre (50, 10) is 40 px above image centre
    orchestrator.detector.predict.side_effect = lambda *_a, **_k: [{
        "class": "hot-spot-high", "class_id": 10, "severity": "CRITICAL",
        "confidence": 0.9, "bbox": [45, 5, 55, 15], "bbox_norm": [0.5, 0.1, 0.1, 0.1],
        "color_bgr": (0, 0, 255), "gps": None,
    }]
    north_up = tmp_path / "thermal_north.jpg"
    east_up = tmp_path / "thermal_east.jpg"
    _write_geotagged_thermal(north_up, heading=None)
    _write_geotagged_thermal(east_up, heading=90.0)

    # Act
    gps_north = orchestrator.inspect_pair(thermal_path=north_up)["detections"][0]["gps"]
    gps_east = orchestrator.inspect_pair(thermal_path=east_up)["detections"][0]["gps"]

    # Assert — no heading metadata: falls back to 0, offset is due north
    assert gps_north["lat"] > 19.0
    assert gps_north["lon"] == pytest.approx(72.0, abs=1e-9)
    # Heading 90: the same offset rotated due east, same distance
    assert gps_east["lat"] == pytest.approx(19.0, abs=1e-9)
    assert gps_east["lon"] > 72.0
    north_m = math.radians(gps_north["lat"] - 19.0) * 6_371_000.0
    east_m = math.radians(gps_east["lon"] - 72.0) * 6_371_000.0 * math.cos(math.radians(19.0))
    assert east_m == pytest.approx(north_m, rel=1e-6)


def _seed_inspection(park_id: str, inspection_id: str) -> None:
    from axalon.db.session import get_session
    from axalon.db.models import Park, Inspection

    session = get_session()
    session.add(Park(id=park_id, name="Test", mode="auto"))
    session.flush()
    session.add(Inspection(id=inspection_id, park_id=park_id, summary="{}"))
    session.commit()
    session.close()


def test_inspect_pair_persists_temperatures(orchestrator, tmp_path):
    """Temperatures from a _temp.raw companion reach the Detection row."""
    import cv2
    import numpy as np
    from axalon.db.session import get_session
    from axalon.db.models import Detection as DbDetection

    thermal = tmp_path / "thermal_003.jpg"
    cv2.imwrite(str(thermal), np.zeros((512, 640, 3), dtype=np.uint8))
    # 30 °C background, 70 °C hotspot inside the mocked bbox [10, 20, 50, 60]
    raw = np.full((512, 640), round((30 + 273.15) / 0.04), dtype=np.uint16)
    raw[20:60, 10:50] = round((70 + 273.15) / 0.04)
    temp_raw = tmp_path / "thermal_003_temp.raw"
    temp_raw.write_bytes(raw.tobytes())
    _seed_inspection("PARK_TEMP", "BATCH-TEMP-001")

    orchestrator.inspect_pair(
        thermal_path=thermal,
        inspection_id="BATCH-TEMP-001",
        temp_raw_path=temp_raw,
        irradiance_wm2=800.0,
    )

    session = get_session()
    row = session.query(DbDetection).filter_by(inspection_id="BATCH-TEMP-001").one()
    assert row.max_temp == pytest.approx(70.0, abs=0.05)
    assert row.reference_temp == pytest.approx(30.0, abs=0.05)
    assert row.delta_t_measured == pytest.approx(40.0, abs=0.1)
    assert row.delta_t_normalized == pytest.approx(50.0, abs=0.2)
    session.close()


def test_inspect_pair_without_temp_raw_leaves_temperatures_null(orchestrator, tmp_path):
    import cv2
    import numpy as np
    from axalon.db.session import get_session
    from axalon.db.models import Detection as DbDetection

    thermal = tmp_path / "thermal_004.jpg"
    cv2.imwrite(str(thermal), np.zeros((100, 100, 3), dtype=np.uint8))
    _seed_inspection("PARK_NOTEMP", "BATCH-NOTEMP-001")

    orchestrator.inspect_pair(thermal_path=thermal, inspection_id="BATCH-NOTEMP-001")

    session = get_session()
    row = session.query(DbDetection).filter_by(inspection_id="BATCH-NOTEMP-001").one()
    assert row.max_temp is None
    assert row.delta_t_measured is None
    session.close()
