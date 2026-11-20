"""Test report generation (ReportLab PDF, Excel, GeoJSON, JSON) and download endpoints."""
from __future__ import annotations

import json
from fastapi.testclient import TestClient
from solardoctor.api.app import app


def test_reports_list_and_formats():
    client = TestClient(app)
    # 1. List available reports
    resp = client.get("/api/v1/reports")
    assert resp.status_code == 200
    reports = resp.json()
    assert isinstance(reports, list)
    assert len(reports) >= 1

    r0 = reports[0]
    report_id = r0["id"]

    # 2. Download PDF (ReportLab)
    r_pdf = client.get(f"/api/v1/report/{report_id}?format=pdf")
    assert r_pdf.status_code == 200
    assert r_pdf.headers["content-type"] == "application/pdf"
    assert len(r_pdf.content) > 1000

    # 3. Download Excel (.xlsx)
    r_excel = client.get(f"/api/v1/report/{report_id}?format=excel")
    assert r_excel.status_code == 200
    assert "openxmlformats" in r_excel.headers["content-type"]
    assert len(r_excel.content) > 1000

    # 4. Download GeoJSON (.geojson)
    r_geo = client.get(f"/api/v1/report/{report_id}?format=geojson")
    assert r_geo.status_code == 200
    assert "geo+json" in r_geo.headers["content-type"]
    geo_data = r_geo.json()
    assert geo_data.get("type") == "FeatureCollection"
    assert "features" in geo_data

    # 5. Download JSON
    r_json = client.get(f"/api/v1/report/{report_id}?format=json")
    assert r_json.status_code == 200
    assert "application/json" in r_json.headers["content-type"]
