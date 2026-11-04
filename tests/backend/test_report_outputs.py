"""Unit tests for platform/reporting/report.py — JSON, Excel, PDF outputs."""
from __future__ import annotations

import json

import pytest

from axalon.reporting.report import (
    compute_revenue_loss,
    generate_excel_report,
    generate_json_report,
    generate_pdf_report,
)


def _batch_result() -> dict:
    return {
        "park_id": "PARK_01",
        "flight_date": "2026-04-11",
        "total_images": 2,
        "total_detections": 3,
        "results": [
            {
                "image_id": "img_001",
                "detections": [
                    {"panel_id": "R1-C1", "class": "hot-spot-high",
                     "severity": "CRITICAL", "confidence": 0.91, "class_id": 10},
                    {"panel_id": "R1-C2", "class": "soiling",
                     "severity": "LOW", "confidence": 0.5, "class_id": 7},
                ],
            },
            {
                "image_id": "img_002",
                "detections": [
                    {"panel_id": "R2-C1", "class": "string",
                     "severity": "CRITICAL", "confidence": 0.8, "class_id": 3},
                ],
            },
        ],
    }


def test_json_report_round_trips(tmp_path):
    # Arrange
    out = tmp_path / "report.json"

    # Act
    written = generate_json_report(_batch_result(), out)
    data = json.loads(written.read_text())

    # Assert
    assert data["park_id"] == "PARK_01"
    assert data["total_detections"] == 3
    assert len(data["results"]) == 2


def test_json_report_includes_corrections(tmp_path):
    # Arrange
    out = tmp_path / "report.json"
    corrections = [{"id": 1, "class": "module"}]

    # Act
    data = json.loads(generate_json_report(_batch_result(), out, corrections).read_text())

    # Assert
    assert data["corrections"] == corrections


def test_excel_report_generates_workbook_with_sheets(tmp_path):
    # Arrange
    openpyxl = pytest.importorskip("openpyxl")
    out = tmp_path / "report.xlsx"

    # Act
    written = generate_excel_report(_batch_result(), out)
    wb = openpyxl.load_workbook(str(written))

    # Assert — Summary sheet + park sheet exist
    assert "Summary" in wb.sheetnames
    assert "PARK_01" in wb.sheetnames


def test_excel_report_lists_all_detections(tmp_path):
    # Arrange
    openpyxl = pytest.importorskip("openpyxl")
    out = tmp_path / "report.xlsx"

    # Act
    generate_excel_report(_batch_result(), out)
    wb = openpyxl.load_workbook(str(out))
    ws = wb["PARK_01"]

    # Assert — header row + 3 detection rows
    data_rows = [r for r in ws.iter_rows(min_row=2, values_only=True) if any(r)]
    assert len(data_rows) == 3


def test_excel_report_has_severity_column(tmp_path):
    # Arrange
    openpyxl = pytest.importorskip("openpyxl")
    out = tmp_path / "report.xlsx"

    # Act
    generate_excel_report(_batch_result(), out)
    ws = openpyxl.load_workbook(str(out))["PARK_01"]
    headers = [c.value for c in ws[1]]

    # Assert
    assert "Severity" in headers


def test_compute_revenue_loss_counts_unique_critical_panels():
    # Arrange — two CRITICAL detections on distinct known panels, one LOW
    dets = [
        {"panel_id": "R1-C1", "severity": "CRITICAL"},
        {"panel_id": "R2-C1", "severity": "HIGH"},
        {"panel_id": "R3-C1", "severity": "LOW"},
        {"panel_id": "R?-C?", "severity": "CRITICAL"},  # unknown panel ignored
    ]
    economics = {"cost_per_kwh_usd": 0.10, "panel_capacity_kw": 0.5, "peak_sun_hours_per_day": 4.0}

    # Act
    loss = compute_revenue_loss(dets, economics)

    # Assert — 2 affected panels × 0.5 kW × 4 h × $0.10 = $0.40
    assert loss == pytest.approx(0.40)


def test_pdf_report_generates_without_error(tmp_path):
    # Arrange — skip cleanly when weasyprint isn't installed in the env
    pytest.importorskip("weasyprint")
    pytest.importorskip("jinja2")
    out = tmp_path / "report.pdf"

    # Act
    written = generate_pdf_report(_batch_result(), out)

    # Assert
    assert written.exists()
    assert written.stat().st_size > 0
