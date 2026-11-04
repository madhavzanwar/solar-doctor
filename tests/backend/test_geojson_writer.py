"""Unit tests for platform/reporting/geojson_writer.py — GeoJSON export."""
from __future__ import annotations

import json

from axalon.reporting.geojson_writer import write_geojson


def _batch_result_with_gps() -> dict:
    return {
        "park_id": "PARK_01",
        "flight_date": "2026-04-11",
        "results": [
            {
                "image_id": "img_001",
                "detections": [
                    {
                        "panel_id": "R1-C1",
                        "class": "hot-spot-high",
                        "class_id": 10,
                        "severity": "CRITICAL",
                        "confidence": 0.912345,
                        "gps": {"lat": 19.076, "lon": 72.877},
                    },
                    {
                        "panel_id": "R1-C2",
                        "class": "soiling",
                        "class_id": 7,
                        "severity": "LOW",
                        "confidence": 0.55,
                        "detection_gps": {"lat": 19.077, "lon": 72.878},
                    },
                ],
            },
            {
                "image_id": "img_002",
                "detections": [
                    # No GPS → must be skipped
                    {
                        "panel_id": "R2-C1",
                        "class": "module",
                        "severity": "MEDIUM",
                        "confidence": 0.7,
                    },
                ],
            },
        ],
    }


def test_geojson_writer_produces_valid_featurecollection(tmp_path):
    # Arrange
    out = tmp_path / "anomalies.geojson"

    # Act
    written = write_geojson(_batch_result_with_gps(), out)
    data = json.loads(written.read_text())

    # Assert
    assert data["type"] == "FeatureCollection"
    assert isinstance(data["features"], list)
    for feature in data["features"]:
        assert feature["type"] == "Feature"
        assert feature["geometry"]["type"] == "Point"


def test_geojson_writer_includes_only_detections_with_gps(tmp_path):
    # Arrange
    out = tmp_path / "anomalies.geojson"

    # Act
    data = json.loads(write_geojson(_batch_result_with_gps(), out).read_text())

    # Assert — 2 of 3 detections have GPS
    assert len(data["features"]) == 2
    assert data["properties"]["total_anomalies"] == 2


def test_geojson_writer_uses_lon_lat_order(tmp_path):
    # Arrange
    out = tmp_path / "anomalies.geojson"

    # Act
    data = json.loads(write_geojson(_batch_result_with_gps(), out).read_text())

    # Assert — GeoJSON coordinates are [lon, lat]
    first = data["features"][0]
    assert first["geometry"]["coordinates"] == [72.877, 19.076]


def test_geojson_writer_sets_severity_and_class_properties(tmp_path):
    # Arrange
    out = tmp_path / "anomalies.geojson"

    # Act
    data = json.loads(write_geojson(_batch_result_with_gps(), out).read_text())

    # Assert
    props = data["features"][0]["properties"]
    assert props["severity"] == "CRITICAL"
    assert props["anomaly_class"] == "hot-spot-high"
    assert props["panel_id"] == "R1-C1"
    assert props["confidence"] == 0.912  # rounded to 3 dp


def test_geojson_writer_handles_empty_results(tmp_path):
    # Arrange
    out = tmp_path / "empty.geojson"

    # Act
    data = json.loads(write_geojson({"park_id": "P", "results": []}, out).read_text())

    # Assert
    assert data["features"] == []
    assert data["properties"]["total_anomalies"] == 0
