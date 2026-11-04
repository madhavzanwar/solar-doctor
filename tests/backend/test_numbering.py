"""Unit tests for platform/park/numbering.py — panel-ID parsing.

PanelNumberOCR.__init__ loads EasyOCR (heavy / downloads models), so these tests
construct the object via __new__ to exercise the pure parsing methods directly.
"""
from __future__ import annotations

import numpy as np
import pytest

from axalon.park.numbering import PanelNumberOCR


@pytest.fixture
def ocr() -> PanelNumberOCR:
    # Bypass __init__ (no EasyOCR) — only the pure parse methods are under test.
    return PanelNumberOCR.__new__(PanelNumberOCR)


@pytest.mark.parametrize(
    "text,expected",
    [
        ("C4-28", {"type": "cell", "row": 4, "number": 28}),
        ("S3-12", {"type": "string", "row": 3, "number": 12}),
        ("R3-C7", {"type": "grid", "row": 3, "col": 7}),
        ("INV-02/STR-05", {"type": "inv_string", "inv": 2, "str": 5}),
        ("INV02-STR05", {"type": "inv_string", "inv": 2, "str": 5}),
        ("A-103", {"type": "alpha_row", "row": "A", "number": 103}),
    ],
)
def test_parse_panel_id_recognizes_known_schemes(ocr, text, expected):
    # Act
    parsed = ocr.parse_panel_id(text)

    # Assert
    assert parsed == expected


@pytest.mark.parametrize("text", ["", "HELLO", "1234", "C4", "ZZ-9-9", "R3C7"])
def test_parse_panel_id_returns_none_for_unknown(ocr, text):
    assert ocr.parse_panel_id(text) is None


@pytest.mark.parametrize(
    "parsed,expected",
    [
        ({"type": "cell", "row": 4, "number": 28}, "C4-28"),
        ({"type": "string", "row": 3, "number": 12}, "S3-12"),
        ({"type": "grid", "row": 3, "col": 7}, "R3-C7"),
        ({"type": "inv_string", "inv": 2, "str": 5}, "INV-02/STR-05"),
        ({"type": "alpha_row", "row": "A", "number": 103}, "A-103"),
    ],
)
def test_panel_id_to_string_round_trips(ocr, parsed, expected):
    assert ocr.panel_id_to_string(parsed) == expected


def test_panel_id_to_string_unknown_type_falls_back_to_repr(ocr):
    # Arrange — an unrecognized type returns str(parsed)
    weird = {"type": "mystery", "x": 1}

    # Act / Assert
    assert ocr.panel_id_to_string(weird) == str(weird)


def test_extract_ids_returns_empty_when_reader_unavailable(ocr):
    # Arrange — simulate "easyocr not installed" state
    ocr.reader = None
    image = np.zeros((10, 10, 3), dtype=np.uint8)

    # Act
    result = ocr.extract_ids_from_rgb(image)

    # Assert
    assert result == []


class _StubReader:
    """Stand-in for an EasyOCR reader returning canned (bbox, text, conf) rows."""

    def __init__(self, rows):
        self._rows = rows

    def readtext(self, _img):
        return self._rows


def test_extract_ids_filters_by_confidence_and_format(ocr):
    # Arrange — one valid panel ID, one low-confidence, one non-panel string
    bbox = [[0, 0], [10, 0], [10, 10], [0, 10]]
    ocr.reader = _StubReader([
        (bbox, "C4-28", 0.95),     # valid, high confidence -> kept
        (bbox, "S1-2", 0.40),      # valid format but below min_confidence -> dropped
        (bbox, "HELLO", 0.99),     # high confidence but not a panel ID -> dropped
    ])
    image = np.zeros((20, 20, 3), dtype=np.uint8)

    # Act
    found = ocr.extract_ids_from_rgb(image, min_confidence=0.7)

    # Assert — only the valid, confident panel ID survives, fully parsed
    assert len(found) == 1
    assert found[0]["text"] == "C4-28"
    assert found[0]["parsed"] == {"type": "cell", "row": 4, "number": 28}
    assert found[0]["center"] == [5, 5]
