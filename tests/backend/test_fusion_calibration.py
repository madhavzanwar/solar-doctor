"""Tests for platform/core/fusion_calibration.py and its use by ImageFusion.

A thermal/RGB rig is rigidly mounted, so one homography (measured once on a
calibration flight) maps thermal pixels to RGB pixels for every frame. These
tests use synthetic homographies and images — no real drone data exists.
"""
from __future__ import annotations

import json

import cv2
import numpy as np
import pytest

from axalon.core.fusion import ImageFusion
from axalon.core.fusion_calibration import (
    CALIBRATION_FORMAT,
    CalibrationError,
    FusionCalibration,
    build_calibration,
    compute_homography_from_pairs,
    load_calibration_file,
    loads_calibration,
    pairs_from_checkerboard,
    resolve_active_calibration,
    save_calibration_file,
    store_calibration,
)

# A plausible thermal→RGB mapping: scale ~6x, small rotation, translation.
_KNOWN_H = np.array(
    [[6.10, 0.12, 180.0],
     [-0.08, 6.05, 140.0],
     [0.00001, 0.000005, 1.0]],
    dtype=np.float64,
)
_THERMAL_SIZE = (640, 512)
_RGB_SIZE = (4000, 3000)


def _project(H: np.ndarray, pts: np.ndarray) -> np.ndarray:
    return cv2.perspectiveTransform(pts.reshape(1, -1, 2).astype(np.float64), H).reshape(-1, 2)


def _valid_doc(**overrides) -> dict:
    doc = {
        "format": CALIBRATION_FORMAT,
        "version": 1,
        "rig_id": "AXL-RIG-01",
        "thermal_camera": "iTL612R Pro 25mm",
        "rgb_camera": "RGB-12MP",
        "thermal_size": list(_THERMAL_SIZE),
        "rgb_size": list(_RGB_SIZE),
        "homography": _KNOWN_H.tolist(),
        "rms_error_px": 0.8,
        "created_at": "2026-09-01T10:00:00Z",
    }
    doc.update(overrides)
    return doc


# ── loader / validation ──────────────────────────────────────────────────────

def test_parse_valid_calibration_roundtrip(tmp_path):
    # Arrange
    path = tmp_path / "cal.json"
    path.write_text(json.dumps(_valid_doc()))

    # Act
    cal = load_calibration_file(path)

    # Assert
    assert isinstance(cal, FusionCalibration)
    assert cal.rig_id == "AXL-RIG-01"
    assert cal.thermal_size == _THERMAL_SIZE
    assert cal.rgb_size == _RGB_SIZE
    assert np.allclose(cal.matrix, _KNOWN_H)
    assert cal.rms_error_px == pytest.approx(0.8)


def test_homography_is_normalised_so_h33_is_one():
    cal = loads_calibration(json.dumps(_valid_doc(homography=(_KNOWN_H * 4).tolist())))
    assert cal.matrix[2, 2] == pytest.approx(1.0)
    assert np.allclose(cal.matrix, _KNOWN_H)


@pytest.mark.parametrize(
    "overrides, fragment",
    [
        ({"format": "something-else"}, "format"),
        ({"version": 2}, "version"),
        ({"homography": [[1, 0], [0, 1]]}, "3x3"),
        ({"homography": [[1, 0, 0], [0, 1, 0], [0, 0, "x"]]}, "numeric"),
        ({"homography": [[1, 0, 0], [0, 1, 0], [0, 0, float("nan")]]}, "finite"),
        ({"homography": [[0, 0, 0], [0, 0, 0], [0, 0, 1]]}, "singular"),
        ({"homography": [[1, 0, 0], [0, 1, 0], [0, 0, 0]]}, "h33"),
        # w changes sign across the thermal frame → horizon inside the image
        ({"homography": [[1, 0, 0], [0, 1, 0], [-0.01, 0, 1]]}, "horizon"),
        ({"thermal_size": [640]}, "thermal_size"),
        ({"rgb_size": [0, 3000]}, "rgb_size"),
        ({"rig_id": ""}, "rig_id"),
        ({"rms_error_px": -1}, "rms_error_px"),
        ({"created_at": "yesterday"}, "created_at"),
    ],
)
def test_invalid_calibration_is_rejected(overrides, fragment):
    with pytest.raises(CalibrationError, match=fragment):
        loads_calibration(json.dumps(_valid_doc(**overrides)))


def test_missing_required_key_is_rejected():
    doc = _valid_doc()
    del doc["homography"]
    with pytest.raises(CalibrationError, match="homography"):
        loads_calibration(json.dumps(doc))


def test_non_json_is_rejected():
    with pytest.raises(CalibrationError, match="JSON"):
        loads_calibration("not json {")


def test_non_object_is_rejected():
    with pytest.raises(CalibrationError, match="object"):
        loads_calibration("[1, 2, 3]")


# ── homography application + scaling ─────────────────────────────────────────

def test_project_points_at_calibration_size_matches_known_homography():
    # Arrange
    cal = loads_calibration(json.dumps(_valid_doc()))
    pts = np.array([[0, 0], [320, 256], [639, 511], [100, 400]], dtype=np.float64)

    # Act
    out = cal.project_points(pts, _THERMAL_SIZE, _RGB_SIZE)

    # Assert
    assert np.allclose(out, _project(_KNOWN_H, pts), atol=1e-6)


def test_scaled_homography_handles_half_resolution_images():
    # Arrange — same rig, but both streams delivered at half resolution
    cal = loads_calibration(json.dumps(_valid_doc()))
    thermal_half = (320, 256)
    rgb_half = (2000, 1500)
    pts_half = np.array([[10, 20], [160, 128], [300, 250]], dtype=np.float64)

    # Act
    out = cal.project_points(pts_half, thermal_half, rgb_half)

    # Assert — equivalent to upscaling thermal pts, applying H, downscaling RGB
    expected = _project(_KNOWN_H, pts_half * 2.0) / 2.0
    assert np.allclose(out, expected, atol=1e-6)


def test_scaled_homography_returns_none_on_aspect_ratio_mismatch():
    # A 4:3 RGB stream against a 16:9 frame means a different sensor mode —
    # the calibration no longer describes this pair.
    cal = loads_calibration(json.dumps(_valid_doc()))
    assert cal.scaled_homography(_THERMAL_SIZE, (1920, 1080)) is None


# ── computing a calibration from point pairs ─────────────────────────────────

def _grid_thermal_points() -> np.ndarray:
    xs = np.linspace(40, 600, 5)
    ys = np.linspace(40, 470, 4)
    return np.array([[x, y] for y in ys for x in xs], dtype=np.float64)


def test_compute_homography_recovers_known_mapping():
    # Arrange
    thermal = _grid_thermal_points()
    rgb = _project(_KNOWN_H, thermal)

    # Act
    result = compute_homography_from_pairs(thermal, rgb)

    # Assert
    H = result.homography / result.homography[2, 2]
    assert np.allclose(_project(H, thermal), rgb, atol=0.05)
    assert result.rms_error_px < 0.05
    assert result.inliers == len(thermal)


def test_compute_homography_rejects_outlier_with_ransac():
    # Arrange — one badly mis-clicked point
    thermal = _grid_thermal_points()
    rgb = _project(_KNOWN_H, thermal)
    rgb[3] += np.array([250.0, -300.0])

    # Act
    result = compute_homography_from_pairs(thermal, rgb, ransac_threshold_px=3.0)

    # Assert — outlier excluded; RMS computed over inliers stays tiny
    assert result.inliers == len(thermal) - 1
    assert not result.inlier_mask[3]
    assert result.rms_error_px < 0.1


def test_compute_homography_needs_four_pairs():
    thermal = _grid_thermal_points()[:3]
    with pytest.raises(CalibrationError, match="at least 4"):
        compute_homography_from_pairs(thermal, _project(_KNOWN_H, thermal))


def test_compute_homography_rejects_mismatched_lengths():
    thermal = _grid_thermal_points()
    with pytest.raises(CalibrationError, match="same number"):
        compute_homography_from_pairs(thermal, _project(_KNOWN_H, thermal)[:-1])


def test_compute_homography_rejects_collinear_points():
    thermal = np.array([[10, 10], [20, 20], [30, 30], [40, 40], [50, 50]], dtype=np.float64)
    with pytest.raises(CalibrationError, match="collinear"):
        compute_homography_from_pairs(thermal, _project(_KNOWN_H, thermal))


def test_compute_homography_rejects_duplicate_points():
    thermal = np.array([[10, 10], [10, 10], [300, 40], [40, 300], [300, 300]], dtype=np.float64)
    with pytest.raises(CalibrationError, match="duplicate"):
        compute_homography_from_pairs(thermal, _project(_KNOWN_H, thermal))


def test_build_and_save_calibration_roundtrip(tmp_path):
    # Arrange
    thermal = _grid_thermal_points()
    rgb = _project(_KNOWN_H, thermal)
    result = compute_homography_from_pairs(thermal, rgb)

    # Act
    cal = build_calibration(
        result, thermal_size=_THERMAL_SIZE, rgb_size=_RGB_SIZE, rig_id="RIG-7",
        thermal_camera="t", rgb_camera="r", method="point-pairs",
    )
    path = tmp_path / "out.json"
    save_calibration_file(cal, path)
    loaded = load_calibration_file(path)

    # Assert
    assert loaded.rig_id == "RIG-7"
    assert loaded.num_points == len(thermal)
    assert loaded.method == "point-pairs"
    assert np.allclose(loaded.project_points(thermal, _THERMAL_SIZE, _RGB_SIZE), rgb, atol=0.05)


def _checkerboard(cols: int, rows: int, square: int, margin: int) -> np.ndarray:
    """Draw an inner-corner (cols x rows) checkerboard on a white canvas."""
    w = (cols + 1) * square + 2 * margin
    h = (rows + 1) * square + 2 * margin
    img = np.full((h, w), 255, dtype=np.uint8)
    for r in range(rows + 1):
        for c in range(cols + 1):
            if (r + c) % 2 == 0:
                y0, x0 = margin + r * square, margin + c * square
                img[y0:y0 + square, x0:x0 + square] = 0
    return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


def test_checkerboard_pairs_recover_homography():
    # Arrange — "thermal" board image, and an "RGB" view warped by a known H.
    # The thermal image is inverted (heated grid: hot squares are bright).
    thermal = _checkerboard(cols=7, rows=6, square=40, margin=60)
    th, tw = thermal.shape[:2]
    S = np.array([[2.0, 0.05, 30.0], [-0.03, 2.0, 20.0], [0.0, 0.0, 1.0]])
    rgb = cv2.warpPerspective(thermal, S, (tw * 2 + 80, th * 2 + 60), borderValue=(255, 255, 255))
    thermal_inverted = 255 - thermal

    # Act
    t_pts, r_pts = pairs_from_checkerboard(thermal_inverted, rgb, (7, 6))
    result = compute_homography_from_pairs(t_pts, r_pts)

    # Assert
    assert len(t_pts) == 42
    probe = np.array([[100.0, 100.0], [200.0, 150.0]])
    H = result.homography / result.homography[2, 2]
    assert np.allclose(_project(H, probe), _project(S, probe), atol=1.5)


def test_checkerboard_missing_board_raises():
    blank = np.full((200, 200, 3), 128, dtype=np.uint8)
    with pytest.raises(CalibrationError, match="checkerboard"):
        pairs_from_checkerboard(blank, blank, (7, 6))


def test_checkerboard_symmetric_pattern_rejected():
    board = _checkerboard(cols=6, rows=6, square=30, margin=40)
    with pytest.raises(CalibrationError, match="asymmetric"):
        pairs_from_checkerboard(board, board, (6, 6))


# ── active calibration resolution ────────────────────────────────────────────

def test_resolve_prefers_env_path(tmp_path, monkeypatch, db_session):
    # Arrange — DB has one calibration, env points at another
    store_calibration(db_session, loads_calibration(json.dumps(_valid_doc(rig_id="DB-RIG"))))
    env_file = tmp_path / "env.json"
    env_file.write_text(json.dumps(_valid_doc(rig_id="ENV-RIG")))
    monkeypatch.setenv("AXALON_FUSION_CALIBRATION", str(env_file))

    # Act
    active = resolve_active_calibration(session=db_session, settings={})

    # Assert
    assert active.calibration.rig_id == "ENV-RIG"
    assert active.source == "env"
    assert active.error is None


def test_resolve_uses_settings_path_then_db(tmp_path, monkeypatch, db_session):
    monkeypatch.delenv("AXALON_FUSION_CALIBRATION", raising=False)
    store_calibration(db_session, loads_calibration(json.dumps(_valid_doc(rig_id="DB-RIG"))))
    settings_file = tmp_path / "settings_cal.json"
    settings_file.write_text(json.dumps(_valid_doc(rig_id="YAML-RIG")))

    from_settings = resolve_active_calibration(
        session=db_session, settings={"camera": {"fusion_calibration": str(settings_file)}}
    )
    from_db = resolve_active_calibration(
        session=db_session, settings={"camera": {"fusion_calibration": ""}}
    )

    assert (from_settings.source, from_settings.calibration.rig_id) == ("settings", "YAML-RIG")
    assert (from_db.source, from_db.calibration.rig_id) == ("database", "DB-RIG")


def test_resolve_reports_broken_env_file_without_silently_using_db(tmp_path, monkeypatch, db_session):
    store_calibration(db_session, loads_calibration(json.dumps(_valid_doc(rig_id="DB-RIG"))))
    bad = tmp_path / "bad.json"
    bad.write_text("{}")
    monkeypatch.setenv("AXALON_FUSION_CALIBRATION", str(bad))

    active = resolve_active_calibration(session=db_session, settings={})

    assert active.calibration is None
    assert active.source == "env"
    assert active.error


def test_resolve_nothing_configured(monkeypatch, db_session):
    monkeypatch.delenv("AXALON_FUSION_CALIBRATION", raising=False)
    active = resolve_active_calibration(session=db_session, settings={})
    assert active.calibration is None
    assert active.source is None
    assert active.error is None


# ── ImageFusion integration + fallback order ─────────────────────────────────

def _det(bbox) -> dict:
    return {
        "class": "hot-spot-high", "class_id": 10, "confidence": 0.9,
        "bbox": list(bbox), "bbox_norm": [0.5, 0.5, 0.1, 0.1],
        "severity": "CRITICAL", "color_bgr": (0, 0, 255),
    }


def test_fusion_auto_uses_calibration_first_even_with_gps():
    # Arrange
    cal = loads_calibration(json.dumps(_valid_doc()))
    fusion = ImageFusion(mode="auto", calibration=cal)
    thermal = np.zeros((512, 640, 3), dtype=np.uint8)
    rgb = np.zeros((3000, 4000, 3), dtype=np.uint8)

    # Act
    result = fusion.align(thermal, rgb, [_det([100, 100, 140, 140])],
                          thermal_gps={"lat": 1, "lon": 2}, rgb_gps={"lat": 1, "lon": 2})

    # Assert
    assert result.mode == "calibration"
    corners = np.array([[100, 100], [140, 100], [140, 140], [100, 140]], dtype=np.float64)
    proj = _project(_KNOWN_H, corners)
    x1, y1, x2, y2 = result.detections[0]["bbox"]
    assert abs(x1 - proj[:, 0].min()) <= 1 and abs(x2 - proj[:, 0].max()) <= 1
    assert abs(y1 - proj[:, 1].min()) <= 1 and abs(y2 - proj[:, 1].max()) <= 1
    assert result.image.shape == rgb.shape


def test_fusion_falls_back_to_gps_when_calibration_does_not_fit_sizes():
    cal = loads_calibration(json.dumps(_valid_doc()))
    fusion = ImageFusion(mode="auto", calibration=cal)
    thermal = np.zeros((512, 640, 3), dtype=np.uint8)
    rgb = np.zeros((1080, 1920, 3), dtype=np.uint8)  # wrong aspect → calibration unusable

    result = fusion.align(thermal, rgb, [_det([10, 10, 20, 20])],
                          thermal_gps={"lat": 1, "lon": 2}, rgb_gps={"lat": 1, "lon": 2})

    assert result.mode == "gps"


def test_fusion_without_calibration_or_gps_tries_feature_then_offset():
    fusion = ImageFusion(mode="auto", camera_offset=[4, 5])
    blank = np.zeros((60, 60, 3), dtype=np.uint8)  # no ORB features

    result = fusion.align(blank, blank, [_det([10, 10, 20, 20])])

    assert result.mode == "offset"
    assert result.detections[0]["bbox"] == [14, 15, 24, 25]


def test_fusion_feature_homography_is_expressed_in_full_rgb_pixels():
    # ORB matches against RGB resized to thermal size; the returned H must be
    # rescaled back so boxes land in full-resolution RGB coordinates.
    rng = np.random.default_rng(7)
    base = rng.integers(0, 255, size=(40, 50), dtype=np.uint8)
    thermal = cv2.cvtColor(cv2.resize(base, (200, 160), interpolation=cv2.INTER_NEAREST), cv2.COLOR_GRAY2BGR)
    rgb = cv2.resize(thermal, (400, 320), interpolation=cv2.INTER_NEAREST)

    H = ImageFusion(mode="feature")._feature_homography(thermal, rgb)

    assert H is not None
    out = _project(H, np.array([[50.0, 40.0], [150.0, 120.0]]))
    assert np.allclose(out, [[100.0, 80.0], [300.0, 240.0]], atol=3.0)


def test_align_and_overlay_still_returns_plain_image():
    cal = loads_calibration(json.dumps(_valid_doc()))
    fusion = ImageFusion(mode="auto", calibration=cal)
    thermal = np.zeros((512, 640, 3), dtype=np.uint8)
    rgb = np.zeros((3000, 4000, 3), dtype=np.uint8)
    out = fusion.align_and_overlay(thermal, rgb, [_det([1, 1, 5, 5])])
    assert isinstance(out, np.ndarray) and out.shape == rgb.shape
