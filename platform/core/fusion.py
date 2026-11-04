"""
fusion.py — Thermal + RGB image alignment and detection overlay.

Projects thermal IR bounding boxes onto the corresponding RGB image.
Alignment tiers, tried in order in ``auto`` mode until one yields a homography:
  0. Calibration   — fixed rig homography from a calibration flight
                     (core/fusion_calibration.py); used whenever configured
                     and valid for the frame sizes
  1. GPS-based     — uses EXIF GPS + GSD to estimate homography
  2. Feature-based — ORB keypoint matching (cv2.findHomography)
  3. Fixed offset  — configurable pixel translation for fixed-rig drones

The tier actually used is reported as ``FusionResult.mode``.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from ml.src.utils import draw_detections_severity, get_logger

from axalon.core.fusion_calibration import FusionCalibration

logger = get_logger("axalon.fusion")

MODE_CALIBRATION = "calibration"
MODE_GPS = "gps"
MODE_FEATURE = "feature"
MODE_OFFSET = "offset"
MODE_SKIPPED = "skipped"


@dataclass(frozen=True)
class FusionResult:
    """Outcome of projecting thermal detections onto an RGB frame."""

    image: np.ndarray
    mode: str                      # tier that produced the mapping
    homography: np.ndarray | None  # thermal px → RGB px (None when skipped)
    detections: list[dict]         # detections with bboxes in RGB pixels


class ImageFusion:
    """Align thermal detections onto RGB imagery."""

    def __init__(
        self,
        mode: str = "auto",
        camera_offset: list[int] | None = None,
        calibration: FusionCalibration | None = None,
    ) -> None:
        """
        Args:
            mode:          "calibration" | "gps" | "feature" | "offset" | "auto"
            camera_offset: [dx, dy] pixel offset thermal→RGB for fixed rigs.
            calibration:   Rig calibration; tried first in "auto" mode.
        """
        self.mode = mode
        self.camera_offset = camera_offset or [0, 0]
        self.calibration = calibration

    def align(
        self,
        thermal_bgr: np.ndarray,
        rgb_bgr: np.ndarray,
        detections: list[dict],
        thermal_gps: dict | None = None,
        rgb_gps: dict | None = None,
    ) -> FusionResult:
        """Project thermal detections onto the RGB image and report the tier used."""
        if not detections:
            return FusionResult(rgb_bgr.copy(), MODE_SKIPPED, None, [])

        mode, H = self._first_homography(thermal_bgr, rgb_bgr, thermal_gps, rgb_gps)
        rgb_detections = [{**det, "bbox": _project_bbox(det["bbox"], H)} for det in detections]
        image = draw_detections_severity(rgb_bgr, rgb_detections)
        return FusionResult(image, mode, H, rgb_detections)

    def align_and_overlay(
        self,
        thermal_bgr: np.ndarray,
        rgb_bgr: np.ndarray,
        detections: list[dict],
        thermal_gps: dict | None = None,
        rgb_gps: dict | None = None,
    ) -> np.ndarray:
        """Project thermal detections onto RGB image with severity coloring.

        Thin wrapper over :meth:`align` for callers that only need pixels.
        """
        return self.align(thermal_bgr, rgb_bgr, detections, thermal_gps, rgb_gps).image

    def _candidate_modes(self, thermal_gps, rgb_gps) -> list[str]:
        if self.mode != "auto":
            return [self.mode]
        modes = []
        if self.calibration is not None:
            modes.append(MODE_CALIBRATION)
        if thermal_gps and rgb_gps:
            modes.append(MODE_GPS)
        modes.append(MODE_FEATURE)
        return modes

    def _resolve_mode(self, thermal_gps, rgb_gps) -> str:
        return self._candidate_modes(thermal_gps, rgb_gps)[0]

    def _first_homography(
        self, thermal_bgr, rgb_bgr, thermal_gps, rgb_gps
    ) -> tuple[str, np.ndarray]:
        for mode in self._candidate_modes(thermal_gps, rgb_gps):
            H = self._compute_homography(thermal_bgr, rgb_bgr, mode, thermal_gps, rgb_gps)
            if H is not None:
                return mode, H
            logger.info("Fusion tier %r unavailable — trying next", mode)
        dx, dy = self.camera_offset
        return MODE_OFFSET, np.float64([[1, 0, dx], [0, 1, dy], [0, 0, 1]])

    def _compute_homography(
        self,
        thermal_bgr: np.ndarray,
        rgb_bgr: np.ndarray,
        mode: str,
        thermal_gps: dict | None,
        rgb_gps: dict | None,
    ) -> np.ndarray | None:
        """Compute homography matrix H mapping thermal → RGB coordinates."""
        th, tw = thermal_bgr.shape[:2]
        rh, rw = rgb_bgr.shape[:2]

        if mode == MODE_CALIBRATION:
            if self.calibration is None:
                return None
            H = self.calibration.scaled_homography((tw, th), (rw, rh))
            if H is None:
                logger.warning(
                    "Calibration %s does not fit frame sizes thermal=%sx%s rgb=%sx%s",
                    self.calibration.rig_id, tw, th, rw, rh,
                )
            return H

        if mode == MODE_OFFSET:
            dx, dy = self.camera_offset
            return np.float32([[1, 0, dx], [0, 1, dy], [0, 0, 1]])

        if mode == MODE_FEATURE:
            return self._feature_homography(thermal_bgr, rgb_bgr)

        if mode == MODE_GPS:
            # Both images cover approximately the same ground area:
            # scale-only homography from the resolution ratio.
            return np.float32([[rw / tw, 0, 0], [0, rh / th, 0], [0, 0, 1]])

        return None

    def _feature_homography(
        self, thermal_bgr: np.ndarray, rgb_bgr: np.ndarray
    ) -> np.ndarray | None:
        """ORB feature matching to estimate homography (thermal px → full RGB px)."""
        try:
            gray_t = cv2.cvtColor(thermal_bgr, cv2.COLOR_BGR2GRAY)
            gray_r = cv2.cvtColor(rgb_bgr, cv2.COLOR_BGR2GRAY)

            # Resize RGB to thermal size for matching (thermal is lower-res)
            th, tw = gray_t.shape[:2]
            rh, rw = gray_r.shape[:2]
            gray_r_resized = cv2.resize(gray_r, (tw, th))

            orb = cv2.ORB_create(nfeatures=500)
            kp1, des1 = orb.detectAndCompute(gray_t, None)
            kp2, des2 = orb.detectAndCompute(gray_r_resized, None)

            if des1 is None or des2 is None or len(kp1) < 4 or len(kp2) < 4:
                logger.warning("Feature matching: insufficient keypoints")
                return None

            bf = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
            matches = sorted(bf.match(des1, des2), key=lambda m: m.distance)[:50]

            if len(matches) < 4:
                return None

            src_pts = np.float32([kp1[m.queryIdx].pt for m in matches]).reshape(-1, 1, 2)
            dst_pts = np.float32([kp2[m.trainIdx].pt for m in matches]).reshape(-1, 1, 2)

            H, mask = cv2.findHomography(src_pts, dst_pts, cv2.RANSAC, 5.0)
            inliers = int(mask.sum()) if mask is not None else 0
            logger.info("Feature homography: %d inliers from %d matches", inliers, len(matches))
            if H is None:
                return None
            # Matching ran on the RGB frame shrunk to thermal size; undo that
            # so the mapping lands in full-resolution RGB pixels.
            return np.diag([rw / tw, rh / th, 1.0]) @ H

        except Exception as e:
            logger.warning("Feature homography failed: %s", e)
            return None


def _project_bbox(bbox: list, H: np.ndarray) -> list[int]:
    x1, y1, x2, y2 = bbox
    corners = np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dtype=np.float64)
    projected = cv2.perspectiveTransform(
        corners.reshape(1, -1, 2), np.asarray(H, dtype=np.float64)
    ).reshape(-1, 2)
    return [
        int(round(projected[:, 0].min())),
        int(round(projected[:, 1].min())),
        int(round(projected[:, 0].max())),
        int(round(projected[:, 1].max())),
    ]
