#!/usr/bin/env python3
"""
calibrate_fusion.py — Build a thermal→RGB rig calibration file.

The thermal and RGB cameras are rigidly mounted, so one homography measured
on a calibration flight maps thermal pixels to RGB pixels for every frame.
The output JSON is what `POST /settings/fusion-calibration` (Settings tab)
accepts, or what `AXALON_FUSION_CALIBRATION` / settings.yaml
`camera.fusion_calibration` can point at.

Two ways to get correspondences:

1. points — manually picked point pairs (recommended, works for any target).
   Fly over something with sharp thermal AND visual corners (heated/cooled
   metal plates, panel frame corners in the morning, a foil-taped grid),
   grab one thermal + one RGB frame captured at the same instant, and pick
   the same physical point in both. Pick at least 4 pairs (8–15 is better),
   spread across the whole frame, never three on one line.

   JSON input:
     {"rig_id": "AXL-RIG-01", "thermal_size": [640, 512], "rgb_size": [4000, 3000],
      "thermal_camera": "iTL612R Pro 25mm", "rgb_camera": "...",
      "pairs": [{"thermal": [x, y], "rgb": [x, y]}, ...]}
   CSV input (sizes/rig via flags):
     thermal_x,thermal_y,rgb_x,rgb_y

     PYTHONSAFEPATH=1 python3 scripts/calibrate_fusion.py points pairs.json -o rig.json
     PYTHONSAFEPATH=1 python3 scripts/calibrate_fusion.py points pairs.csv -o rig.json \\
         --rig-id AXL-RIG-01 --thermal-size 640x512 --rgb-size 4000x3000

2. checkerboard — a heated grid / checkerboard target visible in both frames.
   PATTERN is inner corners COLSxROWS and must be asymmetric (cols != rows).
   Both polarities are tried, so a heated grid that is bright in thermal works.

     PYTHONSAFEPATH=1 python3 scripts/calibrate_fusion.py checkerboard \\
         thermal.jpg rgb.jpg --pattern 7x6 --rig-id AXL-RIG-01 -o rig.json

The RANSAC fit rejects mis-clicked pairs; the script prints RMS reprojection
error (RGB px) and refuses to write a file when it exceeds --max-rms.
Exit codes: 0 ok, 1 invalid/degenerate input, 2 RMS above limit.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import cv2
import numpy as np

from axalon.core.fusion_calibration import (
    CalibrationError,
    build_calibration,
    compute_homography_from_pairs,
    pairs_from_checkerboard,
    save_calibration_file,
)

EXIT_INVALID = 1
EXIT_RMS_TOO_HIGH = 2
_DEFAULT_MAX_RMS = 5.0


def _parse_size(text: str | None) -> tuple[int, int] | None:
    if not text:
        return None
    try:
        w, h = text.lower().split("x")
        return int(w), int(h)
    except ValueError:
        raise CalibrationError(f"size must look like WIDTHxHEIGHT, got {text!r}") from None


def _read_pairs(path: Path) -> tuple[np.ndarray, np.ndarray, dict]:
    """Return (thermal_pts, rgb_pts, metadata) from a JSON or CSV pairs file."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CalibrationError(f"cannot read {path}: {exc}") from None

    if path.suffix.lower() == ".csv":
        rows = list(csv.DictReader(text.splitlines()))
        required = {"thermal_x", "thermal_y", "rgb_x", "rgb_y"}
        if not rows or not required.issubset(rows[0].keys()):
            raise CalibrationError(f"CSV needs header columns {sorted(required)}")
        try:
            thermal = [[float(r["thermal_x"]), float(r["thermal_y"])] for r in rows]
            rgb = [[float(r["rgb_x"]), float(r["rgb_y"])] for r in rows]
        except (TypeError, ValueError):
            raise CalibrationError("CSV contains non-numeric coordinates") from None
        return np.array(thermal), np.array(rgb), {}

    try:
        doc = json.loads(text)
    except ValueError as exc:
        raise CalibrationError(f"{path} is not valid JSON: {exc}") from None
    pairs = doc.get("pairs") if isinstance(doc, dict) else None
    if not isinstance(pairs, list):
        raise CalibrationError("JSON input needs a 'pairs' list of {thermal: [x,y], rgb: [x,y]}")
    try:
        thermal = [[float(v) for v in p["thermal"]] for p in pairs]
        rgb = [[float(v) for v in p["rgb"]] for p in pairs]
    except (KeyError, TypeError, ValueError):
        raise CalibrationError("each pair needs numeric 'thermal' and 'rgb' [x, y]") from None
    meta = {k: doc.get(k) for k in ("rig_id", "thermal_size", "rgb_size",
                                     "thermal_camera", "rgb_camera")}
    return np.array(thermal).reshape(-1, 2), np.array(rgb).reshape(-1, 2), meta


def _image_size(path: Path) -> tuple[np.ndarray, tuple[int, int]]:
    img = cv2.imread(str(path), cv2.IMREAD_COLOR)
    if img is None:
        raise CalibrationError(f"cannot read image {path}")
    return img, (img.shape[1], img.shape[0])


def _gather(args) -> tuple[np.ndarray, np.ndarray, dict, str]:
    if args.command == "points":
        thermal, rgb, meta = _read_pairs(Path(args.input))
        return thermal, rgb, meta, "point-pairs"

    pattern = _parse_size(args.pattern)
    thermal_img, thermal_size = _image_size(Path(args.thermal_image))
    rgb_img, rgb_size = _image_size(Path(args.rgb_image))
    thermal, rgb = pairs_from_checkerboard(thermal_img, rgb_img, pattern)
    return thermal, rgb, {"thermal_size": thermal_size, "rgb_size": rgb_size}, "checkerboard"


def _metadata(args, meta: dict) -> dict:
    thermal_size = _parse_size(args.thermal_size) or meta.get("thermal_size")
    rgb_size = _parse_size(args.rgb_size) or meta.get("rgb_size")
    rig_id = args.rig_id or meta.get("rig_id")
    if not rig_id:
        raise CalibrationError("rig id required (--rig-id or 'rig_id' in the JSON input)")
    if not thermal_size or not rgb_size:
        raise CalibrationError("thermal and RGB image sizes required (--thermal-size/--rgb-size)")
    return {
        "rig_id": rig_id,
        "thermal_size": tuple(thermal_size),
        "rgb_size": tuple(rgb_size),
        "thermal_camera": args.thermal_camera or meta.get("thermal_camera"),
        "rgb_camera": args.rgb_camera or meta.get("rgb_camera"),
    }


def _check_bounds(points: np.ndarray, size: tuple[int, int], name: str) -> None:
    w, h = size
    if np.any(points < 0) or np.any(points[:, 0] > w) or np.any(points[:, 1] > h):
        raise CalibrationError(f"{name} points fall outside the {w}x{h} frame")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    pts = sub.add_parser("points", help="fit from manually picked point pairs (JSON or CSV)")
    pts.add_argument("input", help="pairs .json or .csv")

    board = sub.add_parser("checkerboard", help="fit from a checkerboard / heated-grid target")
    board.add_argument("thermal_image")
    board.add_argument("rgb_image")
    board.add_argument("--pattern", required=True, help="inner corners COLSxROWS, e.g. 7x6")

    for p in (pts, board):
        p.add_argument("-o", "--output", required=True, help="calibration JSON to write")
        p.add_argument("--rig-id")
        p.add_argument("--thermal-size", help="WIDTHxHEIGHT the thermal points are in")
        p.add_argument("--rgb-size", help="WIDTHxHEIGHT the RGB points are in")
        p.add_argument("--thermal-camera")
        p.add_argument("--rgb-camera")
        p.add_argument("--ransac-threshold", type=float, default=3.0,
                       help="max reprojection error (RGB px) for a pair to count as inlier")
        p.add_argument("--max-rms", type=float, default=_DEFAULT_MAX_RMS,
                       help="refuse to write when inlier RMS error exceeds this (RGB px)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        thermal, rgb, meta, method = _gather(args)
        info = _metadata(args, meta)
        _check_bounds(np.asarray(thermal, dtype=float).reshape(-1, 2), info["thermal_size"], "thermal")
        _check_bounds(np.asarray(rgb, dtype=float).reshape(-1, 2), info["rgb_size"], "rgb")
        result = compute_homography_from_pairs(thermal, rgb, args.ransac_threshold)
        calibration = build_calibration(result, method=method, **info)
    except CalibrationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_INVALID

    print(f"Pairs: {result.num_points}  inliers: {result.inliers}")
    print(f"RMS reprojection error: {result.rms_error_px:.3f} px (inliers), "
          f"{result.rms_all_px:.3f} px (all pairs)")
    for idx in np.flatnonzero(~result.inlier_mask):
        print(f"  outlier pair #{idx}: thermal={thermal[idx].tolist()} rgb={rgb[idx].tolist()}")

    if result.rms_error_px > args.max_rms:
        print(f"error: RMS {result.rms_error_px:.3f} px exceeds --max-rms {args.max_rms}; "
              "re-pick the points", file=sys.stderr)
        return EXIT_RMS_TOO_HIGH

    save_calibration_file(calibration, args.output)
    print(f"Wrote {args.output} (rig {calibration.rig_id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
