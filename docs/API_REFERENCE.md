# API Reference

Base URL: `http://localhost:8000`

Recommended local start:

```bash
./run.sh api
```

Interactive docs:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## POST /inspect

Inspect a single thermal image and an optional RGB companion image.

Request: `multipart/form-data`

- `thermal_image` required file
- `rgb_image` optional file
- `park_id` optional string, default `unknown`
- `park_mode` optional string, default `auto`
- `altitude_m` optional float, default `40.0`

Response `200`:

```json
{
  "job_id": "AXL-20260411-143022-thermal_001",
  "status": "completed",
  "total_detections": 3,
  "summary": {
    "CRITICAL": 1,
    "HIGH": 1,
    "MEDIUM": 1,
    "LOW": 0
  },
  "detections": [
    {
      "class": "hot-spot-high",
      "severity": "CRITICAL",
      "confidence": 0.91,
      "panel_id": "R3-C7",
      "bbox": [100, 200, 150, 250],
      "gps": {"lat": 28.45, "lon": 77.12}
    }
  ]
}
```

Validation notes:

- Allowed image extensions: `.jpg`, `.jpeg`, `.png`, `.tiff`, `.tif`
- Max upload size per image: `50 MB`
- `park_id` allows only letters, digits, `_`, `-`
- `altitude_m` must be between `1` and `500`

## POST /batch

Queue a background batch job from a ZIP archive.

Request: `multipart/form-data`

- `images` required file
  ZIP archive containing the mission folder contents
- `park_id` optional string, default `unknown`
- `park_mode` optional string, default `auto`
- `altitude_m` optional float, default `40.0`

Response `202`:

```json
{
  "job_id": "batch-1234abcd",
  "status": "queued",
  "message": "Batch job queued. Poll GET /status/{job_id} for progress."
}
```

Validation notes:

- Only `.zip` uploads are accepted
- Max ZIP size: `2 GB`
- Max ZIP members: `10,000`

## GET /status/{job_id}

Return progress for a queued, running, completed, or failed job.

Response `200`:

```json
{
  "job_id": "batch-1234abcd",
  "status": "processing",
  "progress": 0.45,
  "processed": 19,
  "total": 42
}
```

Possible `status` values:

- `queued`
- `processing`
- `completed`
- `failed`

When a job fails, the response also includes a sanitized `error` field.

## GET /report/{job_id}

Download a generated report for a completed batch job.

Query parameter:

- `format` one of `pdf`, `json`, `excel`, `geojson`

Examples:

```bash
curl "http://localhost:8000/report/batch-1234abcd?format=pdf" -o inspection_report.pdf
curl "http://localhost:8000/report/batch-1234abcd?format=excel" -o inspection_report.xlsx
curl "http://localhost:8000/report/batch-1234abcd?format=geojson" -o park_anomaly_map.geojson
```

Notes:

- Reports are available only after job completion
- PDF output depends on WeasyPrint and system libraries from `docs/INSTALLATION.md`

## GET /parks

List all parks currently stored in the database.

Response `200`:

```json
{
  "parks": [
    {
      "id": "PARK_01",
      "name": "Demo Park",
      "mode": "auto",
      "total_panels": 396,
      "rows": 18,
      "cols": 22
    }
  ],
  "total": 1
}
```

## GET /park/{park_id}

Return one park plus inspection history.

Response `200`:

```json
{
  "park_id": "PARK_01",
  "name": "Demo Park",
  "mode": "auto",
  "total_panels": 396,
  "rows": 18,
  "cols": 22,
  "total_inspections": 2,
  "inspections": [
    {
      "id": "batch-1234abcd",
      "flight_date": "2026-04-25",
      "total_images": 42,
      "total_detections": 9,
      "summary": {
        "CRITICAL": 1,
        "HIGH": 2,
        "MEDIUM": 4,
        "LOW": 2
      }
    }
  ]
}
```

## GET /health

Health and dependency summary.

Response `200`:

```json
{
  "status": "ok",
  "model": "YOLOv8s",
  "weights": "ml/checkpoints/best.pt",
  "version": "1.0.0",
  "db": "ok",
  "parks_in_db": 1
}
```
