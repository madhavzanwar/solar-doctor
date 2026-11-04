"""
numbering.py — Panel ID extraction via OCR for numbered solar parks.

Uses EasyOCR to read panel/string labels from RGB drone images,
then parses them into structured panel identifiers.

Supported ID schemes:
  - C4-28       → {type: "cell", row: 4, number: 28}
  - S3-12       → {type: "string", row: 3, number: 12}
  - R3-C7       → {type: "grid", row: 3, col: 7}
  - INV-02/STR-05 → {type: "inv_string", inv: 2, str: 5}
  - A-103       → {type: "alpha_row", row: "A", number: 103}
"""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

from ml.src.utils import get_logger

logger = get_logger("axalon.numbering")

# Regex patterns for known solar park ID schemes (extend as needed)
_PANEL_ID_PATTERNS = [
    # C4-28, C12-003
    (re.compile(r'^C(\d{1,3})-(\d{1,4})$', re.IGNORECASE),
     lambda m: {"type": "cell", "row": int(m.group(1)), "number": int(m.group(2))}),
    # S3-12, S01-007
    (re.compile(r'^S(\d{1,3})-(\d{1,4})$', re.IGNORECASE),
     lambda m: {"type": "string", "row": int(m.group(1)), "number": int(m.group(2))}),
    # R3-C7
    (re.compile(r'^R(\d{1,3})-C(\d{1,4})$', re.IGNORECASE),
     lambda m: {"type": "grid", "row": int(m.group(1)), "col": int(m.group(2))}),
    # INV-02/STR-05 or INV02-STR05
    (re.compile(r'^INV[-_]?(\d{1,3})[-/]STR[-_]?(\d{1,3})$', re.IGNORECASE),
     lambda m: {"type": "inv_string", "inv": int(m.group(1)), "str": int(m.group(2))}),
    # A-103, B-27 (alpha row)
    (re.compile(r'^([A-Z])-(\d{1,4})$', re.IGNORECASE),
     lambda m: {"type": "alpha_row", "row": m.group(1).upper(), "number": int(m.group(2))}),
]


class PanelNumberOCR:
    """Extract and parse panel IDs from RGB drone images using EasyOCR."""

    def __init__(self, languages: list[str] | None = None, gpu: bool = True) -> None:
        """
        Args:
            languages: OCR languages (default: English only).
            gpu:       Use GPU for OCR if available.
        """
        try:
            import easyocr
            self.reader = easyocr.Reader(languages or ["en"], gpu=gpu)
            logger.info("EasyOCR initialized (gpu=%s)", gpu)
        except ImportError:
            logger.warning("easyocr not installed — install with: pip install easyocr")
            self.reader = None

    def extract_ids_from_rgb(
        self,
        rgb_image: np.ndarray,
        min_confidence: float = 0.7,
    ) -> list[dict]:
        """Run OCR on an RGB image and return recognized panel IDs.

        Args:
            rgb_image:      BGR image array (as loaded by OpenCV).
            min_confidence: Minimum OCR confidence to accept.

        Returns:
            List of dicts:
            {
                "text": "C4-28",
                "bbox_ocr": [[x1,y1],[x2,y1],[x2,y2],[x1,y2]],
                "center": [cx, cy],
                "confidence": 0.94,
                "parsed": {"type": "cell", "row": 4, "number": 28} | None
            }
        """
        if self.reader is None:
            return []

        import cv2
        rgb_for_ocr = cv2.cvtColor(rgb_image, cv2.COLOR_BGR2RGB)
        raw_results = self.reader.readtext(rgb_for_ocr)

        found = []
        for bbox_ocr, text, conf in raw_results:
            if conf < min_confidence:
                continue
            text_clean = text.strip().replace(" ", "").upper()
            parsed = self.parse_panel_id(text_clean)
            if parsed is None:
                continue  # not a panel ID format

            xs = [pt[0] for pt in bbox_ocr]
            ys = [pt[1] for pt in bbox_ocr]
            found.append({
                "text": text_clean,
                "bbox_ocr": bbox_ocr,
                "center": [int(sum(xs) / 4), int(sum(ys) / 4)],
                "confidence": float(conf),
                "parsed": parsed,
            })

        logger.info("OCR found %d panel IDs", len(found))
        return found

    def parse_panel_id(self, text: str) -> dict | None:
        """Parse a raw text string into a structured panel ID dict.

        Returns None if the text does not match any known pattern.
        """
        for pattern, extractor in _PANEL_ID_PATTERNS:
            m = pattern.match(text)
            if m:
                return extractor(m)
        return None

    def panel_id_to_string(self, parsed: dict) -> str:
        """Convert a parsed panel ID back to a canonical string form."""
        t = parsed.get("type")
        if t == "cell":
            return f"C{parsed['row']}-{parsed['number']}"
        if t == "string":
            return f"S{parsed['row']}-{parsed['number']}"
        if t == "grid":
            return f"R{parsed['row']}-C{parsed['col']}"
        if t == "inv_string":
            return f"INV-{parsed['inv']:02d}/STR-{parsed['str']:02d}"
        if t == "alpha_row":
            return f"{parsed['row']}-{parsed['number']}"
        return str(parsed)
