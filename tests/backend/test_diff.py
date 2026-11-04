"""Unit tests for platform/park/diff.py — build_diff() comparison logic."""
from __future__ import annotations

from axalon.park.diff import build_diff


def _det(panel_id: str, cls: str, severity: str) -> dict:
    return {"panel_id": panel_id, "class": cls, "severity": severity}


def test_empty_inputs_return_empty_groups():
    # Arrange / Act
    result = build_diff([], [])

    # Assert
    assert result == {"new": [], "resolved": [], "changed": []}


def test_new_item_present_in_b_only():
    # Arrange
    a = []
    b = [_det("R1-C1", "hot-spot-high", "CRITICAL")]

    # Act
    result = build_diff(a, b)

    # Assert
    assert result["new"] == [
        {"panel_id": "R1-C1", "class": "hot-spot-high",
         "severity_a": None, "severity_b": "CRITICAL"}
    ]
    assert result["resolved"] == []
    assert result["changed"] == []


def test_resolved_item_present_in_a_only():
    # Arrange
    a = [_det("R2-C3", "soiling", "LOW")]
    b = []

    # Act
    result = build_diff(a, b)

    # Assert
    assert result["resolved"] == [
        {"panel_id": "R2-C3", "class": "soiling",
         "severity_a": "LOW", "severity_b": None}
    ]
    assert result["new"] == []


def test_changed_item_when_severity_differs():
    # Arrange — same panel+class, severity escalated
    a = [_det("R1-C1", "hot-spot-low", "HIGH")]
    b = [_det("R1-C1", "hot-spot-low", "CRITICAL")]

    # Act
    result = build_diff(a, b)

    # Assert
    assert result["changed"] == [
        {"panel_id": "R1-C1", "class": "hot-spot-low",
         "severity_a": "HIGH", "severity_b": "CRITICAL"}
    ]
    assert result["new"] == []
    assert result["resolved"] == []


def test_identical_severity_is_not_a_change():
    # Arrange
    a = [_det("R1-C1", "module", "MEDIUM")]
    b = [_det("R1-C1", "module", "MEDIUM")]

    # Act
    result = build_diff(a, b)

    # Assert
    assert result == {"new": [], "resolved": [], "changed": []}


def test_detection_without_class_is_skipped():
    # Arrange — missing class means it cannot be keyed; should be ignored
    a = [{"panel_id": "R1-C1", "severity": "LOW"}]
    b = []

    # Act
    result = build_diff(a, b)

    # Assert
    assert result == {"new": [], "resolved": [], "changed": []}


def test_missing_panel_id_falls_back_to_placeholder():
    # Arrange — no panel_id → keyed under "R?-C?"
    a = []
    b = [{"class": "string", "severity": "CRITICAL"}]

    # Act
    result = build_diff(a, b)

    # Assert
    assert result["new"][0]["panel_id"] == "R?-C?"


def test_duplicate_panel_class_keeps_first_severity():
    # Arrange — two entries for same (panel_id, class); first wins
    a = []
    b = [
        _det("R1-C1", "soiling", "LOW"),
        _det("R1-C1", "soiling", "HIGH"),
    ]

    # Act
    result = build_diff(a, b)

    # Assert — collapsed to a single new item using the first severity
    assert len(result["new"]) == 1
    assert result["new"][0]["severity_b"] == "LOW"
