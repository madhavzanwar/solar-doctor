"""
assign_gps_exif.py — Embed random GPS EXIF into a folder of JPEG images.

Simulates a drone flight grid over a solar park near Jodhpur, Rajasthan.
Each image gets a slightly different lat/lon as if taken from a moving drone.

Usage:
    python scripts/assign_gps_exif.py --folder /path/to/images/
    python scripts/assign_gps_exif.py --folder /home/parakh/test_mission/thermal/
"""

import sys, os
import platform  # pre-import before project path added
import argparse

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)

import random
from pathlib import Path
import piexif

random.seed(42)

# ── Base location: solar park near Jodhpur, Rajasthan ────────────────────────
BASE_LAT =  26.2389   # degrees N
BASE_LON =  73.0243   # degrees E
# Each image is ~5m apart (≈0.000045° per metre)
STEP_M   =  5.0
DEG_PER_M = 0.000009


def _to_dms_rational(deg: float) -> tuple:
    """Convert decimal degrees to EXIF DMS rational tuples."""
    d = int(abs(deg))
    m_full = (abs(deg) - d) * 60
    m = int(m_full)
    s_full = (m_full - m) * 60
    # Store as (numerator, denominator) — use 1000x precision for seconds
    return (d, 1), (m, 1), (int(s_full * 1000), 1000)


def embed_gps(image_path: Path, lat: float, lon: float) -> None:
    img_bytes = image_path.read_bytes()

    # Try to load existing EXIF; start fresh if none
    try:
        exif_dict = piexif.load(img_bytes)
    except Exception:
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}}

    exif_dict["GPS"] = {
        piexif.GPSIFD.GPSLatitudeRef:  b"N" if lat >= 0 else b"S",
        piexif.GPSIFD.GPSLatitude:     _to_dms_rational(lat),
        piexif.GPSIFD.GPSLongitudeRef: b"E" if lon >= 0 else b"W",
        piexif.GPSIFD.GPSLongitude:    _to_dms_rational(lon),
        piexif.GPSIFD.GPSAltitudeRef:  0,
        piexif.GPSIFD.GPSAltitude:     (4000, 100),  # 40 m altitude
    }

    exif_bytes = piexif.dump(exif_dict)
    piexif.insert(exif_bytes, img_bytes, str(image_path))


def main():
    parser = argparse.ArgumentParser(description="Embed random GPS EXIF into thermal images")
    parser.add_argument("--folder", required=True, help="Folder containing JPEG images")
    parser.add_argument("--base-lat", type=float, default=BASE_LAT)
    parser.add_argument("--base-lon", type=float, default=BASE_LON)
    parser.add_argument("--step-m",  type=float, default=STEP_M,
                        help="Metres between consecutive image centres")
    args = parser.parse_args()

    folder = Path(args.folder)
    images = sorted(p for p in folder.iterdir()
                    if p.suffix.lower() in {".jpg", ".jpeg"})

    if not images:
        print(f"No JPEG images found in {folder}")
        sys.exit(1)

    step_deg = args.step_m * DEG_PER_M
    print(f"Embedding GPS into {len(images)} images in {folder}")
    print(f"Base location: {args.base_lat:.6f}°N, {args.base_lon:.6f}°E")
    print(f"Step: {args.step_m} m ({step_deg:.7f}°)")
    print()

    for i, img_path in enumerate(images):
        # Lay out in a snake-grid pattern
        cols = max(1, int(len(images) ** 0.5))
        row  = i // cols
        col  = i %  cols if row % 2 == 0 else (cols - 1 - i % cols)

        lat = args.base_lat + row * step_deg + random.uniform(-0.000002, 0.000002)
        lon = args.base_lon + col * step_deg + random.uniform(-0.000002, 0.000002)

        embed_gps(img_path, lat, lon)
        print(f"  [{i+1:02d}/{len(images)}] {img_path.name}  →  {lat:.6f}°N  {lon:.6f}°E")

    print(f"\nDone. GPS embedded in {len(images)} images.")


if __name__ == "__main__":
    main()
