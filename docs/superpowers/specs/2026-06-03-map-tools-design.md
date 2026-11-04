# Mission Planner — Map Tools (Area B)

**Date:** 2026-06-03
**Status:** Approved (brainstorm). Frontend-only, in the Plan tab. Closes Hammer "site boundary / measure" gap.

## Goals
1. **Import site boundary** — load a `.geojson`/`.json`/`.kml` polygon as the survey area; fit the map to it.
2. **Export boundary** — download the current drawn area as GeoJSON or KML.
3. **Measure tool** — toggle on the map; click points to read running distance + enclosed area; clear.

## Non-Goals
- Named-site persistence in a backend (export/import files is enough for v1; localStorage optional later).
- Freehand annotations/labels (phase 2).

## Components

### `lib/boundaryIO.ts` (pure, tested)
- `parseGeoJson(text: string): LatLon[]` — first Polygon/LineString ring → `LatLon[]` (drops closing dup).
- `parseKml(text: string): LatLon[]` — first `<coordinates>` block (Polygon/LineString) via `DOMParser`; parses `lon,lat[,alt]` tuples.
- `parseBoundary(text, filename): LatLon[]` — dispatch by extension/content.
- `toGeoJson(points: LatLon[]): string` — a `Polygon` Feature.
- `toKml(points: LatLon[]): string` — a `<Polygon>` Placemark.
- Validation: ≥3 points or throw a clear error; ignore Z; clamp lat/lon ranges.

### `PlanTab.tsx`
- `handleImportBoundary(file: File)` — read text, `parseBoundary`, `setPolygon`, bump `fitKey` (forces a map fit-to-bounds), toast on parse error.
- `handleExportBoundary(format: 'geojson' | 'kml')` — `toGeoJson`/`toKml(polygon)` → download (reuse the blob-download pattern from `waypointExport`).
- New state `fitKey: number`; pass `fitKey` to `PlanMap` and `onImportBoundary`/`onExportBoundary` to `PlanSidebar`.

### `PlanSidebar.tsx`
- New **"Site boundary"** section: an Import `<input type=file accept=".geojson,.json,.kml">` and Export GeoJSON / Export KML buttons (disabled when no polygon).

### `PlanMap.tsx`
- **Boundary outline:** render the `polygon` prop as a faint outline layer (its own `LayerGroup`) so an imported area is visible before waypoints compute.
- **Fit on import:** `useEffect(..., [fitKey])` → `map.fitBounds(polygon)` when `fitKey` changes (not on every draw).
- **Measure tool:** a "Measure" toggle button overlay (top-left). When active, map clicks append measure points (separate `LayerGroup`): draw the polyline, show total distance (haversine) and, with ≥3 points, the enclosed area (shoelace, m²→ha) in a small readout; a Clear button; toggling off removes the layer. Self-contained — no new props.

## Testing (vitest)
- `parseGeoJson`/`parseKml` round-trip with `toGeoJson`/`toKml` (point count + coords within tolerance).
- `parseBoundary` dispatches by extension; bad input throws.
- Reuse jsdom `DOMParser` for the KML test.

## Rollout
Frontend-only → `git push origin main` (Vercel). No backend/Supabase change.
