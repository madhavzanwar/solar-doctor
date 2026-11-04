---
name: analysis-pipeline
description: Use when working on the end-to-end inspection flow (ingest → detect → localize → persist → report) in platform/pipeline and platform/core. Read before changing how an uploaded image set becomes a fault report.
---

# Analysis Pipeline

Orchestrates a thermal image set into GPS-anchored, severity-scored fault reports.

## Flow
```
ingest (unzip / list images)
  → core/detector.py   (YOLO11m → detection dicts; see ml-detection)
  → core/fusion.py     (merge/dedupe detections, aggregate per panel)
  → core/geo.py        (GPS from EXIF or orthomosaic anchoring)
  → park/              (panel IDs: OCR numbering or synthetic R{row}-C{col})
  → db/                (persist inspection + detections; see database)
  → reporting/         (PDF / Excel / GeoJSON; see reporting)
```

## Modules
- `platform/pipeline/` — top-level orchestration (ingest → detect → report).
- `platform/core/detector.py` — YOLO wrapper, returns the canonical detection dict.
- `platform/core/fusion.py` — combines detections, per-panel aggregation.
- `platform/core/geo.py` — coordinate handling / GPS anchoring.

## Key invariants
- Every detection dict matches the contract in the `ml-detection` skill.
- Severity/color come only from `ml.src.utils` — never recomputed here.
- Every anomaly carries GPS (EXIF or orthomosaic). The custom drone has **no built-in GPS** — coordinates are injected by the companion computer (see hardware notes / `park-localization`).
- Detection runs on **thermal** images only.

## Where to start
- Adding a pipeline stage: wire it in `platform/pipeline/`, keep stages pure where possible, persist via the `database` skill's `get_session()`.
- Tests live in `tests/`; run with `PYTHONSAFEPATH=1 python -m pytest`.
