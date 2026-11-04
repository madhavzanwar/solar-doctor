"""make_sample_mission.py — generate a synthetic flight mission for local testing.

Writes N pairs of synthetic thermal + RGB JPEGs into tests/fixtures/sample_mission/.
Each pair carries EXIF GPS on a small grid so the map has spatially distributed markers.
Hot-spot blobs in the thermal image are tuned to trigger the YOLO 'hot-spot-*' classes
at the default 0.25 confidence threshold.
"""

from __future__ import annotations

import argparse
import math
import random
from fractions import Fraction
from pathlib import Path

import cv2
import numpy as np
import piexif
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "tests" / "fixtures" / "sample_mission"

CENTER_LAT = 19.0760  # Mumbai-ish anchor; arbitrary
CENTER_LON = 72.8777
GRID_SPACING_M = 8.0  # meters between adjacent images
IMG_W, IMG_H = 640, 512


def _to_deg_min_sec(value: float) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    value = abs(value)
    deg = int(value)
    minutes_float = (value - deg) * 60
    minutes = int(minutes_float)
    seconds = round((minutes_float - minutes) * 60 * 10000)
    return ((deg, 1), (minutes, 1), (seconds, 10000))


def _exif_for(lat: float, lon: float, altitude_m: float) -> bytes:
    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: b"N" if lat >= 0 else b"S",
        piexif.GPSIFD.GPSLatitude: _to_deg_min_sec(lat),
        piexif.GPSIFD.GPSLongitudeRef: b"E" if lon >= 0 else b"W",
        piexif.GPSIFD.GPSLongitude: _to_deg_min_sec(lon),
        piexif.GPSIFD.GPSAltitudeRef: 0,
        piexif.GPSIFD.GPSAltitude: (int(altitude_m * 100), 100),
    }
    return piexif.dump({"GPS": gps_ifd})


def _make_thermal(rng: random.Random) -> np.ndarray:
    base = np.full((IMG_H, IMG_W), 70, dtype=np.uint8)
    noise = rng.randint(-8, 8)
    img = np.clip(base.astype(int) + noise + rng.randint(-3, 3), 30, 110).astype(np.uint8)
    img = cv2.GaussianBlur(img, (15, 15), 5)
    n_hot = rng.randint(1, 3)
    for _ in range(n_hot):
        cx = rng.randint(60, IMG_W - 60)
        cy = rng.randint(60, IMG_H - 60)
        r = rng.randint(18, 32)
        intensity = rng.randint(220, 255)
        cv2.circle(img, (cx, cy), r, intensity, -1, lineType=cv2.LINE_AA)
        img = cv2.GaussianBlur(img, (9, 9), 3)
    return cv2.applyColorMap(img, cv2.COLORMAP_INFERNO)


def _make_rgb(rng: random.Random) -> np.ndarray:
    img = np.full((IMG_H, IMG_W, 3), (35, 40, 50), dtype=np.uint8)
    cols, rows = 8, 6
    pad = 12
    cell_w = (IMG_W - pad * (cols + 1)) // cols
    cell_h = (IMG_H - pad * (rows + 1)) // rows
    for r in range(rows):
        for c in range(cols):
            x1 = pad + c * (cell_w + pad)
            y1 = pad + r * (cell_h + pad)
            shade = 25 + rng.randint(0, 15)
            cv2.rectangle(img, (x1, y1), (x1 + cell_w, y1 + cell_h), (shade, shade + 5, shade + 10), -1)
            cv2.rectangle(img, (x1, y1), (x1 + cell_w, y1 + cell_h), (90, 100, 110), 1)
    return img


def _write_jpeg_with_gps(path: Path, bgr: np.ndarray, lat: float, lon: float, altitude_m: float) -> None:
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    pil = Image.fromarray(rgb)
    exif_bytes = _exif_for(lat, lon, altitude_m)
    path.parent.mkdir(parents=True, exist_ok=True)
    pil.save(path, "JPEG", quality=88, exif=exif_bytes)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--altitude", type=float, default=42.0)
    parser.add_argument("--seed", type=int, default=20260522)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    thermal_dir = OUT_DIR / "thermal"
    rgb_dir = OUT_DIR / "rgb"

    side = int(math.ceil(math.sqrt(args.count)))
    meters_per_deg_lat = 111_320.0
    for i in range(args.count):
        row, col = divmod(i, side)
        dlat = (row * GRID_SPACING_M) / meters_per_deg_lat
        dlon = (col * GRID_SPACING_M) / (meters_per_deg_lat * math.cos(math.radians(CENTER_LAT)))
        lat = CENTER_LAT + dlat
        lon = CENTER_LON + dlon

        thermal = _make_thermal(rng)
        rgb = _make_rgb(rng)
        name = f"img_{i + 1:03d}.jpg"
        _write_jpeg_with_gps(thermal_dir / name, thermal, lat, lon, args.altitude)
        _write_jpeg_with_gps(rgb_dir / name, rgb, lat, lon, args.altitude)

    print(f"Wrote {args.count} pairs to {OUT_DIR}")


if __name__ == "__main__":
    main()
