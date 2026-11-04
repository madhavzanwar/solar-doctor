"""
setup_ism_mission.py — Build a full test mission from real ISM thermal images.

Creates /home/parakh/ism_mission/
  thermal/  — 50 real ISM images (upscaled to 640×480, GPS embedded)
  rgb/      — matching synthetic RGB with 4×6 solar panel grid

Run:
    python scripts/setup_ism_mission.py
"""

import sys, os, random
import platform  # pre-import before project path

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)

import json
from pathlib import Path
import cv2
import numpy as np
import piexif

random.seed(42)
np.random.seed(42)

# ── Config ────────────────────────────────────────────────────────────────────
ISM_IMAGES = Path("/home/parakh/Desktop/AxalonSystems/ml/Datasets/InfraredSolarModules/2020-02-14_InfraredSolarModules/InfraredSolarModules/images")
ISM_META   = ISM_IMAGES.parent / "module_metadata.json"
OUT_DIR    = Path("/home/parakh/ism_mission")
N_IMAGES   = 50
IMG_W, IMG_H = 640, 480

# Panel grid for RGB
GRID_ROWS, GRID_COLS = 4, 6
MARGIN, PAD = 40, 8

# GPS base — solar park near Jodhpur
BASE_LAT, BASE_LON = 26.2389, 73.0243
DEG_PER_M = 0.000009
STEP_M = 5.0


# ── Helpers ───────────────────────────────────────────────────────────────────

def panel_rects():
    uw = IMG_W - 2 * MARGIN
    uh = IMG_H - 2 * MARGIN
    pw = (uw - (GRID_COLS - 1) * PAD) // GRID_COLS
    ph = (uh - (GRID_ROWS - 1) * PAD) // GRID_ROWS
    rects = []
    for r in range(GRID_ROWS):
        for c in range(GRID_COLS):
            x1 = MARGIN + c * (pw + PAD)
            y1 = MARGIN + r * (ph + PAD)
            rects.append((x1, y1, x1 + pw, y1 + ph))
    return rects


def make_rgb(rects) -> np.ndarray:
    img = np.full((IMG_H, IMG_W, 3), (30, 35, 25), dtype=np.uint8)
    for x1, y1, x2, y2 in rects:
        base = 90 + random.randint(-10, 10)
        color = (base - 20, base, base + 10)
        cv2.rectangle(img, (x1, y1), (x2, y2), color, -1)
        pw, ph = x2 - x1, y2 - y1
        lc = (color[0] - 15, color[1] - 15, color[2] - 15)
        for d in [1, 2]:
            cv2.line(img, (x1, y1 + ph * d // 3), (x2, y1 + ph * d // 3), lc, 1)
            cv2.line(img, (x1 + pw * d // 3, y1), (x1 + pw * d // 3, y2), lc, 1)
        cv2.rectangle(img, (x1, y1), (x2, y2), (160, 170, 160), 1)
    return img


def _to_dms(deg: float):
    d = int(abs(deg))
    m_full = (abs(deg) - d) * 60
    m = int(m_full)
    s = (m_full - m) * 60
    return (d, 1), (m, 1), (int(s * 1000), 1000)


def embed_gps(path: Path, lat: float, lon: float):
    data = path.read_bytes()
    try:
        exif = piexif.load(data)
    except Exception:
        exif = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}}
    exif["GPS"] = {
        piexif.GPSIFD.GPSLatitudeRef:  b"N",
        piexif.GPSIFD.GPSLatitude:     _to_dms(lat),
        piexif.GPSIFD.GPSLongitudeRef: b"E",
        piexif.GPSIFD.GPSLongitude:    _to_dms(lon),
        piexif.GPSIFD.GPSAltitudeRef:  0,
        piexif.GPSIFD.GPSAltitude:     (4000, 100),
    }
    piexif.insert(piexif.dump(exif), data, str(path))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    thermal_dir = OUT_DIR / "thermal"
    rgb_dir     = OUT_DIR / "rgb"
    thermal_dir.mkdir(parents=True, exist_ok=True)
    rgb_dir.mkdir(parents=True, exist_ok=True)

    # Pick images with actual anomalies (not No-Anomaly) first, pad with rest
    meta = json.loads(ISM_META.read_text())
    anomaly = [k for k, v in meta.items() if v["anomaly_class"] != "No-Anomaly"]
    normal  = [k for k, v in meta.items() if v["anomaly_class"] == "No-Anomaly"]
    random.shuffle(anomaly); random.shuffle(normal)
    selected = (anomaly + normal)[:N_IMAGES]

    rects = panel_rects()
    step  = STEP_M * DEG_PER_M
    cols  = max(1, int(N_IMAGES ** 0.5))

    print(f"Building ISM mission ({N_IMAGES} images) → {OUT_DIR}")
    print(f"  Anomaly images : {min(len(anomaly), N_IMAGES)}")
    print(f"  Panel grid     : {GRID_ROWS}×{GRID_COLS}")
    print()

    for i, key in enumerate(selected):
        stem = f"{i+1:03d}"
        src  = ISM_IMAGES / meta[key]["image_filepath"].split("/")[-1]

        # Thermal: upscale real ISM image to 640×480
        img = cv2.imread(str(src))
        if img is None:
            print(f"  [SKIP] {src.name} not found")
            continue
        thermal = cv2.resize(img, (IMG_W, IMG_H), interpolation=cv2.INTER_CUBIC)
        # Apply inferno colormap for thermal look
        gray = cv2.cvtColor(thermal, cv2.COLOR_BGR2GRAY)
        thermal_colored = cv2.applyColorMap(gray, cv2.COLORMAP_INFERNO)
        t_path = thermal_dir / f"{stem}.jpg"
        cv2.imwrite(str(t_path), thermal_colored, [cv2.IMWRITE_JPEG_QUALITY, 95])

        # GPS: snake-grid layout
        row = i // cols
        col = i % cols if row % 2 == 0 else (cols - 1 - i % cols)
        lat = BASE_LAT + row * step + random.uniform(-0.000002, 0.000002)
        lon = BASE_LON + col * step + random.uniform(-0.000002, 0.000002)
        embed_gps(t_path, lat, lon)

        # RGB: synthetic panel grid
        rgb = make_rgb(rects)
        cv2.imwrite(str(rgb_dir / f"{stem}.jpg"), rgb, [cv2.IMWRITE_JPEG_QUALITY, 95])

        cls = meta[key]["anomaly_class"]
        print(f"  [{i+1:02d}/{N_IMAGES}] {stem}.jpg  {cls:<20}  {lat:.6f}°N  {lon:.6f}°E")

    print(f"\nDone. Mission ready at: {OUT_DIR}")
    print(f"\nDashboard settings:")
    print(f"  Flight Folder Path : {OUT_DIR}")
    print(f"  Park ID            : ISM_PARK")
    print(f"  Drone Altitude     : 40")


if __name__ == "__main__":
    main()
