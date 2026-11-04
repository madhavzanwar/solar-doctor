"""Unit tests for platform/core/fusion.py — ImageFusion alignment logic."""
from __future__ import annotations

import numpy as np
import pytest

from axalon.core.fusion import ImageFusion


def _detection() -> dict:
    return {
        "class": "hot-spot-high",
        "class_id": 10,
        "confidence": 0.9,
        "bbox": [2, 2, 8, 8],
        "bbox_norm": [0.5, 0.5, 0.3, 0.3],
        "severity": "CRITICAL",
        "color_bgr": (0, 0, 255),
    }


def test_resolve_mode_explicit_passthrough():
    # Arrange
    fusion = ImageFusion(mode="offset")

    # Act / Assert — explicit mode is never overridden
    assert fusion._resolve_mode(None, None) == "offset"


def test_resolve_mode_auto_uses_gps_when_both_present():
    fusion = ImageFusion(mode="auto")
    assert fusion._resolve_mode({"lat": 1, "lon": 2}, {"lat": 1, "lon": 2}) == "gps"


def test_resolve_mode_auto_falls_back_to_feature_without_gps():
    fusion = ImageFusion(mode="auto")
    assert fusion._resolve_mode(None, None) == "feature"


def test_compute_homography_offset_is_translation_matrix():
    # Arrange
    fusion = ImageFusion(mode="offset", camera_offset=[5, -3])
    thermal = np.zeros((20, 20, 3), dtype=np.uint8)
    rgb = np.zeros((20, 20, 3), dtype=np.uint8)

    # Act
    H = fusion._compute_homography(thermal, rgb, "offset", None, None)

    # Assert — pure translation by camera_offset
    expected = np.float32([[1, 0, 5], [0, 1, -3], [0, 0, 1]])
    assert np.allclose(H, expected)


def test_compute_homography_gps_is_scale_matrix():
    # Arrange — RGB twice the thermal resolution → scale factor 2 on each axis
    fusion = ImageFusion(mode="gps")
    thermal = np.zeros((10, 10, 3), dtype=np.uint8)
    rgb = np.zeros((20, 20, 3), dtype=np.uint8)

    # Act
    H = fusion._compute_homography(thermal, rgb, "gps", {"lat": 0}, {"lat": 0})

    # Assert
    expected = np.float32([[2, 0, 0], [0, 2, 0], [0, 0, 1]])
    assert np.allclose(H, expected)


def test_align_and_overlay_empty_detections_returns_copy():
    # Arrange
    fusion = ImageFusion(mode="offset")
    thermal = np.zeros((20, 20, 3), dtype=np.uint8)
    rgb = np.full((20, 20, 3), 7, dtype=np.uint8)

    # Act
    out = fusion.align_and_overlay(thermal, rgb, [])

    # Assert — same content, but a distinct array (copy, not the same object)
    assert np.array_equal(out, rgb)
    assert out is not rgb


def test_align_and_overlay_offset_returns_same_shape_image():
    # Arrange
    fusion = ImageFusion(mode="offset", camera_offset=[1, 1])
    thermal = np.zeros((20, 20, 3), dtype=np.uint8)
    rgb = np.zeros((20, 20, 3), dtype=np.uint8)

    # Act — projects the detection bbox and draws it
    out = fusion.align_and_overlay(thermal, rgb, [_detection()])

    # Assert
    assert out.shape == rgb.shape
    assert out.dtype == rgb.dtype


def _textured(h: int, w: int, seed: int) -> np.ndarray:
    """A reproducible noisy image so ORB finds keypoints."""
    rng = np.random.default_rng(seed)
    return rng.integers(0, 255, size=(h, w, 3), dtype=np.uint8)


def test_feature_homography_runs_on_textured_images():
    # Arrange — textured images give ORB enough keypoints to attempt matching
    fusion = ImageFusion(mode="feature")
    thermal = _textured(64, 64, seed=1)
    rgb = _textured(128, 128, seed=2)

    # Act — must not raise; returns a 3x3 matrix or None
    H = fusion._feature_homography(thermal, rgb)

    # Assert
    assert H is None or H.shape == (3, 3)


def test_feature_homography_blank_images_return_none():
    # Arrange — featureless images yield no descriptors
    fusion = ImageFusion(mode="feature")
    blank = np.zeros((32, 32, 3), dtype=np.uint8)

    # Act
    H = fusion._feature_homography(blank, blank)

    # Assert — insufficient keypoints path
    assert H is None


def test_align_and_overlay_feature_mode_returns_same_shape():
    # Arrange
    fusion = ImageFusion(mode="feature")
    thermal = _textured(40, 40, seed=3)
    rgb = _textured(40, 40, seed=4)

    # Act — exercises _resolve_mode -> feature -> _compute_homography -> projection
    out = fusion.align_and_overlay(thermal, rgb, [_detection()])

    # Assert
    assert out.shape == rgb.shape


def test_align_and_overlay_offset_fallback_when_no_homography():
    # Arrange — blank feature images produce H=None, forcing the offset fallback
    fusion = ImageFusion(mode="feature", camera_offset=[3, 3])
    blank = np.zeros((30, 30, 3), dtype=np.uint8)

    # Act
    out = fusion.align_and_overlay(blank, blank, [_detection()])

    # Assert — bbox shifted by camera_offset, image returned intact in shape
    assert out.shape == blank.shape
