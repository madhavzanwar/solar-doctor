---
name: reporting
description: Use when generating or modifying inspection reports in platform/reporting — PDF (WeasyPrint + Jinja2), Excel (openpyxl), and GeoJSON outputs, including IEC 62446-3 compliance fields.
---

# Reporting (PDF / Excel / GeoJSON)

Renders persisted inspection data into deliverables. Lives in `platform/reporting/`; exposed via the API's `GET /report/{jobId}?format=…`.

## Outputs
- **PDF** — Jinja2 HTML templates → **WeasyPrint**. Needs system libs (`libpango-1.0-0`, `libpangoft2-1.0-0`, `libpangocairo-1.0-0`, `libcairo2`, `libgdk-pixbuf-2.0-0`) — already installed in the backend `Dockerfile`.
- **Excel** — `openpyxl` (`.xlsx`).
- **GeoJSON** — `geopandas`/`pyproj` for GPS-anchored fault layers.

## Conventions
- Severity labels and colors come from `ml.src.utils` (`SEVERITY_MAP`, `SEVERITY_COLOR_BGR`) — never recompute.
- Every fault row carries its panel ID (from `park-localization`) and GPS.
- For **IEC 62446-3** compliance, include absolute temperature and **Delta_T** per anomaly. These come from the drone's MATRIX-TEMP per-pixel matrix (iTL612R Pro) when available — see project memory `drone-camera-specs`. If temperature data is absent, leave those columns blank rather than fabricating values.

## Where to start
- Templates + serializers: `platform/reporting/`.
- Add a format: implement the serializer, wire it into the report endpoint (`platform-api`), keep the severity/GPS contract.

## Gotchas
- WeasyPrint failures are almost always missing system libs — check the Dockerfile, not the Python code.
- Large parks: stream/paginate; don't build unbounded in-memory structures.
