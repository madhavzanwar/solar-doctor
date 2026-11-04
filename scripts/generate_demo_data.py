"""
Generate synthetic demo mission data for Axalon platform testing.

Creates:
  demo_mission/
    thermal/  — 12 thermal-looking images (heatmap colormap, simulated hot spots)
    rgb/      — 12 matching RGB images with a 4×6 solar panel grid

Stems match (001..012) so the ingest pipeline pairs them automatically.
Panel grid is large enough for contour detection (min_panel_area=500px²).
"""

import sys
import os

# Pre-import stdlib platform before project's ./platform/ can shadow it
import platform  # noqa: F401

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _ROOT)

import random
import json
from pathlib import Path

import cv2
import numpy as np

random.seed(42)
np.random.seed(42)

# ── Config ────────────────────────────────────────────────────────────────────
OUT_DIR    = Path("/home/parakh/demo_mission")
N_IMAGES   = 12          # flight images
IMG_W      = 640
IMG_H      = 480
GRID_ROWS  = 4
GRID_COLS  = 6           # 24 panels per image

PANEL_PAD  = 8           # gap between panels (px)
MARGIN     = 40          # border margin (px)

# ── Helpers ───────────────────────────────────────────────────────────────────

def _panel_rects(img_w: int, img_h: int, rows: int, cols: int, margin: int, pad: int):
    """Return (x1,y1,x2,y2) for each panel in a rows×cols grid."""
    usable_w = img_w - 2 * margin
    usable_h = img_h - 2 * margin
    pw = (usable_w - (cols - 1) * pad) // cols
    ph = (usable_h - (rows - 1) * pad) // rows
    rects = []
    for r in range(rows):
        for c in range(cols):
            x1 = margin + c * (pw + pad)
            y1 = margin + r * (ph + pad)
            rects.append((x1, y1, x1 + pw, y1 + ph))
    return rects, pw, ph


def make_rgb(image_idx: int, rects) -> np.ndarray:
    """Synthetic aerial RGB: dark ground + blue-grey solar panels."""
    img = np.full((IMG_H, IMG_W, 3), (30, 35, 25), dtype=np.uint8)  # dark earth

    for i, (x1, y1, x2, y2) in enumerate(rects):
        # Panel base colour — slight variation per panel
        base = 90 + random.randint(-10, 10)
        color = (base - 20, base, base + 10)          # bluish-grey
        cv2.rectangle(img, (x1, y1), (x2, y2), color, -1)

        # Cell grid lines on panel surface
        pw, ph = x2 - x1, y2 - y1
        line_col = (color[0] - 15, color[1] - 15, color[2] - 15)
        for div in [1, 2]:
            cv2.line(img, (x1, y1 + ph * div // 3), (x2, y1 + ph * div // 3), line_col, 1)
            cv2.line(img, (x1 + pw * div // 3, y1), (x1 + pw * div // 3, y2), line_col, 1)

        # Panel border (bright edge — helps contour detection)
        cv2.rectangle(img, (x1, y1), (x2, y2), (160, 170, 160), 1)

    return img


def make_thermal(image_idx: int, rects) -> np.ndarray:
    """Synthetic thermal IR image: panels as warm regions, hot-spots injected."""
    base = np.random.randint(20, 50, (IMG_H, IMG_W), dtype=np.uint8)

    # Panels are warmer than background
    for x1, y1, x2, y2 in rects:
        warmth = random.randint(120, 160)
        base[y1:y2, x1:x2] = np.clip(
            base[y1:y2, x1:x2] + warmth, 0, 255
        ).astype(np.uint8)

    # Inject 2-4 hot spots (simulate anomalies) per image
    n_spots = random.randint(2, 4)
    for _ in range(n_spots):
        rx1, ry1, rx2, ry2 = random.choice(rects)
        # Hot spot: small bright region inside a panel
        sx = random.randint(rx1 + 5, rx2 - 10)
        sy = random.randint(ry1 + 5, ry2 - 10)
        sw = random.randint(8, 20)
        sh = random.randint(8, 20)
        cv2.rectangle(base, (sx, sy), (sx + sw, sy + sh),
                      random.randint(210, 255), -1)

    # Apply Gaussian blur for realistic thermal look
    blurred = cv2.GaussianBlur(base, (7, 7), 2)

    # Colorise with COLORMAP_INFERNO (thermal look)
    thermal_bgr = cv2.applyColorMap(blurred, cv2.COLORMAP_INFERNO)
    return thermal_bgr


def main():
    thermal_dir = OUT_DIR / "thermal"
    rgb_dir     = OUT_DIR / "rgb"
    thermal_dir.mkdir(parents=True, exist_ok=True)
    rgb_dir.mkdir(parents=True, exist_ok=True)

    rects, pw, ph = _panel_rects(IMG_W, IMG_H, GRID_ROWS, GRID_COLS, MARGIN, PANEL_PAD)
    print(f"Panel size: {pw}×{ph}px  (area={pw*ph}px²)  —  {len(rects)} panels per image")

    for i in range(1, N_IMAGES + 1):
        stem = f"{i:03d}"

        rgb = make_rgb(i, rects)
        cv2.imwrite(str(rgb_dir / f"{stem}.jpg"), rgb)

        thermal = make_thermal(i, rects)
        cv2.imwrite(str(thermal_dir / f"{stem}.jpg"), thermal)

        print(f"  [{i:02d}/{N_IMAGES}] {stem}.jpg written")

    print(f"\nDemo data ready at: {OUT_DIR}")
    print(f"  thermal/ : {len(list(thermal_dir.iterdir()))} images")
    print(f"  rgb/     : {len(list(rgb_dir.iterdir()))} images")
    print(f"\nIn the dashboard:")
    print(f"  Flight Folder Path : {OUT_DIR}")
    print(f"  Park ID            : DEMO_PARK")
    print(f"  Drone Altitude     : 40")


if __name__ == "__main__":
    main()
