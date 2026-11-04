"""
fusion_calibration.py — Fixed thermal→RGB homography for a rigid camera rig.

Thermal and RGB frames share almost no visual features, so per-frame ORB
matching (fusion tier 2) is unreliable. The two cameras are rigidly mounted,
though, so a single homography measured once (spec §15.4 #1, "calibration
flight") maps thermal pixels to RGB pixels for every frame of that rig.

Calibration file (JSON, ``format: "axalon-fusion-calibration"``, version 1)::

    {
      "format": "axalon-fusion-calibration",
      "version": 1,
      "rig_id": "AXL-RIG-01",                 # required, non-empty
      "thermal_camera": "iTL612R Pro 25mm",   # optional free text
      "rgb_camera": "RGB-12MP",               # optional free text
      "thermal_size": [640, 512],             # [width, height] px the H was measured at
      "rgb_size": [4000, 3000],               # [width, height] px
      "homography": [[h11,h12,h13],[h21,h22,h23],[h31,h32,h33]],  # thermal px → RGB px
      "rms_error_px": 0.84,                   # reprojection RMS in RGB px (inliers)
      "num_points": 12,                       # optional
      "method": "point-pairs",                # optional: point-pairs | checkerboard
      "created_at": "2026-09-01T10:00:00Z"    # ISO 8601
    }

Frames at a different resolution than the calibration are handled by scaling
(``H' = S_rgb · H · S_thermal⁻¹``) as long as each stream keeps its aspect
ratio; a changed aspect ratio means a different sensor mode or crop, which
the calibration does not describe, so it is refused rather than guessed.

Active calibration resolution order (first configured source wins, and a
broken configured source is reported — never silently skipped):
  1. ``AXALON_FUSION_CALIBRATION`` env var → path to a calibration file
  2. ``camera.fusion_calibration`` in settings.yaml → path
  3. ``app_config`` DB row ``fusion_calibration`` (set via the API upload)
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np

from ml.src.utils import get_logger

logger = get_logger("axalon.fusion_calibration")

CALIBRATION_FORMAT = "axalon-fusion-calibration"
CALIBRATION_VERSION = 1
CALIBRATION_ENV_VAR = "AXALON_FUSION_CALIBRATION"
CALIBRATION_CONFIG_KEY = "fusion_calibration"
CALIBRATION_METHODS = ("point-pairs", "checkerboard")

MIN_POINT_PAIRS = 4
# Aspect ratios within this relative tolerance count as "same stream shape".
_ASPECT_TOLERANCE = 0.02
# Picked points closer than this (px) are treated as the same point.
_DUPLICATE_TOLERANCE_PX = 0.5
# Normalised smallest/largest singular value below which points are collinear.
_COLLINEAR_RATIO = 1e-3
_SINGULAR_EPS = 1e-9

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_SETTINGS_PATH = Path(__file__).resolve().parents[1] / "config" / "settings.yaml"


class CalibrationError(ValueError):
    """Raised when a calibration file or point set is invalid or degenerate."""


# ── data model ───────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class FusionCalibration:
    """A validated thermal→RGB homography for one camera rig."""

    homography: tuple[tuple[float, float, float], ...]
    thermal_size: tuple[int, int]
    rgb_size: tuple[int, int]
    rig_id: str
    rms_error_px: float
    created_at: str
    thermal_camera: str | None = None
    rgb_camera: str | None = None
    num_points: int | None = None
    method: str | None = None

    @property
    def matrix(self) -> np.ndarray:
        return np.array(self.homography, dtype=np.float64)

    def scaled_homography(
        self, thermal_size: tuple[int, int], rgb_size: tuple[int, int]
    ) -> np.ndarray | None:
        """Homography for frames of the given ``(width, height)`` sizes.

        Returns ``None`` when either stream's aspect ratio differs from the
        calibration's — the stored homography does not describe that pair.
        """
        if not (_same_aspect(thermal_size, self.thermal_size)
                and _same_aspect(rgb_size, self.rgb_size)):
            return None
        s_thermal_inv = np.diag([
            self.thermal_size[0] / thermal_size[0],
            self.thermal_size[1] / thermal_size[1],
            1.0,
        ])
        s_rgb = np.diag([
            rgb_size[0] / self.rgb_size[0],
            rgb_size[1] / self.rgb_size[1],
            1.0,
        ])
        return s_rgb @ self.matrix @ s_thermal_inv

    def project_points(
        self,
        points: np.ndarray,
        thermal_size: tuple[int, int] | None = None,
        rgb_size: tuple[int, int] | None = None,
    ) -> np.ndarray:
        """Map ``(N, 2)`` thermal pixel points into RGB pixel coordinates."""
        H = self.scaled_homography(thermal_size or self.thermal_size, rgb_size or self.rgb_size)
        if H is None:
            raise CalibrationError(
                "image aspect ratio does not match the calibration's thermal_size/rgb_size"
            )
        pts = np.asarray(points, dtype=np.float64).reshape(1, -1, 2)
        return cv2.perspectiveTransform(pts, H).reshape(-1, 2)

    def to_dict(self) -> dict:
        doc: dict[str, Any] = {
            "format": CALIBRATION_FORMAT,
            "version": CALIBRATION_VERSION,
            "rig_id": self.rig_id,
            "thermal_camera": self.thermal_camera,
            "rgb_camera": self.rgb_camera,
            "thermal_size": list(self.thermal_size),
            "rgb_size": list(self.rgb_size),
            "homography": [list(row) for row in self.homography],
            "rms_error_px": self.rms_error_px,
            "num_points": self.num_points,
            "method": self.method,
            "created_at": self.created_at,
        }
        return {k: v for k, v in doc.items() if v is not None}

    def summary(self) -> dict:
        """Everything but the matrix — what an operator needs to eyeball."""
        return {
            "rig_id": self.rig_id,
            "thermal_camera": self.thermal_camera,
            "rgb_camera": self.rgb_camera,
            "thermal_size": list(self.thermal_size),
            "rgb_size": list(self.rgb_size),
            "rms_error_px": self.rms_error_px,
            "num_points": self.num_points,
            "method": self.method,
            "created_at": self.created_at,
        }


def _same_aspect(a: tuple[int, int], b: tuple[int, int]) -> bool:
    ra = a[0] / a[1]
    rb = b[0] / b[1]
    return abs(ra - rb) / rb <= _ASPECT_TOLERANCE


# ── validation / parsing ─────────────────────────────────────────────────────

def _require(doc: dict, key: str) -> Any:
    if key not in doc:
        raise CalibrationError(f"missing required key '{key}'")
    return doc[key]


def _parse_size(doc: dict, key: str) -> tuple[int, int]:
    value = _require(doc, key)
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in value)):
        raise CalibrationError(f"'{key}' must be [width, height] of positive integers")
    return int(value[0]), int(value[1])


def _parse_matrix(value: Any) -> np.ndarray:
    if (not isinstance(value, (list, tuple)) or len(value) != 3
            or not all(isinstance(row, (list, tuple)) and len(row) == 3 for row in value)):
        raise CalibrationError("'homography' must be a 3x3 array")
    for row in value:
        for v in row:
            if isinstance(v, bool) or not isinstance(v, (int, float)):
                raise CalibrationError("'homography' entries must be numeric")
    H = np.array(value, dtype=np.float64)
    if not np.all(np.isfinite(H)):
        raise CalibrationError("'homography' entries must be finite")
    return H


def validate_homography(H: np.ndarray, thermal_size: tuple[int, int]) -> np.ndarray:
    """Normalise ``H`` (h33 = 1) and reject matrices that cannot be a rig mapping."""
    if abs(H[2, 2]) < _SINGULAR_EPS:
        raise CalibrationError("'homography' h33 must be non-zero")
    H = H / H[2, 2]
    scale = np.abs(H).max()
    if abs(np.linalg.det(H)) < _SINGULAR_EPS * max(scale, 1.0) ** 3:
        raise CalibrationError("'homography' is singular (not invertible)")
    w, h = thermal_size
    corners = np.array([[0, 0, 1], [w, 0, 1], [0, h, 1], [w, h, 1]], dtype=np.float64)
    denominators = corners @ H[2]
    if np.any(denominators <= 0):
        raise CalibrationError(
            "'homography' puts the horizon inside the thermal frame — "
            "points would project to infinity"
        )
    return H


def parse_calibration(doc: Any) -> FusionCalibration:
    """Validate a decoded calibration document and build a FusionCalibration."""
    if not isinstance(doc, dict):
        raise CalibrationError("calibration must be a JSON object")
    if _require(doc, "format") != CALIBRATION_FORMAT:
        raise CalibrationError(f"'format' must be '{CALIBRATION_FORMAT}'")
    if _require(doc, "version") != CALIBRATION_VERSION:
        raise CalibrationError(f"unsupported 'version' (expected {CALIBRATION_VERSION})")

    rig_id = _require(doc, "rig_id")
    if not isinstance(rig_id, str) or not rig_id.strip():
        raise CalibrationError("'rig_id' must be a non-empty string")

    thermal_size = _parse_size(doc, "thermal_size")
    rgb_size = _parse_size(doc, "rgb_size")
    H = validate_homography(_parse_matrix(_require(doc, "homography")), thermal_size)

    rms = _require(doc, "rms_error_px")
    if isinstance(rms, bool) or not isinstance(rms, (int, float)) or not math.isfinite(rms) or rms < 0:
        raise CalibrationError("'rms_error_px' must be a finite number >= 0")

    created_at = _require(doc, "created_at")
    try:
        datetime.fromisoformat(str(created_at))
    except ValueError:
        raise CalibrationError("'created_at' must be an ISO 8601 timestamp") from None

    num_points = doc.get("num_points")
    if num_points is not None and (isinstance(num_points, bool) or not isinstance(num_points, int)
                                   or num_points < MIN_POINT_PAIRS):
        raise CalibrationError(f"'num_points' must be an integer >= {MIN_POINT_PAIRS}")
    method = doc.get("method")
    if method is not None and method not in CALIBRATION_METHODS:
        raise CalibrationError(f"'method' must be one of {CALIBRATION_METHODS}")

    return FusionCalibration(
        homography=tuple(tuple(float(v) for v in row) for row in H),
        thermal_size=thermal_size,
        rgb_size=rgb_size,
        rig_id=rig_id.strip(),
        rms_error_px=float(rms),
        created_at=str(created_at),
        thermal_camera=_optional_str(doc, "thermal_camera"),
        rgb_camera=_optional_str(doc, "rgb_camera"),
        num_points=num_points,
        method=method,
    )


def _optional_str(doc: dict, key: str) -> str | None:
    value = doc.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise CalibrationError(f"'{key}' must be a string")
    return value.strip() or None


def loads_calibration(text: str | bytes) -> FusionCalibration:
    try:
        doc = json.loads(text)
    except (ValueError, UnicodeDecodeError) as exc:
        raise CalibrationError(f"calibration is not valid JSON: {exc}") from None
    return parse_calibration(doc)


def load_calibration_file(path: str | Path) -> FusionCalibration:
    path = Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CalibrationError(f"cannot read calibration file {path}: {exc}") from None
    return loads_calibration(text)


def save_calibration_file(calibration: FusionCalibration, path: str | Path) -> None:
    Path(path).write_text(json.dumps(calibration.to_dict(), indent=2) + "\n", encoding="utf-8")


# ── computing a homography ───────────────────────────────────────────────────

@dataclass(frozen=True)
class HomographyResult:
    homography: np.ndarray
    rms_error_px: float          # over RANSAC inliers
    rms_all_px: float            # over every supplied pair (diagnostic)
    inlier_mask: np.ndarray = field(repr=False)
    inliers: int = 0
    num_points: int = 0


def _as_points(points: Any, name: str) -> np.ndarray:
    arr = np.asarray(points, dtype=np.float64)
    if arr.ndim != 2 or arr.shape[1] != 2:
        raise CalibrationError(f"{name} points must be an (N, 2) array of [x, y]")
    if not np.all(np.isfinite(arr)):
        raise CalibrationError(f"{name} points must be finite numbers")
    return arr


def _is_collinear(points: np.ndarray) -> bool:
    centred = points - points.mean(axis=0)
    singular = np.linalg.svd(centred, compute_uv=False)
    return singular[0] == 0 or singular[-1] / singular[0] < _COLLINEAR_RATIO


def _has_duplicates(points: np.ndarray) -> bool:
    diffs = points[:, None, :] - points[None, :, :]
    dist = np.sqrt((diffs ** 2).sum(axis=-1))
    np.fill_diagonal(dist, np.inf)
    return bool((dist < _DUPLICATE_TOLERANCE_PX).any())


def _check_point_set(points: np.ndarray, name: str) -> None:
    if _has_duplicates(points):
        raise CalibrationError(f"{name} points contain duplicate picks")
    if _is_collinear(points):
        raise CalibrationError(f"{name} points are collinear — spread them across the frame")
    if len(points) == MIN_POINT_PAIRS:
        for skip in range(MIN_POINT_PAIRS):
            if _is_collinear(np.delete(points, skip, axis=0)):
                raise CalibrationError(
                    f"{name} points: three of the four are collinear — add or move a point"
                )


def compute_homography_from_pairs(
    thermal_points: Any,
    rgb_points: Any,
    ransac_threshold_px: float = 3.0,
) -> HomographyResult:
    """Fit the thermal→RGB homography from manually picked correspondences.

    Uses RANSAC when more than four pairs are given so a single mis-click
    does not skew the rig calibration.
    """
    thermal = _as_points(thermal_points, "thermal")
    rgb = _as_points(rgb_points, "rgb")
    if len(thermal) != len(rgb):
        raise CalibrationError("thermal and rgb must have the same number of points")
    if len(thermal) < MIN_POINT_PAIRS:
        raise CalibrationError(f"need at least {MIN_POINT_PAIRS} point pairs, got {len(thermal)}")
    _check_point_set(thermal, "thermal")
    _check_point_set(rgb, "rgb")

    method = 0 if len(thermal) == MIN_POINT_PAIRS else cv2.RANSAC
    H, mask = cv2.findHomography(
        thermal.reshape(-1, 1, 2), rgb.reshape(-1, 1, 2), method, ransac_threshold_px
    )
    if H is None or not np.all(np.isfinite(H)):
        raise CalibrationError("could not fit a homography — point set is degenerate")
    inlier_mask = (mask.ravel().astype(bool) if mask is not None
                   else np.ones(len(thermal), dtype=bool))
    inliers = int(inlier_mask.sum())
    if inliers < MIN_POINT_PAIRS:
        raise CalibrationError(
            f"only {inliers} pairs agree on a homography (need {MIN_POINT_PAIRS}) — check the picks"
        )

    projected = cv2.perspectiveTransform(thermal.reshape(1, -1, 2), H).reshape(-1, 2)
    errors = np.sqrt(((projected - rgb) ** 2).sum(axis=1))
    return HomographyResult(
        homography=H / H[2, 2],
        rms_error_px=float(np.sqrt((errors[inlier_mask] ** 2).mean())),
        rms_all_px=float(np.sqrt((errors ** 2).mean())),
        inlier_mask=inlier_mask,
        inliers=inliers,
        num_points=len(thermal),
    )


def build_calibration(
    result: HomographyResult,
    *,
    thermal_size: tuple[int, int],
    rgb_size: tuple[int, int],
    rig_id: str,
    thermal_camera: str | None = None,
    rgb_camera: str | None = None,
    method: str = "point-pairs",
    created_at: str | None = None,
) -> FusionCalibration:
    """Wrap a fitted homography into a validated calibration record."""
    doc = {
        "format": CALIBRATION_FORMAT,
        "version": CALIBRATION_VERSION,
        "rig_id": rig_id,
        "thermal_camera": thermal_camera,
        "rgb_camera": rgb_camera,
        "thermal_size": [int(thermal_size[0]), int(thermal_size[1])],
        "rgb_size": [int(rgb_size[0]), int(rgb_size[1])],
        "homography": result.homography.tolist(),
        "rms_error_px": round(result.rms_error_px, 4),
        "num_points": result.num_points,
        "method": method,
        "created_at": created_at or datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return parse_calibration({k: v for k, v in doc.items() if v is not None})


# ── checkerboard / heated-grid target ────────────────────────────────────────

def _find_board(image_bgr: np.ndarray, pattern: tuple[int, int]) -> np.ndarray | None:
    gray = image_bgr if image_bgr.ndim == 2 else cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    flags = cv2.CALIB_CB_ADAPTIVE_THRESH | cv2.CALIB_CB_NORMALIZE_IMAGE
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 30, 0.01)
    # A heated grid shows hot squares bright in thermal, so try both polarities.
    for candidate in (gray, 255 - gray):
        found, corners = cv2.findChessboardCorners(candidate, pattern, flags)
        if found:
            refined = cv2.cornerSubPix(candidate, corners, (5, 5), (-1, -1), criteria)
            return refined.reshape(-1, 2).astype(np.float64)
    return None


def pairs_from_checkerboard(
    thermal_bgr: np.ndarray,
    rgb_bgr: np.ndarray,
    pattern: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray]:
    """Detect a checkerboard / heated-grid target in both frames and pair corners.

    ``pattern`` is inner corners ``(cols, rows)``. It must be asymmetric so
    detection cannot return the grid rotated by 90°. The remaining 180°
    ordering ambiguity is resolved with the rig prior: both cameras look the
    same way, so the first→last corner direction must agree in both frames.
    """
    cols, rows = int(pattern[0]), int(pattern[1])
    if cols < 2 or rows < 2:
        raise CalibrationError("checkerboard pattern needs at least 2x2 inner corners")
    if cols == rows:
        raise CalibrationError("checkerboard pattern must be asymmetric (cols != rows)")

    thermal = _find_board(thermal_bgr, (cols, rows))
    if thermal is None:
        raise CalibrationError("checkerboard not found in thermal image")
    rgb = _find_board(rgb_bgr, (cols, rows))
    if rgb is None:
        raise CalibrationError("checkerboard not found in RGB image")

    if float(np.dot(thermal[-1] - thermal[0], rgb[-1] - rgb[0])) < 0:
        rgb = rgb[::-1].copy()
    return thermal, rgb


# ── persistence + active calibration ─────────────────────────────────────────

@dataclass(frozen=True)
class ActiveCalibration:
    calibration: FusionCalibration | None
    source: str | None          # "env" | "settings" | "database" | None
    error: str | None = None
    path: str | None = None


def store_calibration(session, calibration: FusionCalibration) -> None:
    from axalon.core.app_config import set_config

    set_config(session, CALIBRATION_CONFIG_KEY, json.dumps(calibration.to_dict()))


def _load_settings(settings: dict | None) -> dict:
    if settings is not None:
        return settings
    try:
        import yaml

        with _DEFAULT_SETTINGS_PATH.open("r") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        logger.warning("Could not read settings.yaml for fusion calibration path")
        return {}


def _from_path(raw_path: str, source: str) -> ActiveCalibration:
    path = Path(raw_path).expanduser()
    if not path.is_absolute():
        path = _REPO_ROOT / path
    try:
        return ActiveCalibration(load_calibration_file(path), source, None, str(path))
    except CalibrationError as exc:
        logger.error("Fusion calibration from %s (%s) is invalid: %s", source, path, exc)
        return ActiveCalibration(None, source, str(exc), str(path))


def resolve_active_calibration(session=None, settings: dict | None = None) -> ActiveCalibration:
    """Find the calibration the pipeline should use, and where it came from."""
    env_path = os.environ.get(CALIBRATION_ENV_VAR, "").strip()
    if env_path:
        return _from_path(env_path, "env")

    camera = (_load_settings(settings).get("camera") or {})
    settings_path = str(camera.get("fusion_calibration") or "").strip()
    if settings_path:
        return _from_path(settings_path, "settings")

    return _from_database(session)


def _from_database(session) -> ActiveCalibration:
    from axalon.core.app_config import get_config

    owns_session = session is None
    try:
        if owns_session:
            from axalon.db.session import get_session

            session = get_session()
        raw = get_config(session, CALIBRATION_CONFIG_KEY)
    except Exception as exc:
        logger.warning("Fusion calibration DB lookup failed: %s", exc)
        return ActiveCalibration(None, "database", f"database lookup failed: {exc}")
    finally:
        if owns_session and session is not None:
            session.close()
    if not raw:
        return ActiveCalibration(None, None)
    try:
        return ActiveCalibration(loads_calibration(raw), "database")
    except CalibrationError as exc:
        return ActiveCalibration(None, "database", str(exc))
