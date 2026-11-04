import numpy as np
import pytest
from pathlib import Path
from axalon.core.temp_extractor import (
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


def test_normalize_delta_t_negative_irradiance():
    with pytest.raises(ValueError, match="non-negative"):
        normalize_delta_t(10.0, -100.0)


def test_compute_delta_t_offscreen_bbox():
    matrix = np.full((512, 640), 25.0, dtype=np.float32)
    result = compute_delta_t(matrix, [700, 600, 750, 650])
    assert result["delta_t_measured"] is None
    assert result["reference_temp"] is None


import cv2
from axalon.pipeline.ingest import find_image_pairs


def test_find_image_pairs_includes_temp_raw(tmp_path):
    thermal_dir = tmp_path / "thermal"
    thermal_dir.mkdir()
    img = thermal_dir / "img_001.jpg"
    cv2.imwrite(str(img), np.ones((1, 1, 3), dtype=np.uint8) * 255)
    raw = thermal_dir / "img_001_temp.raw"
    raw.write_bytes(b"\x00" * (640 * 512 * 2))
    pairs = find_image_pairs(tmp_path)
    assert len(pairs) == 1
    assert pairs[0]["temp_raw"] == raw


def test_find_image_pairs_temp_raw_none_when_absent(tmp_path):
    thermal_dir = tmp_path / "thermal"
    thermal_dir.mkdir()
    cv2.imwrite(str(thermal_dir / "img_001.jpg"), np.ones((1, 1, 3), dtype=np.uint8) * 255)
    pairs = find_image_pairs(tmp_path)
    assert len(pairs) == 1
    assert pairs[0]["temp_raw"] is None
