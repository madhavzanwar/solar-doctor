"""
geojson_writer.py — Export anomaly detections as GeoJSON.

Compatible with QGIS, Google Earth, and ArcGIS for field navigation.
"""

from __future__ import annotations

import json
from pathlib import Path


def write_geojson(batch_result: dict, output_path: str | Path) -> Path:
    """Write a GeoJSON FeatureCollection of anomaly locations.

    Only detections with GPS coordinates are included.

    Args:
        batch_result: Batch inspection result dict from orchestrator.
        output_path:  Output .geojson file path.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    features = []
    for result in batch_result.get("results", []):
        for det in result.get("detections", []):
            gps = det.get("gps") or det.get("detection_gps")
            if not gps or "lat" not in gps or "lon" not in gps:
                continue

            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [gps["lon"], gps["lat"]],  # GeoJSON is [lon, lat]
                },
                "properties": {
                    "panel_id": det.get("panel_id", "N/A"),
                    "anomaly_class": det.get("class", ""),
                    "class_id": det.get("class_id", -1),
                    "severity": det.get("severity", ""),
                    "confidence": round(det.get("confidence", 0), 3),
                    "image_id": result.get("image_id", ""),
                    "park_id": batch_result.get("park_id", ""),
                    "flight_date": batch_result.get("flight_date", ""),
                },
            })

    geojson = {
        "type": "FeatureCollection",
        "features": features,
        "properties": {
            "park_id": batch_result.get("park_id", ""),
            "total_anomalies": len(features),
            "flight_date": batch_result.get("flight_date", ""),
        },
    }

    output_path.write_text(json.dumps(geojson, indent=2))
    return output_path
