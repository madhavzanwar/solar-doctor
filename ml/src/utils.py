"""
utils.py — shared helpers for visualisation, severity mapping, and YOLO I/O.

Intentionally import-light so notebooks can do `from src.utils import *`
without pulling in heavy deps at the top of every cell.
"""

from __future__ import annotations

import logging
import warnings
from pathlib import Path
from typing import Sequence

import cv2
import matplotlib.pyplot as plt
import numpy as np

# ── Canonical class list ────────────────────────────────────────────────────
CANONICAL_CLASSES: list[str] = [
    "cell",            # 0
    "cell-multi",      # 1
    "module",          # 2
    "string",          # 3
    "bypass-diode",    # 4
    "offline-module",  # 5
    "vegetation-shading",  # 6
    "soiling",         # 7
    "short-circuit",   # 8
    "hot-spot-low",    # 9
    "hot-spot-high",   # 10
]

CLASS2ID: dict[str, int] = {c: i for i, c in enumerate(CANONICAL_CLASSES)}
ID2CLASS: dict[int, str] = {i: c for i, c in enumerate(CANONICAL_CLASSES)}

# ── Severity mapping ────────────────────────────────────────────────────────
SEVERITY_MAP: dict[str, str] = {
    "hot-spot-high":       "CRITICAL",
    "bypass-diode":        "CRITICAL",
    "string":              "CRITICAL",
    "hot-spot-low":        "HIGH",
    "offline-module":      "HIGH",
    "short-circuit":       "HIGH",
    "cell":                "MEDIUM",
    "cell-multi":          "MEDIUM",
    "module":              "MEDIUM",
    "vegetation-shading":  "LOW",
    "soiling":             "LOW",
}

SEVERITY_COLOR_BGR: dict[str, tuple[int, int, int]] = {
    "CRITICAL": (0,   0,   255),   # red
    "HIGH":     (0,   165, 255),   # orange
    "MEDIUM":   (0,   255, 255),   # yellow
    "LOW":      (255, 0,   0),     # blue
}

# ── IEC TS 62446-3:2017 — Classes of Abnormality (CoA) ──────────────────────
# Table 4: CoA 1 = OK, CoA 2 = thermal abnormality, CoA 3 = safety-relevant
IEC_COA_MAP: dict[str, int] = {
    "hot-spot-high":       3,   # >40 K — safety-relevant (Annex C, Example 9b)
    "bypass-diode":        3,   # Heated junction box / diode failure (Annex C, Example 10–12)
    "string":              3,   # String open circuit — prompt action (Annex C, Example 1–3)
    "cell-multi":          2,   # Multi-cell anomaly — check and rectify
    "short-circuit":       2,   # Module short-circuit pattern (Annex C, Example 2)
    "offline-module":      2,   # Module in open circuit (Annex C, Example 1–3)
    "cell":                2,   # Single cell 10–40 K (Annex C, Example 7a)
    "module":              2,   # Module-level extended anomaly
    "hot-spot-low":        2,   # 10–40 K single cell (Annex C, Example 7a)
    "soiling":             2,   # Shading/soiling — clean (Annex C, Example 8)
    "vegetation-shading":  2,   # Vegetation shading
}

IEC_COA_LABEL: dict[int, str] = {
    1: "CoA 1 — No Abnormality",
    2: "CoA 2 — Thermal Abnormality",
    3: "CoA 3 — Safety-Relevant Thermal Abnormality",
}

# Recommended action per CoA (IEC 62446-3 Table 4)
IEC_COA_ACTION: dict[int, str] = {
    1: "No action required.",
    2: "Check the cause and, if necessary, rectify in a reasonable period.",
    3: "Prompt interruption of operation, check the cause and rectify in a reasonable period.",
}

# ── IEC 62446-3 §7.4 — Abnormality type for temperature normalization ────────
# "point": localized (<few mm²), x=1.5 for PV modules
# "extended": cell-size or larger, x=1.0 (linear)
IEC_ABNORMALITY_TYPE: dict[str, str] = {
    "bypass-diode":        "point",    # localized at diode/junction-box contact
    "hot-spot-high":       "extended", # cell-area or larger at >40 K
    "hot-spot-low":        "extended", # cell-area at 10–40 K
    "cell":                "extended",
    "cell-multi":          "extended",
    "module":              "extended",
    "string":              "extended",
    "offline-module":      "extended",
    "short-circuit":       "extended",
    "soiling":             "extended",
    "vegetation-shading":  "extended",
}

# ΔT range at 1 000 W/m² from Annex C (min_K, max_K); None = not defined
IEC_DELTA_T_RANGE_K: dict[str, tuple[float | None, float | None]] = {
    "cell":                (10.0, 40.0),
    "cell-multi":          (10.0, None),
    "hot-spot-low":        (10.0, 40.0),
    "hot-spot-high":       (40.0, None),
    "module":              (2.0,  7.0),
    "offline-module":      (2.0,  7.0),
    "short-circuit":       (2.0,  7.0),
    "string":              (2.0,  7.0),
    "bypass-diode":        (3.0,  None),
    "soiling":             (0.0,  7.0),
    "vegetation-shading":  (0.0,  None),
}


def normalize_delta_t(
    delta_t_measured: float,
    irradiance_wm2: float,
    abnormality_type: str = "extended",
    nominal_irradiance_wm2: float = 1000.0,
) -> float:
    """Normalize a measured ΔT to nominal irradiance per IEC 62446-3 §7.4.

    Formula: ΔT₂ = (G₂ / G₁)^x × ΔT₁
        x = 1.5 for point abnormalities in PV modules
        x = 1.0 for extended-area abnormalities (linear)

    Args:
        delta_t_measured:      Measured temperature difference (K or °C delta).
        irradiance_wm2:        Actual in-plane irradiance at time of measurement (W/m²).
        abnormality_type:      "point" or "extended" (from IEC_ABNORMALITY_TYPE).
        nominal_irradiance_wm2: Target irradiance for normalization (default 1000 W/m²).

    Returns:
        ΔT normalized to nominal irradiance.

    Raises:
        ValueError: if irradiance_wm2 ≤ 0.
    """
    if irradiance_wm2 <= 0:
        raise ValueError(f"irradiance_wm2 must be > 0, got {irradiance_wm2}")
    x = 1.5 if abnormality_type == "point" else 1.0
    return (nominal_irradiance_wm2 / irradiance_wm2) ** x * delta_t_measured

# ── YOLO label I/O ──────────────────────────────────────────────────────────

def read_yolo_label(label_path: Path) -> list[tuple[int, float, float, float, float]]:
    """Return list of (class_id, cx, cy, w, h) from a YOLO .txt label file."""
    boxes: list[tuple[int, float, float, float, float]] = []
    if not label_path.exists() or label_path.stat().st_size == 0:
        return boxes
    for line in label_path.read_text().splitlines():
        parts = line.strip().split()
        if len(parts) != 5:
            continue
        try:
            cid, cx, cy, w, h = int(parts[0]), *map(float, parts[1:])
            boxes.append((cid, cx, cy, w, h))
        except ValueError:
            logging.warning("Malformed label line in %s: %r", label_path, line)
    return boxes


def write_yolo_label(
    label_path: Path,
    boxes: list[tuple[int, float, float, float, float]],
) -> None:
    """Write (class_id, cx, cy, w, h) list to a YOLO .txt label file."""
    label_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{cid} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}" for cid, cx, cy, w, h in boxes]
    label_path.write_text("\n".join(lines) + ("\n" if lines else ""))


# ── Bounding-box drawing ────────────────────────────────────────────────────

def yolo_to_pixel(
    cx: float, cy: float, w: float, h: float, img_w: int, img_h: int
) -> tuple[int, int, int, int]:
    """Convert normalised YOLO coords → pixel (x1, y1, x2, y2)."""
    x1 = int((cx - w / 2) * img_w)
    y1 = int((cy - h / 2) * img_h)
    x2 = int((cx + w / 2) * img_w)
    y2 = int((cy + h / 2) * img_h)
    return x1, y1, x2, y2


def draw_yolo_boxes(
    img_bgr: np.ndarray,
    boxes: list[tuple[int, float, float, float, float]],
    color: tuple[int, int, int] = (0, 255, 0),
    thickness: int = 2,
    labels: Sequence[str] | None = None,
    font_scale: float = 0.45,
) -> np.ndarray:
    """Draw YOLO-format boxes on a BGR image copy. Returns the annotated copy."""
    out = img_bgr.copy()
    h, w = out.shape[:2]
    for cid, cx, cy, bw, bh in boxes:
        x1, y1, x2, y2 = yolo_to_pixel(cx, cy, bw, bh, w, h)
        cv2.rectangle(out, (x1, y1), (x2, y2), color, thickness)
        if labels is not None and 0 <= cid < len(labels):
            cv2.putText(
                out, labels[cid], (x1, max(y1 - 4, 12)),
                cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, 1, cv2.LINE_AA,
            )
    return out


def draw_detections_severity(
    img_bgr: np.ndarray,
    detections: list[dict],
    thickness: int = 2,
    font_scale: float = 0.45,
) -> np.ndarray:
    """Draw detections coloured by severity.

    Each detection dict must have keys: bbox [x1,y1,x2,y2], class, severity, confidence.
    """
    out = img_bgr.copy()
    for det in detections:
        x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
        color = SEVERITY_COLOR_BGR.get(det["severity"], (128, 128, 128))
        cv2.rectangle(out, (x1, y1), (x2, y2), color, thickness)
        label = f"{det['class']} {det['confidence']:.2f}"
        cv2.putText(
            out, label, (x1, max(y1 - 4, 12)),
            cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, 1, cv2.LINE_AA,
        )
    return out


# ── Image grid helpers ──────────────────────────────────────────────────────

def show_image_grid(
    images: list[np.ndarray],
    titles: list[str] | None = None,
    ncols: int = 3,
    figsize_per_cell: tuple[float, float] = (4.0, 3.5),
) -> None:
    """Display a list of BGR images in a matplotlib grid (converts BGR→RGB)."""
    n = len(images)
    nrows = (n + ncols - 1) // ncols
    fig, axes = plt.subplots(
        nrows, ncols,
        figsize=(figsize_per_cell[0] * ncols, figsize_per_cell[1] * nrows),
    )
    axes = np.array(axes).flatten()
    for i, ax in enumerate(axes):
        if i < n:
            ax.imshow(cv2.cvtColor(images[i], cv2.COLOR_BGR2RGB))
            if titles:
                ax.set_title(titles[i], fontsize=8)
        ax.axis("off")
    plt.tight_layout()
    plt.show()


def load_bgr(path: Path, target_size: tuple[int, int] | None = None) -> np.ndarray:
    """Load an image as BGR; optionally resize. Raises FileNotFoundError if missing."""
    img = cv2.imread(str(path))
    if img is None:
        raise FileNotFoundError(f"Could not load image: {path}")
    if target_size is not None:
        img = cv2.resize(img, target_size, interpolation=cv2.INTER_LINEAR)
    return img


# ── Logging setup ───────────────────────────────────────────────────────────

def get_logger(name: str = "solar_thermal") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("[%(levelname)s] %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger
