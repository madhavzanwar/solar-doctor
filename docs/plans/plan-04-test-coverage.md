# Plan 04 — Expand Test Coverage to 80%
**Priority:** P1 | **Effort:** Large
**Goal:** Ensure every significant module has unit + integration tests; hit 80%+ coverage.

---

## Current Test Inventory

```
tests/backend/
  test_analytics_overview.py
  test_api_contract.py
  test_app_config.py
  test_auth.py
  test_corrections.py
  test_corrections_in_report.py
  test_fault_comments.py
  test_grid_unit.py
  test_inventory.py
  test_job_persistence.py
  test_map_renderer.py
  test_missions.py
  test_object_store.py
  test_park_grid_endpoint.py
  test_pipeline_unit.py
  test_projects.py
  test_temp_extractor.py
  test_track.py
  test_trend.py
  test_trend_endpoint.py
```

**Missing test files:**

| Module | Test file to create |
|--------|-------------------|
| `platform/park/locator.py` | `tests/backend/test_locator.py` |
| `platform/park/diff.py` (endpoints) | `tests/backend/test_diff_endpoint.py` |
| `platform/core/fusion.py` | `tests/backend/test_fusion.py` |
| `platform/core/geo.py` | `tests/backend/test_geo.py` |
| `platform/pipeline/tracking.py` | `tests/backend/test_tracking.py` |
| `platform/reporting/geojson_writer.py` | `tests/backend/test_geojson_writer.py` |
| `platform/reporting/report.py` (PDF/Excel) | `tests/backend/test_report_outputs.py` |
| Batch job + /status + /report flow | `tests/backend/test_batch_flow.py` |
| Ortho endpoints | `tests/backend/test_ortho.py` |

---

## How to Measure Coverage

```bash
pip install pytest-cov
python3 -m pytest tests/backend/ --cov=platform --cov-report=term-missing --cov-fail-under=80
```

Run this first to see the baseline, then add tests until it passes.

---

## Test Writing Guidelines

### AAA Pattern (Arrange-Act-Assert)

```python
def test_geo_extracts_gps_from_exif(tmp_path):
    # Arrange
    img = _make_test_image_with_gps(tmp_path, lat=19.076, lon=72.877)

    # Act
    result = extract_gps(img)

    # Assert
    assert result["latitude"] == pytest.approx(19.076, abs=1e-4)
    assert result["longitude"] == pytest.approx(72.877, abs=1e-4)
```

### Use the existing conftest.py fixtures

```python
# tests/backend/conftest.py already provides:
# - client: TestClient (FastAPI test client)
# - db_session: SQLAlchemy session on fresh in-memory SQLite
# - auth_headers: {"Authorization": "Bearer test-key"}
# Use these fixtures; do not create new DB sessions in tests.
```

---

## Tests to Write — Priority Order

### 1. `test_geo.py` — GPS extraction

```python
def test_extract_gps_from_exif_jpg():
def test_extract_gps_returns_none_when_no_exif():
def test_extract_gps_handles_corrupt_exif():
def test_synthetic_gps_returns_valid_coords():
```

### 2. `test_fusion.py` — Thermal/RGB fusion

```python
def test_fusion_returns_none_when_rgb_missing():
def test_fusion_projects_bbox_correctly():
def test_fusion_handles_different_resolutions():
```

### 3. `test_geojson_writer.py` — GeoJSON output

```python
def test_geojson_writer_produces_valid_featurecollection():
def test_geojson_writer_includes_all_detections():
def test_geojson_writer_uses_detection_gps_coordinates():
def test_geojson_writer_sets_severity_property():
```

### 4. `test_report_outputs.py` — PDF and Excel

```python
def test_excel_report_contains_all_detections(tmp_path):
def test_excel_report_has_severity_column(tmp_path):
def test_json_report_matches_schema(tmp_path):
def test_pdf_report_generates_without_error(tmp_path):
```

### 5. `test_batch_flow.py` — Full batch job lifecycle

```python
def test_batch_job_creates_job_record(client, auth_headers, tmp_path):
def test_batch_status_returns_running(client, auth_headers):
def test_batch_status_returns_done_after_completion(client, auth_headers):
def test_batch_report_download_json(client, auth_headers):
def test_batch_report_download_excel(client, auth_headers):
```

### 6. `test_ortho.py` — Ortho tile server

```python
def test_upload_ortho_accepts_geotiff(client, auth_headers, tmp_path):
def test_list_orthos_returns_uploaded(client, auth_headers):
def test_get_ortho_tile_returns_png(client, auth_headers):
def test_delete_ortho_removes_file(client, auth_headers):
```

### 7. `test_diff_endpoint.py` — Inspection diff

```python
def test_diff_two_identical_inspections_returns_empty_diff():
def test_diff_new_fault_appears_in_added():
def test_diff_resolved_fault_appears_in_removed():
```

### 8. `test_tracking.py` — Fault lifecycle tracking

```python
def test_tracking_marks_new_fault_as_open():
def test_tracking_marks_missing_fault_as_stale():
def test_tracking_marks_stale_fault_as_resolved():
```

---

## Done When

- [ ] `pytest --cov=platform --cov-fail-under=80` passes
- [ ] All new test files follow AAA pattern
- [ ] No test uses mocked DB (use real in-memory SQLite via conftest)
- [ ] CI `tests/backend/` step still passes in under 3 minutes
