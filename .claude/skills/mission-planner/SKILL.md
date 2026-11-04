---
name: mission-planner
description: Use when working on the drone Mission Planner in website/nextjs — the frontend-only geometry engine (grid/perimeter/corridor), camera footprint math, waypoint export (Litchi CSV / KML / QGC .plan / ArduPilot .waypoints), the Leaflet map UI, and mission persistence.
---

# Mission Planner

Draw a survey area on a satellite map, set flight + camera params, preview the waypoint path, export to a flight controller, and save/reload. **Geometry runs entirely in the browser** (instant redraw; works even when the backend is asleep). The backend only persists missions.

Spec: `docs/superpowers/specs/2026-06-02-mission-planner-design.md`.

## Files
- `website/nextjs/lib/missionGeometry.ts` — pure engine: `generateGrid`, `generatePerimeter`, `generateCorridor`, `computeStats`, `computeFootprint`. Types: `LatLon`, `Waypoint`, `MissionParams`, `MissionStats`, `MissionType`.
- `website/nextjs/lib/cameras.ts` — camera presets (default **iTL612R Pro**: 7.68×6.144 mm, 25 mm, 640×512) + Custom.
- `website/nextjs/lib/waypointExport.ts` — exporters + `downloadMission`. `ExportFormat = 'litchi' | 'kml' | 'plan' | 'waypoints'`.
- `website/nextjs/components/Platform/PlanTab.tsx` — state owner (mission, camera, params, polygon; derives waypoints/stats via `useMemo`).
- `…/PlanMap.tsx` — Leaflet map (Esri satellite, `maxNativeZoom: 19`), draw tools, waypoint overlay, North/East coord-jump box.
- `…/PlanSidebar.tsx` — params sliders, camera picker, saved missions, export format picker.

## Export formats
| Format | Ext | Notes |
|--------|-----|-------|
| Litchi CSV | `.csv` | distance-triggered photos (`photo_distinterval`) |
| KML | `.kml` | LineString + per-waypoint placemarks |
| QGC `.plan` | `.plan` | QGroundControl JSON (takeoff/trigger/waypoints/RTL) |
| ArduPilot `.waypoints` | `.waypoints` | QGC WPL 110 tab-separated |

## Persistence (backend)
- `Mission` model + `POST/GET/DELETE /missions` already exist (`platform/api/app.py`, see `platform-api`/`database`).
- Frontend saves `polygon/waypoints/params/area_ha/image_count` into existing columns.

## Footprint math (defaults)
`footprint_w = sensor_w/focal × altitude`; line spacing = `footprint_w·(1−side_overlap)`; photo spacing = `footprint_h·(1−front_overlap)`. Defaults: 40 m alt, 75% front / 65% side, nadir gimbal. iTL612R Pro @ 40 m/25 mm ≈ 12.3×9.8 m, GSD ≈ 19 mm/px.

## Tests & gotchas
- Tests: `website/nextjs/tests/unit/` (vitest); run `cd website/nextjs && npm test`.
- Map provider is abstracted so Mapbox can replace Leaflet later (set `NEXT_PUBLIC_MAPBOX_TOKEN`).
- Esri tiles cap at ~z19 → keep `maxNativeZoom: 19` so Leaflet upscales instead of showing "map data not available".
