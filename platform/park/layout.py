"""
layout.py — Auto-detect solar park grid layout from drone images.

For unnumbered solar parks, infers panel rows/columns from RGB imagery
using contour detection and grid-fitting. Assigns synthetic panel IDs
in "R{row}-C{col}" format anchored to real GPS coordinates.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from ml.src.utils import get_logger

logger = get_logger("axalon.layout")


class ParkLayoutDetector:
    """Detect solar panel grid layout from RGB images."""

    def __init__(
        self,
        min_panel_area: int = 500,
        max_panel_area: int = 50_000,
        row_cluster_tolerance_px: int = 30,
    ) -> None:
        self.min_panel_area = min_panel_area
        self.max_panel_area = max_panel_area
        self.row_cluster_tolerance_px = row_cluster_tolerance_px

    def detect_panels(self, rgb_bgr: np.ndarray) -> list[dict]:
        """Detect rectangular solar panel regions in an RGB image.

        Uses Canny edge detection + contour filtering for panel rectangles.

        Returns:
            List of panel dicts: {"bbox": [x1,y1,x2,y2], "center": [cx,cy], "area": int}
        """
        gray = cv2.cvtColor(rgb_bgr, cv2.COLOR_BGR2GRAY)
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blur, 50, 150)

        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        edges = cv2.dilate(edges, kernel, iterations=1)

        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        panels = []
        for c in contours:
            area = cv2.contourArea(c)
            if not (self.min_panel_area <= area <= self.max_panel_area):
                continue

            # Filter by rectangularity (solar panels are rectangular)
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.04 * peri, True)
            if len(approx) not in (4, 5):  # 4-5 vertices = rectangle-like
                continue

            x, y, w, h = cv2.boundingRect(c)
            aspect = max(w, h) / max(min(w, h), 1)
            if aspect > 6:  # too elongated — likely a row boundary, not a panel
                continue

            cx, cy = x + w // 2, y + h // 2
            panels.append({"bbox": [x, y, x + w, y + h], "center": [cx, cy], "area": int(area)})

        logger.info("Detected %d panel candidates", len(panels))
        return panels

    def assign_grid_ids(self, panels: list[dict]) -> list[dict]:
        """Assign synthetic R{row}-C{col} IDs to detected panels.

        Clusters panels by Y-coordinate into rows, then assigns column
        indices by X-coordinate within each row.

        Returns:
            Same panel list with "panel_id" added to each dict.
        """
        if not panels:
            return panels

        # Sort by Y (top to bottom = row 1, 2, ...)
        sorted_panels = sorted(panels, key=lambda p: p["center"][1])

        # Cluster into rows by Y-proximity
        rows: list[list[dict]] = []
        current_row: list[dict] = [sorted_panels[0]]
        ref_y = sorted_panels[0]["center"][1]

        for panel in sorted_panels[1:]:
            if abs(panel["center"][1] - ref_y) <= self.row_cluster_tolerance_px:
                current_row.append(panel)
            else:
                rows.append(current_row)
                current_row = [panel]
                ref_y = panel["center"][1]
        rows.append(current_row)

        # Within each row, sort by X (left to right = col 1, 2, ...)
        result = []
        for row_idx, row in enumerate(rows, start=1):
            row_sorted = sorted(row, key=lambda p: p["center"][0])
            for col_idx, panel in enumerate(row_sorted, start=1):
                result.append({**panel, "panel_id": f"R{row_idx}-C{col_idx}"})

        logger.info("Grid: %d rows, %d total panels", len(rows), len(result))
        return result

    def build_layout(
        self,
        rgb_images: list[np.ndarray],
        gps_coords: list[dict] | None = None,
    ) -> dict:
        """Build a complete park layout from a series of RGB images.

        Args:
            rgb_images: List of RGB drone images covering the park.
            gps_coords: Optional list of {"lat", "lon"} per image (same order).

        Returns:
            Park layout dict (see AXALON_PLATFORM_SPEC.md §6.2).
        """
        all_panels: list[dict] = []
        seen_centers: set[tuple[int, int]] = set()
        for idx, img in enumerate(rgb_images):
            panels = self.detect_panels(img)
            gps = gps_coords[idx] if gps_coords and idx < len(gps_coords) else None
            for p in panels:
                # Deduplicate panels at the same position across images (snap to 20px grid)
                key = (round(p["center"][0] / 20), round(p["center"][1] / 20))
                if key in seen_centers:
                    continue
                seen_centers.add(key)
                p["source_image_idx"] = idx
                p["source_gps"] = gps
                all_panels.append(p)

        all_panels = self.assign_grid_ids(all_panels)

        panel_map = {p["panel_id"]: {
            "bbox_image": p["bbox"],
            "center": p["center"],
            "gps": p.get("source_gps"),
        } for p in all_panels}

        # Unique row count
        rows = sorted(set(int(p["panel_id"].split("-C")[0][1:]) for p in all_panels))

        return {
            "mode": "auto-grid",
            "total_panels": len(all_panels),
            "rows": len(rows),
            "panel_map": panel_map,
        }
