# Platform Phase 6 — RGB Fusion Display, Ortho Tile Map & Park Map PNG Export

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Wire three deferred features: (A) show the fused RGB annotated image in the Inspect tab when an RGB image is uploaded alongside thermal; (B) add an interactive Leaflet ortho tile map with panel-level detection markers to the Park Map tab; (C) add server-side PNG export of the park fault grid with a download button.

**Architecture:**
- (A) Backend exposes `rgb_filename` in the `/inspect` response; frontend adds an optional second file input and renders the fused result via the existing `GET /results/{job_id}/{filename}` endpoint.
- (B) `react-leaflet` renders the ortho as an XYZ tile layer (tiles served by the existing `GET /park/{id}/ortho/{name}/tiles/{z}/{x}/{y}.png` endpoint, which is already CORS-enabled and auth-free); panel GPS points from the park grid become `CircleMarker` overlays.
- (C) A new `platform/core/map_renderer.py` uses Pillow to paint a grid PNG; a new `GET /park/{id}/grid/png` endpoint serves it; ParkMapTab downloads it as a file.

**Tech Stack:** Python/FastAPI, Pillow (already installed), react-leaflet + leaflet + @types/leaflet (new), Next.js 14 dynamic imports (ssr:false for Leaflet), Vitest, Playwright, pytest

---

## Files Created / Modified

| File | Action | Purpose |
|------|--------|---------|
| `platform/api/app.py` | Modify | Add `rgb_filename` to `/inspect` response; add `GET /park/{id}/grid/png` |
| `platform/core/map_renderer.py` | **Create** | Pillow grid PNG renderer |
| `tests/backend/test_api_contract.py` | Modify | Test `rgb_filename` in inspect response; test PNG endpoint |
| `tests/backend/test_map_renderer.py` | **Create** | Unit tests for `render_grid_png()` |
| `website/nextjs/lib/api.ts` | Modify | Fix `OrthoMeta.bounds` type; add `parkGridPng()` method; type `InspectResult` |
| `website/nextjs/components/Platform/InspectTab.tsx` | Modify | Add RGB file input; show fused image |
| `website/nextjs/components/Platform/OrthoMap.tsx` | **Create** | Leaflet map: ortho tile layer + detection markers |
| `website/nextjs/components/Platform/DynamicOrthoMap.tsx` | **Create** | SSR-safe wrapper (`dynamic(..., {ssr:false})`) |
| `website/nextjs/components/Platform/ParkMapTab.tsx` | Modify | Fetch ortho list; add upload section; Grid/Map toggle |
| `website/nextjs/app/platform/layout.tsx` | Modify | Import leaflet CSS |
| `website/nextjs/tests/unit/OrthoMap.test.tsx` | **Create** | Vitest unit test for OrthoMap |
| `website/nextjs/tests/e2e/golden_path.spec.ts` | Modify | Add PNG download assertion to golden path |

---

## Task 1 — Expose `rgb_filename` in `/inspect` Response

**Files:**
- Modify: `platform/api/app.py` (around line 410 — the `/inspect` JSONResponse)
- Modify: `tests/backend/test_api_contract.py`

The orchestrator already writes `{stem}_rgb_annotated.jpg` to the job directory when an RGB image is provided. The `/inspect` endpoint builds the result dict but strips it out before returning. This task adds it back.

- [ ] **Step 1: Write the failing test**

Add to `tests/backend/test_api_contract.py`:

```python
# ── /inspect rgb_filename ─────────────────────────────────────────────────────

THERMAL_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "tests/fixtures/sample_mission/thermal/img_001.jpg"
)
RGB_FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "tests/fixtures/sample_mission/rgb/img_001.jpg"
)

def test_inspect_single_thermal_returns_job_id(client):
    """Thermal-only inspect: shape check."""
    with open(THERMAL_FIXTURE, "rb") as f:
        r = client.post(
            "/inspect",
            files={"thermal_image": ("img_001.jpg", f, "image/jpeg")},
            data={"park_id": "TEST"},
        )
    assert r.status_code == 200
    body = r.json()
    assert "job_id" in body
    assert "detections" in body
    assert body.get("rgb_filename", "") == ""


def test_inspect_with_rgb_returns_rgb_filename(client):
    """Thermal+RGB inspect: rgb_filename is non-empty."""
    with open(THERMAL_FIXTURE, "rb") as ft, open(RGB_FIXTURE, "rb") as fr:
        r = client.post(
            "/inspect",
            files={
                "thermal_image": ("img_001.jpg", ft, "image/jpeg"),
                "rgb_image": ("img_001.jpg", fr, "image/jpeg"),
            },
            data={"park_id": "TEST"},
        )
    assert r.status_code == 200
    body = r.json()
    assert "rgb_filename" in body
    assert body["rgb_filename"].endswith("_rgb_annotated.jpg")
```

Also add `from pathlib import Path` at the top of the file if not already present.

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/parakh/Desktop/AxalonSystems
PYTHONSAFEPATH=1 .venv/bin/python -m pytest tests/backend/test_api_contract.py::test_inspect_with_rgb_returns_rgb_filename -v
```

Expected: FAIL — `AssertionError: assert 'rgb_filename' in {...}` (key absent from response).

- [ ] **Step 3: Add `rgb_filename` to the `/inspect` JSONResponse**

In `platform/api/app.py`, find the `return JSONResponse(content={...})` at the end of `async def inspect_pair` (around line 411). Replace it:

```python
    return JSONResponse(content={
        "job_id": result["job_id"],
        "status": "completed",
        "total_detections": result["total_detections"],
        "summary": result["summary"],
        "detections": result["detections"],
        "rgb_filename": Path(result.get("annotated_rgb") or "").name,
    })
```

`Path("").name` is `""`, so thermal-only inspections return `"rgb_filename": ""`.

- [ ] **Step 4: Run both new tests**

```bash
PYTHONSAFEPATH=1 .venv/bin/python -m pytest tests/backend/test_api_contract.py::test_inspect_single_thermal_returns_job_id tests/backend/test_api_contract.py::test_inspect_with_rgb_returns_rgb_filename -v
```

Expected: both PASS.

- [ ] **Step 5: Run full backend suite to check no regressions**

```bash
PYTHONSAFEPATH=1 .venv/bin/python -m pytest tests/backend/ -q
```

Expected: 50 passed (48 existing + 2 new).

- [ ] **Step 6: Commit**

```bash
git add platform/api/app.py tests/backend/test_api_contract.py
git commit -m "feat(inspect): expose rgb_filename in /inspect response"
```

---

## Task 2 — RGB Upload Input & Fused Image Display in InspectTab

**Files:**
- Modify: `website/nextjs/lib/api.ts`
- Modify: `website/nextjs/components/Platform/InspectTab.tsx`

- [ ] **Step 1: Fix `InspectResult` type and add `rgb_filename`**

In `website/nextjs/lib/api.ts`, replace:

```typescript
export type InspectResult = Record<string, unknown>
```

with:

```typescript
export type InspectResult = {
  job_id: string
  status: string
  total_detections: number
  summary: {
    by_severity?: { CRITICAL: number; HIGH: number; MEDIUM: number; LOW: number }
    CRITICAL?: number
    HIGH?: number
    MEDIUM?: number
    LOW?: number
    [k: string]: unknown
  }
  detections: Array<{
    class: string
    class_id: number
    confidence: number
    bbox: [number, number, number, number]
    bbox_norm: [number, number, number, number]
    severity: string
    [k: string]: unknown
  }>
  rgb_filename?: string
  [k: string]: unknown
}
```

- [ ] **Step 2: Add RGB state and input to InspectTab**

In `website/nextjs/components/Platform/InspectTab.tsx`, add a second file state alongside `inspectFile`:

After `const [inspectFile, setInspectFile] = useState<File | null>(null)` (or similar), add:

```typescript
const [rgbFile, setRgbFile] = useState<File | null>(null)
```

In `runInspect()`, the FormData is already built. Add the RGB file if present:

```typescript
  async function runInspect() {
    if (!inspectFile) return
    setInspectBusy(true)
    setInspectError(null)
    setInspectResult(null)
    const form = new FormData()
    form.append('thermal_image', inspectFile)
    form.append('park_id', 'unknown')
    form.append('altitude_m', String(altitude))
    if (rgbFile) form.append('rgb_image', rgbFile)
    try {
      const data = await api.inspect(form)
      setInspectResult(data as InspectResult)
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : err instanceof Error
            ? err.message
            : 'Inspect failed'
      setInspectError(msg)
      toast.error(msg)
    } finally {
      setInspectBusy(false)
    }
  }
```

- [ ] **Step 3: Add the RGB file input to the upload UI**

Find the thermal file input section (the `<div className="drop"...>` block). After it (and before the "Run detection" button), add an RGB file input section. Locate the `<input hidden type="file" accept=".jpg,.jpeg,.png,.tif,.tiff"` element and the surrounding drop zone, then add after that entire drop-zone `<div>`:

```tsx
          <div
            style={{ marginTop: 10, fontSize: 12, color: '#64748b' }}
            onClick={() => document.getElementById('rgb-upload-input')?.click()}
          >
            <input
              id="rgb-upload-input"
              type="file"
              hidden
              accept=".jpg,.jpeg,.png,.tif,.tiff"
              onChange={(e) => setRgbFile(e.target.files?.[0] ?? null)}
            />
            <span style={{ cursor: 'pointer', textDecoration: 'underline' }}>
              {rgbFile ? `RGB: ${rgbFile.name}` : '+ Add RGB image (optional, enables fusion)'}
            </span>
            {rgbFile && (
              <button
                style={{ marginLeft: 8, fontSize: 11, color: '#ef4444', background: 'none', border: 'none', cursor: 'pointer' }}
                onClick={(e) => { e.stopPropagation(); setRgbFile(null) }}
              >
                ✕
              </button>
            )}
          </div>
```

- [ ] **Step 4: Show fused RGB image when present**

After the `AnnotationCanvas` block in the JSX (around line 274), add:

```tsx
          {inspectResult && inspectResult.rgb_filename && (
            <div style={{ marginTop: 16 }}>
              <div style={{ fontSize: 12, fontWeight: 700, color: '#64748b', marginBottom: 6 }}>
                Fused RGB Overlay
              </div>
              <img
                src={`${process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'}/results/${inspectResult.job_id}/${inspectResult.rgb_filename}`}
                alt="Fused RGB annotated"
                style={{ width: '100%', borderRadius: 8, display: 'block' }}
              />
            </div>
          )}
```

- [ ] **Step 5: Verify the UI compiles — check TypeScript**

```bash
cd /home/parakh/Desktop/AxalonSystems/website/nextjs
npx tsc --noEmit 2>&1 | head -30
```

Expected: zero errors.

- [ ] **Step 6: Commit**

```bash
git add website/nextjs/lib/api.ts website/nextjs/components/Platform/InspectTab.tsx
git commit -m "feat(inspect): RGB upload input + fused image display"
```

---

## Task 3 — Install react-leaflet & Create SSR Wrapper

**Files:**
- Modify: `website/nextjs/package.json` (via npm install)
- Create: `website/nextjs/components/Platform/DynamicOrthoMap.tsx`
- Modify: `website/nextjs/app/platform/layout.tsx`

Leaflet mutates `window` and `document` at import time — it cannot run in SSR. The fix is `dynamic(() => import('./OrthoMap'), { ssr: false })`.

- [ ] **Step 1: Install packages**

```bash
cd /home/parakh/Desktop/AxalonSystems/website/nextjs
npm install leaflet react-leaflet @types/leaflet
```

Expected: packages added to `node_modules/` and `package.json` updated.

- [ ] **Step 2: Import Leaflet CSS in platform layout**

In `website/nextjs/app/platform/layout.tsx`, add at the top (after any existing imports):

```typescript
import 'leaflet/dist/leaflet.css'
```

- [ ] **Step 3: Create DynamicOrthoMap.tsx**

Create `website/nextjs/components/Platform/DynamicOrthoMap.tsx`:

```typescript
'use client'

import dynamic from 'next/dynamic'
import type { OrthoMapProps } from './OrthoMap'

const OrthoMap = dynamic<OrthoMapProps>(() => import('./OrthoMap').then((m) => m.OrthoMap), {
  ssr: false,
  loading: () => (
    <div style={{ height: 420, display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#0f172a', borderRadius: 8, color: '#64748b', fontSize: 13 }}>
      Loading map…
    </div>
  ),
})

export { OrthoMap as DynamicOrthoMap }
```

- [ ] **Step 4: Verify Next.js still compiles**

```bash
cd /home/parakh/Desktop/AxalonSystems/website/nextjs
npx tsc --noEmit 2>&1 | head -20
```

Expected: zero errors (OrthoMap.tsx doesn't exist yet so there may be one import error — that is fine at this step, it will be resolved in Task 4).

- [ ] **Step 5: Commit**

```bash
git add website/nextjs/app/platform/layout.tsx website/nextjs/components/Platform/DynamicOrthoMap.tsx website/nextjs/package.json website/nextjs/package-lock.json
git commit -m "feat(ortho): install react-leaflet, add SSR-safe DynamicOrthoMap wrapper"
```

---

## Task 4 — OrthoMap Component

**Files:**
- Create: `website/nextjs/components/Platform/OrthoMap.tsx`
- Create: `website/nextjs/tests/unit/OrthoMap.test.tsx`

The map shows the ortho as a tile base layer and overlays a `CircleMarker` for each park panel that has GPS coordinates. Clicking a marker shows a popup with the panel ID and worst severity.

- [ ] **Step 1: Write the failing vitest unit test**

Create `website/nextjs/tests/unit/OrthoMap.test.tsx`:

```typescript
import '@testing-library/jest-dom/vitest'
import { describe, expect, test, vi } from 'vitest'

// Leaflet uses browser APIs unavailable in jsdom — stub at module level
vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: { children: React.ReactNode }) => <div data-testid="map-container">{children}</div>,
  TileLayer: () => <div data-testid="tile-layer" />,
  CircleMarker: ({ children }: { children: React.ReactNode }) => <div data-testid="circle-marker">{children}</div>,
  Popup: ({ children }: { children: React.ReactNode }) => <div data-testid="popup">{children}</div>,
  useMap: () => ({ fitBounds: vi.fn() }),
}))
vi.mock('leaflet', () => ({ default: {}, latLngBounds: vi.fn() }))

import { render, screen } from '@testing-library/react'
import { OrthoMap } from '@/components/Platform/OrthoMap'

const BOUNDS = { west: 71.9, south: 27.5, east: 71.95, north: 27.55 }

const PANELS = [
  { panel_id: 'R1-C1', row: 0, col: 0, worst_severity: 'CRITICAL' as const, detection_count: 2, detections: [], gps: { lat: 27.52, lon: 71.92 } },
  { panel_id: 'R1-C2', row: 0, col: 1, worst_severity: null, detection_count: 0, detections: [], gps: null },
]

describe('OrthoMap', () => {
  test('renders map container', () => {
    render(
      <OrthoMap
        parkId="DEMO"
        orthoName="ortho.tif"
        bounds={BOUNDS}
        center={{ lat: 27.52, lon: 71.92 }}
        panels={PANELS}
      />
    )
    expect(screen.getByTestId('map-container')).toBeInTheDocument()
  })

  test('renders one tile layer', () => {
    render(
      <OrthoMap
        parkId="DEMO"
        orthoName="ortho.tif"
        bounds={BOUNDS}
        center={{ lat: 27.52, lon: 71.92 }}
        panels={PANELS}
      />
    )
    expect(screen.getByTestId('tile-layer')).toBeInTheDocument()
  })

  test('renders circle markers only for panels with GPS', () => {
    render(
      <OrthoMap
        parkId="DEMO"
        orthoName="ortho.tif"
        bounds={BOUNDS}
        center={{ lat: 27.52, lon: 71.92 }}
        panels={PANELS}
      />
    )
    // Only PANELS[0] has gps — PANELS[1] has null gps so no marker
    const markers = screen.getAllByTestId('circle-marker')
    expect(markers).toHaveLength(1)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/parakh/Desktop/AxalonSystems/website/nextjs
npm test -- --run tests/unit/OrthoMap.test.tsx 2>&1 | tail -15
```

Expected: FAIL — `Cannot find module '@/components/Platform/OrthoMap'`.

- [ ] **Step 3: Create OrthoMap.tsx**

Create `website/nextjs/components/Platform/OrthoMap.tsx`:

```typescript
'use client'

import { useEffect } from 'react'
import { MapContainer, TileLayer, CircleMarker, Popup, useMap } from 'react-leaflet'
import type { GridPanel } from '@/lib/api'

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

const SEVERITY_COLOR: Record<string, string> = {
  CRITICAL: '#dc2626',
  HIGH: '#ea580c',
  MEDIUM: '#ca8a04',
  LOW: '#0284c7',
}

export type OrthoMapProps = {
  parkId: string
  orthoName: string
  bounds: { west: number; south: number; east: number; north: number }
  center: { lat: number; lon: number }
  panels: GridPanel[]
}

function BoundsFitter({ bounds }: { bounds: OrthoMapProps['bounds'] }) {
  const map = useMap()
  useEffect(() => {
    map.fitBounds([
      [bounds.south, bounds.west],
      [bounds.north, bounds.east],
    ])
  }, [map, bounds])
  return null
}

export function OrthoMap({ parkId, orthoName, bounds, center, panels }: OrthoMapProps) {
  const tileUrl = `${API_BASE}/park/${encodeURIComponent(parkId)}/ortho/${encodeURIComponent(orthoName)}/tiles/{z}/{x}/{y}.png`

  const panelsWithGps = panels.filter((p) => p.gps !== null)

  return (
    <MapContainer
      center={[center.lat, center.lon]}
      zoom={16}
      style={{ height: 420, width: '100%', borderRadius: 8 }}
    >
      <BoundsFitter bounds={bounds} />
      <TileLayer
        url={tileUrl}
        attribution="Axalon orthomosaic"
        maxZoom={24}
        tileSize={256}
      />
      {panelsWithGps.map((panel) => {
        const color = SEVERITY_COLOR[panel.worst_severity ?? ''] ?? '#64748b'
        return (
          <CircleMarker
            key={panel.panel_id}
            center={[panel.gps!.lat, panel.gps!.lon]}
            radius={6}
            pathOptions={{ color, fillColor: color, fillOpacity: 0.8 }}
          >
            <Popup>
              <strong>{panel.panel_id}</strong>
              <br />
              {panel.worst_severity ?? 'No detections'} · {panel.detection_count} fault
              {panel.detection_count !== 1 ? 's' : ''}
            </Popup>
          </CircleMarker>
        )
      })}
    </MapContainer>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd /home/parakh/Desktop/AxalonSystems/website/nextjs
npm test -- --run tests/unit/OrthoMap.test.tsx 2>&1 | tail -10
```

Expected: 3 passed.

- [ ] **Step 5: TypeScript check**

```bash
npx tsc --noEmit 2>&1 | head -20
```

Expected: zero errors.

- [ ] **Step 6: Commit**

```bash
git add website/nextjs/components/Platform/OrthoMap.tsx website/nextjs/tests/unit/OrthoMap.test.tsx
git commit -m "feat(ortho): OrthoMap component — Leaflet tile layer + detection markers"
```

---

## Task 5 — Wire Ortho Upload & Map Toggle into ParkMapTab

**Files:**
- Modify: `website/nextjs/lib/api.ts`
- Modify: `website/nextjs/components/Platform/ParkMapTab.tsx`

When a park is selected, the tab fetches ortho list. If orthos exist, a "Map" button appears alongside the existing "Grid" view. Selecting "Map" shows `DynamicOrthoMap`; "Grid" shows `ParkMapGrid` as before. An upload button lets operators add a new GeoTIFF.

- [ ] **Step 1: Fix OrthoMeta.bounds type in api.ts**

In `website/nextjs/lib/api.ts`, replace:

```typescript
export type OrthoMeta = {
  name: string
  bounds?: [number, number, number, number]
  [k: string]: unknown
}
```

with:

```typescript
export type OrthoMeta = {
  park_id: string
  name: string
  crs: string
  width: number
  height: number
  band_count: number
  bounds: { west: number; south: number; east: number; north: number }
  center: { lat: number; lon: number }
  size_bytes: number
}
```

- [ ] **Step 2: Add `api.orthos()` return type check**

The `api.orthos()` call already returns `OrthoMeta[]`. Verify its definition in `api.ts` reads:

```typescript
  orthos: (parkId: string) =>
    request<OrthoMeta[]>(`/park/${encodeURIComponent(parkId)}/orthos`).then(
      (resp) => (resp as { orthos: OrthoMeta[] }).orthos ?? (resp as OrthoMeta[])
    ),
```

> **Note:** The backend returns `{"park_id": "...", "orthos": [...]}`, not a bare array. The `.then()` above handles both shapes. If `api.orthos` is already defined differently, adjust accordingly — the key is to extract `body.orthos`.

- [ ] **Step 3: Add ortho state + fetch to ParkMapTab**

In `website/nextjs/components/Platform/ParkMapTab.tsx`, add imports at top:

```typescript
import { DynamicOrthoMap } from '@/components/Platform/DynamicOrthoMap'
import type { OrthoMeta } from '@/lib/api'
```

Add state variables inside `ParkMapTab()`:

```typescript
  const [orthos, setOrthos] = useState<OrthoMeta[]>([])
  const [orthoView, setOrthoView] = useState(false)
  const [orthoUploading, setOrthoUploading] = useState(false)
```

Add a `useEffect` that fetches the ortho list whenever `parkMapParkId` changes (place after the existing `useEffect` that fetches inspections):

```typescript
  useEffect(() => {
    if (!parkMapParkId) { setOrthos([]); return }
    let cancelled = false
    api.orthos(parkMapParkId)
      .then((list) => { if (!cancelled) setOrthos(list) })
      .catch(() => { if (!cancelled) setOrthos([]) })
    return () => { cancelled = true }
  }, [parkMapParkId])
```

- [ ] **Step 4: Add upload handler**

Inside `ParkMapTab()`, add the upload function:

```typescript
  async function handleOrthoUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file || !parkMapParkId) return
    setOrthoUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)
      const meta = await api.uploadOrtho(parkMapParkId, form)
      setOrthos((prev) => [...prev.filter((o) => o.name !== meta.name), meta])
      setOrthoView(true)
      toast.success(`Ortho "${meta.name}" uploaded`)
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Upload failed')
    } finally {
      setOrthoUploading(false)
      e.target.value = ''
    }
  }
```

- [ ] **Step 5: Add ortho toolbar + view toggle to ParkMapTab JSX**

Find the existing toolbar section in the JSX (the `<div>` containing the Park selector and Inspection selector). After it and before the `<div className="park-map-layout"...>`, add the ortho bar:

```tsx
      {parkMapParkId && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10, flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', gap: 4 }}>
            <button
              onClick={() => setOrthoView(false)}
              style={{
                padding: '5px 14px', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: 'pointer',
                background: !orthoView ? '#0ea5e9' : 'transparent',
                color: !orthoView ? '#fff' : '#64748b',
                border: '1px solid #cbd5e1',
              }}
            >
              Grid
            </button>
            <button
              onClick={() => setOrthoView(true)}
              disabled={orthos.length === 0}
              style={{
                padding: '5px 14px', borderRadius: 6, fontSize: 12, fontWeight: 600, cursor: orthos.length > 0 ? 'pointer' : 'not-allowed',
                background: orthoView ? '#0ea5e9' : 'transparent',
                color: orthoView ? '#fff' : '#64748b',
                border: '1px solid #cbd5e1',
                opacity: orthos.length === 0 ? 0.5 : 1,
              }}
            >
              Map {orthos.length > 0 ? `(${orthos.length})` : ''}
            </button>
          </div>
          <label style={{ fontSize: 12, cursor: 'pointer', color: '#0ea5e9' }}>
            <input
              type="file"
              hidden
              accept=".tif,.tiff"
              onChange={handleOrthoUpload}
              disabled={orthoUploading}
            />
            {orthoUploading ? 'Uploading…' : '+ Upload Ortho'}
          </label>
        </div>
      )}
```

- [ ] **Step 6: Render OrthoMap when in map view**

Replace the `<div className="park-map-layout"...>` block with a conditional:

```tsx
      {orthoView && orthos[0] ? (
        <DynamicOrthoMap
          parkId={parkMapParkId}
          orthoName={orthos[0].name}
          bounds={orthos[0].bounds}
          center={orthos[0].center}
          panels={parkMapGrid?.panels ?? []}
        />
      ) : (
        <div
          className="park-map-layout"
          style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 320px', gap: 16 }}
        >
          <ParkMapGrid
            grid={parkMapGrid}
            selectedPanelId={parkMapSelectedPanel?.panel_id ?? null}
            onSelect={(p) => setParkMapSelectedPanel(p)}
          />
          <div className={`park-panel-detail ${parkMapSelectedPanel ? 'is-open' : ''}`}>
            <ParkPanelDetail
              panel={parkMapSelectedPanel}
              jobId={parkMapGrid?.inspection_id ?? null}
              onClose={() => setParkMapSelectedPanel(null)}
            />
          </div>
        </div>
      )}
```

- [ ] **Step 7: TypeScript check**

```bash
cd /home/parakh/Desktop/AxalonSystems/website/nextjs
npx tsc --noEmit 2>&1 | head -20
```

Expected: zero errors.

- [ ] **Step 8: Commit**

```bash
git add website/nextjs/lib/api.ts website/nextjs/components/Platform/ParkMapTab.tsx
git commit -m "feat(ortho): ortho upload panel + Grid/Map toggle in ParkMapTab"
```

---

## Task 6 — Park Map PNG Renderer

**Files:**
- Create: `platform/core/map_renderer.py`
- Create: `tests/backend/test_map_renderer.py`

Pillow renders the fault grid as a static PNG: each panel cell is a colored square (severity color), panel ID printed in the corner, legend at bottom.

- [ ] **Step 1: Write the failing unit test**

Create `tests/backend/test_map_renderer.py`:

```python
"""Unit tests for platform/core/map_renderer.py."""
import io
from PIL import Image


def test_render_returns_bytes():
    from axalon.core.map_renderer import render_grid_png
    panels = [
        {"panel_id": "R1-C1", "row": 0, "col": 0, "worst_severity": "CRITICAL", "detection_count": 2},
        {"panel_id": "R1-C2", "row": 0, "col": 1, "worst_severity": "HIGH", "detection_count": 1},
        {"panel_id": "R2-C1", "row": 1, "col": 0, "worst_severity": None, "detection_count": 0},
    ]
    result = render_grid_png(panels, title="Test Park")
    assert isinstance(result, bytes)
    assert len(result) > 100


def test_render_produces_valid_png():
    from axalon.core.map_renderer import render_grid_png
    panels = [{"panel_id": "R1-C1", "row": 0, "col": 0, "worst_severity": "MEDIUM", "detection_count": 1}]
    result = render_grid_png(panels)
    img = Image.open(io.BytesIO(result))
    assert img.format == "PNG"
    assert img.size[0] > 0 and img.size[1] > 0


def test_render_empty_panels_returns_placeholder():
    from axalon.core.map_renderer import render_grid_png
    result = render_grid_png([])
    img = Image.open(io.BytesIO(result))
    assert img.format == "PNG"


def test_render_uses_severity_colors():
    from axalon.core.map_renderer import render_grid_png, SEVERITY_COLORS
    assert "CRITICAL" in SEVERITY_COLORS
    assert "HIGH" in SEVERITY_COLORS
    assert "MEDIUM" in SEVERITY_COLORS
    assert "LOW" in SEVERITY_COLORS
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/parakh/Desktop/AxalonSystems
PYTHONSAFEPATH=1 .venv/bin/python -m pytest tests/backend/test_map_renderer.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'axalon.core.map_renderer'`.

- [ ] **Step 3: Create map_renderer.py**

Create `platform/core/map_renderer.py`:

```python
"""map_renderer.py — Render a park fault grid as a static PNG using Pillow."""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SEVERITY_COLORS: dict[str | None, tuple[int, int, int]] = {
    "CRITICAL": (220, 38, 38),
    "HIGH": (234, 88, 12),
    "MEDIUM": (202, 138, 4),
    "LOW": (2, 132, 199),
    None: (51, 65, 85),  # slate-700 — no detections
}

_CELL = 48          # pixels per grid cell
_PAD = 20           # outer padding
_TITLE_H = 26       # height reserved for title row
_LEGEND_H = 32      # height reserved for legend row
_BG = (15, 23, 42)  # slate-950
_TEXT = (203, 213, 225)  # slate-300

# Try to load a built-in font; fall back to PIL default if unavailable
def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def render_grid_png(
    panels: list[dict],
    title: str = "",
) -> bytes:
    """Render panels as a fault-coloured grid PNG.

    Args:
        panels: list of dicts with keys ``row``, ``col``, ``panel_id``,
                ``worst_severity`` (CRITICAL/HIGH/MEDIUM/LOW/None).
        title:  optional text printed at the top of the image.

    Returns:
        PNG bytes.
    """
    if not panels:
        img = Image.new("RGB", (320, 80), _BG)
        draw = ImageDraw.Draw(img)
        draw.text((10, 28), "No panel data", fill=_TEXT, font=_font(13))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    max_row = max(p["row"] for p in panels) + 1
    max_col = max(p["col"] for p in panels) + 1

    title_offset = _TITLE_H if title else 0
    w = max_col * _CELL + 2 * _PAD
    h = max_row * _CELL + 2 * _PAD + title_offset + _LEGEND_H

    img = Image.new("RGB", (w, h), _BG)
    draw = ImageDraw.Draw(img)

    small = _font(9)
    medium = _font(12)

    if title:
        draw.text((_PAD, 6), title, fill=_TEXT, font=medium)

    for panel in panels:
        row = panel["row"]
        col = panel["col"]
        sev = panel.get("worst_severity")
        color = SEVERITY_COLORS.get(sev, SEVERITY_COLORS[None])

        x1 = _PAD + col * _CELL + 1
        y1 = _PAD + title_offset + row * _CELL + 1
        x2 = x1 + _CELL - 2
        y2 = y1 + _CELL - 2

        draw.rectangle([x1, y1, x2, y2], fill=color, outline=(30, 41, 59))

        pid = str(panel.get("panel_id", ""))
        if pid:
            draw.text((x1 + 3, y1 + 3), pid[-6:], fill=(255, 255, 255), font=small)

    # Legend
    legend_y = h - _LEGEND_H + 6
    x_cursor = _PAD
    for label, color in [("CRITICAL", (220, 38, 38)), ("HIGH", (234, 88, 12)),
                         ("MEDIUM", (202, 138, 4)), ("LOW", (2, 132, 199)),
                         ("None", (51, 65, 85))]:
        draw.rectangle([x_cursor, legend_y, x_cursor + 12, legend_y + 12], fill=color)
        draw.text((x_cursor + 16, legend_y), label, fill=_TEXT, font=small)
        x_cursor += 68

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
PYTHONSAFEPATH=1 .venv/bin/python -m pytest tests/backend/test_map_renderer.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add platform/core/map_renderer.py tests/backend/test_map_renderer.py
git commit -m "feat(export): Pillow park grid PNG renderer with severity legend"
```

---

## Task 7 — `GET /park/{park_id}/grid/png` Endpoint

**Files:**
- Modify: `platform/api/app.py`
- Modify: `tests/backend/test_api_contract.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/backend/test_api_contract.py`:

```python
# ── /park/{park_id}/grid/png ──────────────────────────────────────────────────

def test_park_grid_png_returns_png(client, batch_fixture):
    batch_fixture(park_id="PNG_TEST")
    r = client.get("/park/PNG_TEST/grid/png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    # Verify it's a real PNG (magic bytes)
    assert r.content[:4] == b'\x89PNG'


def test_park_grid_png_unknown_park_returns_empty_png(client):
    r = client.get("/park/DOES_NOT_EXIST/grid/png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:4] == b'\x89PNG'
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
PYTHONSAFEPATH=1 .venv/bin/python -m pytest tests/backend/test_api_contract.py::test_park_grid_png_returns_png tests/backend/test_api_contract.py::test_park_grid_png_unknown_park_returns_empty_png -v
```

Expected: FAIL — 404 (route not found).

- [ ] **Step 3: Add the endpoint to app.py**

Add after the `list_orthos` endpoint (around line 1080) in `platform/api/app.py`:

```python
@app.get("/park/{park_id}/grid/png")
def export_park_grid_png(park_id: str, inspection_id: str | None = None):
    """Export the park fault grid as a PNG image for download."""
    from axalon.core.map_renderer import render_grid_png
    park_id = _validate_park_id(park_id)

    try:
        grid = get_park_grid(park_id, inspection_id)
        panels = [
            {
                "panel_id": p.get("panel_id"),
                "row": p.get("row", 0),
                "col": p.get("col", 0),
                "worst_severity": p.get("worst_severity"),
                "detection_count": p.get("detection_count", 0),
            }
            for p in (grid.get("panels") or [])
        ]
    except Exception:
        panels = []

    png_bytes = render_grid_png(panels, title=park_id)
    safe_name = park_id.replace("/", "_").replace("..", "")
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}_grid.png"',
            "Cache-Control": "no-store",
        },
    )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
PYTHONSAFEPATH=1 .venv/bin/python -m pytest tests/backend/test_api_contract.py::test_park_grid_png_returns_png tests/backend/test_api_contract.py::test_park_grid_png_unknown_park_returns_empty_png -v
```

Expected: both PASS.

- [ ] **Step 5: Run full backend suite**

```bash
PYTHONSAFEPATH=1 .venv/bin/python -m pytest tests/backend/ -q
```

Expected: 54 passed (50 previous + 2 new contract + 4 map_renderer ≈ check exact count).

- [ ] **Step 6: Commit**

```bash
git add platform/api/app.py tests/backend/test_api_contract.py
git commit -m "feat(export): GET /park/{id}/grid/png endpoint"
```

---

## Task 8 — PNG Download Button in ParkMapTab

**Files:**
- Modify: `website/nextjs/lib/api.ts`
- Modify: `website/nextjs/components/Platform/ParkMapTab.tsx`

- [ ] **Step 1: Add `parkGridPng` to api.ts**

In `website/nextjs/lib/api.ts`, add inside the `api` object (near other park methods):

```typescript
  parkGridPng: (parkId: string, inspectionId?: string) => {
    const q = inspectionId ? `?inspection_id=${encodeURIComponent(inspectionId)}` : ''
    return fetch(
      `${BASE_URL}/park/${encodeURIComponent(parkId)}/grid/png${q}`,
      { headers: sessionStorage.getItem('axalon_api_key')
          ? { Authorization: `Bearer ${sessionStorage.getItem('axalon_api_key')}` }
          : {} }
    ).then((r) => {
      if (!r.ok) throw new Error(`PNG export failed: ${r.status}`)
      return r.blob()
    })
  },
```

> `BASE_URL` is already defined at the top of `api.ts` as `process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'` — use whatever variable name is already used in the file.

- [ ] **Step 2: Add export button to ParkMapTab**

In the ortho toolbar section added in Task 5 (the `<div>` with Grid/Map buttons), add an export button at the end:

```tsx
          {parkMapGrid && (
            <button
              style={{
                marginLeft: 'auto', padding: '5px 14px', borderRadius: 6, fontSize: 12,
                fontWeight: 600, cursor: 'pointer', background: 'transparent',
                color: '#64748b', border: '1px solid #cbd5e1',
              }}
              onClick={async () => {
                try {
                  const blob = await api.parkGridPng(
                    parkMapParkId,
                    parkMapInspectionId || undefined,
                  )
                  const url = URL.createObjectURL(blob)
                  const a = document.createElement('a')
                  a.href = url
                  a.download = `${parkMapParkId}_grid.png`
                  a.click()
                  URL.revokeObjectURL(url)
                } catch (err) {
                  toast.error(err instanceof Error ? err.message : 'Export failed')
                }
              }}
            >
              ↓ Export PNG
            </button>
          )}
```

- [ ] **Step 3: TypeScript check**

```bash
cd /home/parakh/Desktop/AxalonSystems/website/nextjs
npx tsc --noEmit 2>&1 | head -20
```

Expected: zero errors.

- [ ] **Step 4: Commit**

```bash
git add website/nextjs/lib/api.ts website/nextjs/components/Platform/ParkMapTab.tsx
git commit -m "feat(export): park grid PNG download button in ParkMapTab"
```

---

## Task 9 — Full Acceptance Pass

**Files:** verification only — no code changes unless a test fails.

Run every test suite and verify the golden-path Playwright test still exercises the new endpoints.

- [ ] **Step 1: Restart services with fresh build**

```bash
pkill -f "uvicorn\|next dev" 2>/dev/null || true
sleep 2
PYTHONSAFEPATH=1 .venv/bin/uvicorn axalon.api.app:app --host 0.0.0.0 --port 8000 > /tmp/axalon-api.log 2>&1 &
cd /home/parakh/Desktop/AxalonSystems/website/nextjs && npm run dev > /tmp/nextjs.log 2>&1 &
```

Wait ~15 s for both to be ready:

```bash
until curl -sf http://localhost:8000/health && curl -sf -o /dev/null http://localhost:3000/platform; do sleep 2; done && echo "Services ready"
```

- [ ] **Step 2: Backend tests**

```bash
cd /home/parakh/Desktop/AxalonSystems
PYTHONSAFEPATH=1 .venv/bin/python -m pytest tests/backend/ -q
```

Expected: all pass (≥52 tests).

- [ ] **Step 3: Frontend unit tests**

```bash
cd /home/parakh/Desktop/AxalonSystems/website/nextjs
npm test -- --run
```

Expected: all pass (≥26 tests including new OrthoMap tests).

- [ ] **Step 4: Playwright e2e**

```bash
cd /home/parakh/Desktop/AxalonSystems/website/nextjs
npx playwright test --reporter=line
```

Expected: 3 passed (golden path + 2 annotation tests). No regressions.

- [ ] **Step 5: Manual smoke test — PNG download**

```bash
curl -s "http://localhost:8000/park/SOLAR_PARK_DEMO/grid/png" -o /tmp/park_grid.png
file /tmp/park_grid.png
```

Expected: `/tmp/park_grid.png: PNG image data, ...`

- [ ] **Step 6: Final commit**

```bash
cd /home/parakh/Desktop/AxalonSystems
git add -A
git commit -m "chore(platform): Phase 6 acceptance pass — all suites green" || echo "nothing to commit"
```

---

## Self-Review Checklist

**Spec coverage:**
- ✅ RGB fusion: `/inspect` returns `rgb_filename`, InspectTab uploads RGB + shows fused result
- ✅ Ortho tile map: react-leaflet with TileLayer + panel CircleMarkers, upload + Grid/Map toggle
- ✅ Park Map PNG export: Pillow renderer, endpoint, download button
- ✅ `OrthoMeta.bounds` type mismatch fixed in api.ts

**Placeholders:** None — all code blocks are complete and runnable.

**Type consistency:**
- `OrthoMapProps` defined in `OrthoMap.tsx`, imported via `DynamicOrthoMap.tsx` ✅
- `GridPanel` from `@/lib/api` used in `OrthoMap.tsx` ✅
- `InspectResult.rgb_filename` typed as `string | undefined` ✅
- `render_grid_png` signature stable across Task 6 and Task 7 ✅
- `get_park_grid()` called in Task 7 — already defined in `app.py` at line 1182 ✅
