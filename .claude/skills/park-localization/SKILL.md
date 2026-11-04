---
name: park-localization
description: Use when working on panel identification and GPS anchoring in platform/park — turning detections into addressable panels (OCR numbering for numbered parks, synthetic R{row}-C{col} grids for unnumbered ones) with real coordinates.
---

# Park Localization

Gives every detected anomaly an addressable panel ID and GPS position. Lives in `platform/park/`.

## Two park modes
- **Numbered parks** — panels carry printed numbers; use **OCR** to read them and map detections to real IDs.
- **Unnumbered parks** — no printed IDs; generate a **synthetic auto-grid** `R{row}-C{col}` from layout geometry.

## GPS anchoring (critical)
- Every anomaly must carry GPS — from EXIF or by anchoring to an orthomosaic.
- The custom drone uses the **Sensmart iTL612R Pro** thermal core, which has **no built-in GPS / no EXIF GPS**. Coordinates are injected by the companion computer (timestamp-matched against the flight log) — never assume EXIF GPS exists for these frames.
- See the project memory `drone-camera-specs` for sensor/lens details (25 mm lens, GSD ≈ 19 mm/px @ 40 m) that feed grid sizing and footprint math.

## Where to start
- Numbering logic + grid synthesis: `platform/park/`.
- Coordinate transforms: `platform/core/geo.py`.
- Output panel IDs flow into the `database` and `reporting` stages.

## Gotchas
- Keep OCR optional/fallback-safe — many parks are unnumbered.
- `settings.yaml` historically had wrong sensor dimensions; correct values: sensor 7.68 × 6.144 mm, focal 25 mm (not 13).
- Don't hardcode GSD/footprint — derive from camera + altitude (shared with `mission-planner`).
