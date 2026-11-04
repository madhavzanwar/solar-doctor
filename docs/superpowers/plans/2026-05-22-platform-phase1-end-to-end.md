# Platform Phase 1 — End-to-End Operator Flow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the existing `/platform` UI work end-to-end against the live FastAPI backend with synthetic test data — operator can run one batch inspection and download all four report formats.

**Architecture:** Generate a synthetic mission fixture so the YOLO pipeline has input. Extract repeated `fetch()` calls in `app/platform/page.tsx` into a thin typed API client. Add a minimal toast surface so failed requests are never silent. Then walk each tab manually with the live API and fix every broken wire on contact.

**Tech Stack:** Next.js 14 (App Router, client components), Python 3.11+, FastAPI, Ultralytics YOLOv8s, OpenCV, Pillow, `piexif` for EXIF GPS, native `fetch`, no new npm deps.

**Spec:** `docs/superpowers/specs/2026-05-22-platform-phase1-end-to-end-design.md`

---

## File Structure

| Path | Responsibility | Action |
|---|---|---|
| `scripts/make_sample_mission.py` | One-shot script: generates N synthetic thermal + RGB pairs with EXIF GPS into `tests/fixtures/sample_mission/` | Create |
| `tests/fixtures/sample_mission/thermal/` | 20× synthetic thermal JPEGs (640×512, planted hotspots) | Create (committed) |
| `tests/fixtures/sample_mission/rgb/` | 20× synthetic RGB JPEGs (panel-grid render) | Create (committed) |
| `website/nextjs/lib/api.ts` | Typed thin client: `api.health()`, `api.batch()`, `api.status()`, etc. Throws `ApiError(status, body)` | Create |
| `website/nextjs/components/Platform/Toast.tsx` | `ToastProvider` + `useToast()` hook, dependency-free | Create |
| `website/nextjs/app/platform/page.tsx` | Replace inline `fetch(${API_BASE}/...)` with `api.*` + `toast.error()` on failure; fix bugs found during walkthrough | Modify |
| `website/nextjs/app/(site)/layout.tsx` / `website/nextjs/app/platform/layout.tsx` | Wrap children in `<ToastProvider>` | Modify (whichever owns /platform) |
| `website/nextjs/components/Platform/AnomalyMap.tsx` | Fix real-data shape mismatches discovered during walkthrough | Modify |
| `platform/api/app.py` | Fix any endpoint bugs discovered during walkthrough; no new endpoints | Modify |
| `docs/OPERATOR_RUNBOOK.md` | Click-by-click golden path walk-through | Create |

---

## Task 1: Synthetic mission generator

**Files:**
- Create: `scripts/make_sample_mission.py`
- Create: `tests/fixtures/sample_mission/thermal/img_001.jpg` … `img_020.jpg`
- Create: `tests/fixtures/sample_mission/rgb/img_001.jpg` … `img_020.jpg`

- [ ] **Step 1: Write `scripts/make_sample_mission.py`**

```python
"""make_sample_mission.py — generate a synthetic flight mission for local testing.

Writes N pairs of synthetic thermal + RGB JPEGs into tests/fixtures/sample_mission/.
Each pair carries EXIF GPS on a small grid so the map has spatially distributed markers.
Hot-spot blobs in the thermal image are tuned to trigger the YOLO 'hot-spot-*' classes
at the default 0.25 confidence threshold.
"""

from __future__ import annotations

import argparse
import math
import random
from fractions import Fraction
from pathlib import Path

import cv2
import numpy as np
import piexif
from PIL import Image


REPO_ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = REPO_ROOT / "tests" / "fixtures" / "sample_mission"

CENTER_LAT = 19.0760  # Mumbai-ish anchor; arbitrary
CENTER_LON = 72.8777
GRID_SPACING_M = 8.0  # meters between adjacent images
IMG_W, IMG_H = 640, 512


def _to_deg_min_sec(value: float) -> tuple[tuple[int, int], tuple[int, int], tuple[int, int]]:
    value = abs(value)
    deg = int(value)
    minutes_float = (value - deg) * 60
    minutes = int(minutes_float)
    seconds = round((minutes_float - minutes) * 60 * 10000)
    return ((deg, 1), (minutes, 1), (seconds, 10000))


def _exif_for(lat: float, lon: float, altitude_m: float) -> bytes:
    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: b"N" if lat >= 0 else b"S",
        piexif.GPSIFD.GPSLatitude: _to_deg_min_sec(lat),
        piexif.GPSIFD.GPSLongitudeRef: b"E" if lon >= 0 else b"W",
        piexif.GPSIFD.GPSLongitude: _to_deg_min_sec(lon),
        piexif.GPSIFD.GPSAltitudeRef: 0,
        piexif.GPSIFD.GPSAltitude: (int(altitude_m * 100), 100),
    }
    return piexif.dump({"GPS": gps_ifd})


def _make_thermal(rng: random.Random) -> np.ndarray:
    base = np.full((IMG_H, IMG_W), 70, dtype=np.uint8)
    noise = rng.randint(-8, 8)
    img = np.clip(base.astype(int) + noise + rng.randint(-3, 3), 30, 110).astype(np.uint8)
    img = cv2.GaussianBlur(img, (15, 15), 5)
    n_hot = rng.randint(1, 3)
    for _ in range(n_hot):
        cx = rng.randint(60, IMG_W - 60)
        cy = rng.randint(60, IMG_H - 60)
        r = rng.randint(18, 32)
        intensity = rng.randint(220, 255)
        cv2.circle(img, (cx, cy), r, intensity, -1, lineType=cv2.LINE_AA)
        img = cv2.GaussianBlur(img, (9, 9), 3)
    return cv2.applyColorMap(img, cv2.COLORMAP_INFERNO)


def _make_rgb(rng: random.Random) -> np.ndarray:
    img = np.full((IMG_H, IMG_W, 3), (35, 40, 50), dtype=np.uint8)
    cols, rows = 8, 6
    pad = 12
    cell_w = (IMG_W - pad * (cols + 1)) // cols
    cell_h = (IMG_H - pad * (rows + 1)) // rows
    for r in range(rows):
        for c in range(cols):
            x1 = pad + c * (cell_w + pad)
            y1 = pad + r * (cell_h + pad)
            shade = 25 + rng.randint(0, 15)
            cv2.rectangle(img, (x1, y1), (x1 + cell_w, y1 + cell_h), (shade, shade + 5, shade + 10), -1)
            cv2.rectangle(img, (x1, y1), (x1 + cell_w, y1 + cell_h), (90, 100, 110), 1)
    return img


def _write_jpeg_with_gps(path: Path, bgr: np.ndarray, lat: float, lon: float, altitude_m: float) -> None:
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    pil = Image.fromarray(rgb)
    exif_bytes = _exif_for(lat, lon, altitude_m)
    path.parent.mkdir(parents=True, exist_ok=True)
    pil.save(path, "JPEG", quality=88, exif=exif_bytes)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=20)
    parser.add_argument("--altitude", type=float, default=42.0)
    parser.add_argument("--seed", type=int, default=20260522)
    args = parser.parse_args()

    rng = random.Random(args.seed)
    thermal_dir = OUT_DIR / "thermal"
    rgb_dir = OUT_DIR / "rgb"

    side = int(math.ceil(math.sqrt(args.count)))
    meters_per_deg_lat = 111_320.0
    for i in range(args.count):
        row, col = divmod(i, side)
        dlat = (row * GRID_SPACING_M) / meters_per_deg_lat
        dlon = (col * GRID_SPACING_M) / (meters_per_deg_lat * math.cos(math.radians(CENTER_LAT)))
        lat = CENTER_LAT + dlat
        lon = CENTER_LON + dlon

        thermal = _make_thermal(rng)
        rgb = _make_rgb(rng)
        name = f"img_{i + 1:03d}.jpg"
        _write_jpeg_with_gps(thermal_dir / name, thermal, lat, lon, args.altitude)
        _write_jpeg_with_gps(rgb_dir / name, rgb, lat, lon, args.altitude)

    print(f"Wrote {args.count} pairs to {OUT_DIR}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the generator**

Run: `python scripts/make_sample_mission.py`
Expected: `Wrote 20 pairs to /home/parakh/Desktop/AxalonSystems/tests/fixtures/sample_mission`

- [ ] **Step 3: Verify the fixture exists**

Run: `ls tests/fixtures/sample_mission/thermal | wc -l && ls tests/fixtures/sample_mission/rgb | wc -l`
Expected: `20` and `20`

- [ ] **Step 4: Sanity-check one image carries GPS EXIF**

Run: `python -c "import piexif; e=piexif.load('tests/fixtures/sample_mission/thermal/img_001.jpg'); print(e['GPS'])"`
Expected: non-empty dict containing `GPSLatitude` and `GPSLongitude` keys.

- [ ] **Step 5: Sanity-check the YOLO model fires on the fixture**

Run:
```bash
python -c "
from ultralytics import YOLO
m = YOLO('ml/checkpoints/best.pt')
results = m('tests/fixtures/sample_mission/thermal/', conf=0.25, verbose=False)
total = sum(len(r.boxes) for r in results)
print(f'Total detections across 20 images: {total}')
"
```
Expected: total ≥ 5. If 0, the planted hotspots aren't hitting the trained distribution — fall back: copy 20 frames from `ml/data/images/test/` into `tests/fixtures/sample_mission/thermal/` (and use the same images for RGB) and re-run this step.

- [ ] **Step 6: Commit**

```bash
git add scripts/make_sample_mission.py tests/fixtures/sample_mission/
git commit -m "test: synthetic mission fixture for end-to-end platform testing"
```

---

## Task 2: Smoke-test `./run.sh all`

**Files:** none modified yet — verifying current state.

- [ ] **Step 1: Stop any old dev servers**

Run: `./run.sh stop 2>/dev/null || true; pkill -f "next dev" 2>/dev/null || true; sleep 1`

- [ ] **Step 2: Boot both services**

Run in background: `./run.sh all > /tmp/run-all.log 2>&1 &`
Wait for `Local:   http://localhost:3000` in `/tmp/run-all.log`.

- [ ] **Step 3: Health-check both endpoints**

Run: `curl -fsS http://localhost:8000/health && echo && curl -fsS -o /dev/null -w '%{http_code}\n' http://localhost:3000/platform`
Expected: API returns `{"status":"ok",...}` (or similar truthy JSON); platform returns `200`.

- [ ] **Step 4: If either fails, fix and recommit before continuing**

If API fails: read `logs/api.log`, fix the import/wiring issue in `platform/api/app.py` or `run.sh`. Commit each fix as its own change with message `fix(api): <what>`.

If Next.js fails: read `logs/platform.log`. Most likely a stale `.next/` cache — run `rm -rf website/nextjs/.next` and retry.

- [ ] **Step 5: Leave the services running for the remainder of the plan**

Do not stop until Task 13.

---

## Task 3: Minimal Toast component

**Files:**
- Create: `website/nextjs/components/Platform/Toast.tsx`
- Modify: `website/nextjs/app/platform/page.tsx` (wrap `<PlatformPage>` body with `<ToastProvider>` OR add provider in nearest layout)

- [ ] **Step 1: Write `Toast.tsx`**

```tsx
'use client'

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'

type ToastKind = 'error' | 'info' | 'success'
type Toast = { id: number; kind: ToastKind; text: string }

type ToastCtx = {
  push: (kind: ToastKind, text: string) => void
  error: (text: string) => void
  info: (text: string) => void
  success: (text: string) => void
}

const Ctx = createContext<ToastCtx | null>(null)

export function useToast(): ToastCtx {
  const ctx = useContext(Ctx)
  if (!ctx) throw new Error('useToast must be used inside <ToastProvider>')
  return ctx
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])

  const push = useCallback((kind: ToastKind, text: string) => {
    const id = Date.now() + Math.random()
    setToasts((t) => [...t, { id, kind, text }])
    setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 6000)
  }, [])

  const api: ToastCtx = {
    push,
    error: (t) => push('error', t),
    info: (t) => push('info', t),
    success: (t) => push('success', t),
  }

  return (
    <Ctx.Provider value={api}>
      {children}
      <div
        style={{
          position: 'fixed',
          right: 16,
          bottom: 16,
          display: 'flex',
          flexDirection: 'column',
          gap: 8,
          zIndex: 9999,
          maxWidth: 480,
        }}
      >
        {toasts.map((t) => (
          <div
            key={t.id}
            role="status"
            style={{
              background:
                t.kind === 'error' ? '#7f1d1d' : t.kind === 'success' ? '#14532d' : '#1e293b',
              color: '#fff',
              padding: '10px 14px',
              borderRadius: 8,
              fontSize: 13,
              lineHeight: 1.4,
              boxShadow: '0 8px 24px rgba(0,0,0,0.25)',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            {t.text}
          </div>
        ))}
      </div>
    </Ctx.Provider>
  )
}
```

- [ ] **Step 2: Wrap the platform page with the provider**

In `website/nextjs/app/platform/page.tsx`, locate the top-level component (likely `export default function PlatformPage()` or similar) and wrap its returned JSX so that `useToast()` is callable from all descendants. Add the import at top:

```tsx
import { ToastProvider, useToast } from '@/components/Platform/Toast'
```

Then split the component so the body that uses `useToast()` is a child of the provider. Example shape:

```tsx
export default function PlatformPage() {
  return (
    <ToastProvider>
      <PlatformPageBody />
    </ToastProvider>
  )
}

function PlatformPageBody() {
  // ...all existing component body, including useToast() calls...
}
```

- [ ] **Step 3: Run the dev server (already running from Task 2). Hit the page and confirm it still loads.**

Run: `curl -fsS -o /dev/null -w '%{http_code}\n' http://localhost:3000/platform`
Expected: `200`.

- [ ] **Step 4: Manually verify the toast appears**

Temporarily add `<button onClick={() => toast.error('hello')}>test</button>` at the top of `PlatformPageBody`. Open `http://localhost:3000/platform` in a browser, click, see a red toast bottom-right. Remove the button.

- [ ] **Step 5: Commit**

```bash
git add website/nextjs/components/Platform/Toast.tsx website/nextjs/app/platform/page.tsx
git commit -m "feat(platform): minimal toast surface for error visibility"
```

---

## Task 4: API client at `lib/api.ts`

**Files:**
- Create: `website/nextjs/lib/api.ts`

- [ ] **Step 1: Write `api.ts`**

```ts
export const API_BASE =
  process.env.NEXT_PUBLIC_AXALON_API_URL || 'http://localhost:8000'

export class ApiError extends Error {
  status: number
  body: string
  constructor(status: number, body: string, message?: string) {
    super(message ?? `HTTP ${status}: ${body.slice(0, 200)}`)
    this.name = 'ApiError'
    this.status = status
    this.body = body
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, init)
  } catch (err) {
    throw new ApiError(0, String(err), `Network error contacting ${API_BASE}${path}`)
  }
  const text = await res.text()
  if (!res.ok) throw new ApiError(res.status, text)
  if (!text) return undefined as T
  try {
    return JSON.parse(text) as T
  } catch {
    return text as unknown as T
  }
}

// Shapes — keep loose; the API is the source of truth.
export type Health = { status: string; [k: string]: unknown }
export type JobStatus = {
  job_id: string
  state: 'queued' | 'running' | 'succeeded' | 'failed' | string
  progress?: number
  total?: number
  processed?: number
  message?: string
  [k: string]: unknown
}
export type ParkRef = { id: string; name?: string }
export type ParkSummary = Record<string, unknown>
export type MapData = Record<string, unknown>
export type SettingsBlob = Record<string, unknown>
export type InspectResult = Record<string, unknown>
export type OrthoMeta = {
  name: string
  bounds?: [number, number, number, number]
  [k: string]: unknown
}

export const api = {
  health: () => request<Health>('/health'),
  batch: (form: FormData) =>
    request<{ job_id: string }>('/batch', { method: 'POST', body: form }),
  inspect: (form: FormData) =>
    request<InspectResult>('/inspect', { method: 'POST', body: form }),
  status: (jobId: string) => request<JobStatus>(`/status/${encodeURIComponent(jobId)}`),
  reportUrl: (jobId: string, format: 'json' | 'excel' | 'geojson' | 'pdf') =>
    `${API_BASE}/report/${encodeURIComponent(jobId)}?format=${format}`,
  mapData: (jobId: string) => request<MapData>(`/map/${encodeURIComponent(jobId)}`),
  parks: () => request<ParkRef[]>('/parks'),
  park: (parkId: string) =>
    request<ParkSummary>(`/park/${encodeURIComponent(parkId)}`),
  orthos: (parkId: string) =>
    request<OrthoMeta[]>(`/park/${encodeURIComponent(parkId)}/orthos`),
  uploadOrtho: (parkId: string, form: FormData) =>
    request<OrthoMeta>(`/park/${encodeURIComponent(parkId)}/ortho`, {
      method: 'POST',
      body: form,
    }),
  getSettings: () => request<SettingsBlob>('/settings'),
  putSettings: (blob: SettingsBlob) =>
    request<SettingsBlob>('/settings', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(blob),
    }),
}
```

- [ ] **Step 2: TypeScript sanity check**

Run: `cd website/nextjs && npx tsc --noEmit`
Expected: no new errors in `lib/api.ts`. (Pre-existing errors in other files are out of scope; record them if any but do not fix.)

- [ ] **Step 3: Commit**

```bash
git add website/nextjs/lib/api.ts
git commit -m "feat(platform): typed API client with ApiError envelope"
```

---

## Task 5: Replace inline fetches in `page.tsx`

**Files:**
- Modify: `website/nextjs/app/platform/page.tsx`

This task is mechanical but tedious. There are ~10 fetch sites identified at lines 266, 294, 325, 349, 403, 432, 446, 460, 472, 483, 506 (line numbers may have shifted after Task 3 — re-grep). Replace each one.

- [ ] **Step 1: Add the import**

Add near the top of `page.tsx`:

```tsx
import { api, ApiError, API_BASE } from '@/lib/api'
```

Then delete the local `const API_BASE = ...` line.

- [ ] **Step 2: Get a fresh list of fetch sites**

Run: `grep -nE "fetch\(\\\`?\\\$\\{?API_BASE" website/nextjs/app/platform/page.tsx`
Use this list as the worksheet.

- [ ] **Step 3: For each site, replace with `api.*`**

Pattern:

```tsx
// before
const res = await fetch(`${API_BASE}/batch`, { method: 'POST', body: form })
if (!res.ok) { /* silent or alert */ }
const data = await res.json()

// after
let data: { job_id: string }
try {
  data = await api.batch(form)
} catch (err) {
  toast.error(err instanceof ApiError ? err.message : String(err))
  return
}
```

For the health-check effect (line ~266), wrap in try/catch and toast `info` on first connection failure (don't spam on every poll — use a ref to track whether we've already toasted offline).

For `reportUrl` (line ~432), replace the constructed URL with `api.reportUrl(activeJob.id, format)`.

- [ ] **Step 4: Add `const toast = useToast()` near the top of `PlatformPageBody`**

It must be inside the component, after other hooks.

- [ ] **Step 5: Re-grep to confirm no inline `fetch(${API_BASE}` remain**

Run: `grep -nE "fetch\\(\\\`\\\$\\{API_BASE\\}" website/nextjs/app/platform/page.tsx`
Expected: empty (apart from the deleted line in the diff). Inline file-download `<a href={api.reportUrl(...)}>` is fine.

- [ ] **Step 6: TypeScript check**

Run: `cd website/nextjs && npx tsc --noEmit 2>&1 | grep -E "(app/platform/page|lib/api)"`
Expected: no new errors in these files.

- [ ] **Step 7: Hard-reload `/platform` in the browser and confirm the page still mounts**

Open `http://localhost:3000/platform`. Check the browser console — should be no red errors.

- [ ] **Step 8: Commit**

```bash
git add website/nextjs/app/platform/page.tsx
git commit -m "refactor(platform): route page.tsx fetches through typed api client"
```

---

## Task 6: Walk Operations tab + fix

**Files:**
- Modify (as needed): `website/nextjs/app/platform/page.tsx`, `website/nextjs/components/Platform/AnomalyMap.tsx`, `platform/api/app.py`

Goal: full happy-path of the Operations tab works against the live API + synthetic fixture.

- [ ] **Step 1: Zip the fixture**

Run: `cd tests/fixtures && zip -rq sample_mission.zip sample_mission/ && ls -lh sample_mission.zip && cd -`
Expected: ~1–5 MB zip file at `tests/fixtures/sample_mission.zip`.

- [ ] **Step 2: Open the Operations tab in the browser**

Navigate to `http://localhost:3000/platform`. Confirm it's on Operations. Open DevTools → Network + Console.

- [ ] **Step 3: Walk these clicks and observe**

For each, record what happens (works / fails / silent). Apply fixes inline, one commit per fix with message `fix(platform): <symptom>`.

1. Park ID input — type/edit, confirm state updates.
2. Altitude input — same.
3. File picker — choose `tests/fixtures/sample_mission.zip`.
4. Start batch button — POST `/batch`. Expect a `job_id` in the network tab.
5. Progress polling — `/status/{job_id}` every ~2s. UI must show advancing progress.
6. On completion, the job in the list flips to succeeded.
7. Map renders markers from `/map/{job_id}`.
8. Report buttons (JSON / Excel / GeoJSON / PDF) — each triggers a download.

- [ ] **Step 4: For each failure, follow this triage**

- 4xx from API → the FastAPI endpoint likely rejected the payload. Fix the UI to send the right shape, OR fix `platform/api/app.py` if the contract is wrong. Prefer fixing the side that's wrong against its own docs.
- 5xx from API → server-side bug. Read `logs/api.log`. Fix in `platform/api/app.py` minimally.
- Toast appears with sensible text → good, leave as-is.
- Silent break (button does nothing, no toast) → wrap the handler in try/catch + `toast.error(...)`.
- Map renders blank but `/map/{job_id}` returned 200 → check `AnomalyMap.tsx`'s expected data shape against the actual response (Task 10 will harden this).

- [ ] **Step 5: After all clicks pass, re-run the full flow once more from a fresh page load**

Goal: confirm no state-cleanup bugs.

- [ ] **Step 6: Commit (if not already committed during fixes)**

```bash
git add -A && git status
git commit -m "fix(platform): operations tab end-to-end with synthetic fixture" || true
```

---

## Task 7: Walk Inspect tab + fix

**Files:** as needed.

- [ ] **Step 1: Switch to the Inspect tab**

- [ ] **Step 2: Walk the clicks**

1. Choose a single image — `tests/fixtures/sample_mission/thermal/img_001.jpg`.
2. Submit. Expect POST `/inspect` and a response with detections + annotated image.
3. Annotated image renders.
4. Detections list shows class, confidence, severity badge.

- [ ] **Step 3: Triage failures using Task 6 Step 4's rules.**

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix(platform): inspect tab single-image flow" || true
```

---

## Task 8: Walk History tab + fix

**Files:** as needed.

- [ ] **Step 1: Switch to History tab**

- [ ] **Step 2: Walk the clicks**

1. Park dropdown — populated from `/parks`. The park ID used in Task 6 should appear.
2. Select that park — `/park/{id}` returns summary.
3. UI shows the inspection completed in Task 6.

- [ ] **Step 3: Triage. If `/parks` returns empty even after a successful batch, the DB write didn't happen — investigate `platform/pipeline/orchestrator.py`'s `session_scope` writes.**

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix(platform): history tab park list + summary" || true
```

---

## Task 9: Walk Settings tab + fix

**Files:** as needed.

- [ ] **Step 1: Switch to Settings tab**

- [ ] **Step 2: Walk the clicks**

1. Settings load from `/settings` — confidence threshold, altitude, etc. populate.
2. Edit confidence to 0.30.
3. Save — PUT `/settings`. Expect success toast or visible success state.
4. Reload page → new value persists.

- [ ] **Step 3: Triage. If `/settings` returns 404, the endpoint isn't implemented; either implement it minimally in `platform/api/app.py` (read/write `platform/config/settings.yaml`) or remove the Settings tab from this phase's acceptance (document in runbook).**

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix(platform): settings tab load + save round-trip" || true
```

---

## Task 10: AnomalyMap real-data check

**Files:**
- Modify: `website/nextjs/components/Platform/AnomalyMap.tsx`

- [ ] **Step 1: Pull the live `/map/{job_id}` payload to a file for inspection**

Run (replace `<job_id>` with the one from Task 6):
```bash
curl -fsS "http://localhost:8000/map/<job_id>" | python -m json.tool | head -80
```

- [ ] **Step 2: Compare its shape to what `AnomalyMap.tsx` expects**

Open `website/nextjs/components/Platform/AnomalyMap.tsx`. Find the `Anomaly` type and the function that consumes `mapData`. Confirm field names match (e.g. `lat`/`lon` vs `latitude`/`longitude`, `severity` casing).

- [ ] **Step 3: If they diverge, fix in the component (preferred), not the API**

The API is the contract; UI bends.

- [ ] **Step 4: Reload the Operations tab and confirm at least one marker is visible**

- [ ] **Step 5: Commit**

```bash
git add website/nextjs/components/Platform/AnomalyMap.tsx
git commit -m "fix(map): align AnomalyMap to live /map response shape" || true
```

---

## Task 11: Verify all four report downloads

**Files:** none, unless a download is broken.

- [ ] **Step 1: From the Operations tab, click each download in turn**

For each: JSON, Excel, GeoJSON, PDF.

- [ ] **Step 2: Inspect each downloaded file**

```bash
file ~/Downloads/inspection_report.json   # should report JSON or ASCII
file ~/Downloads/inspection_report.xlsx   # should report 'Microsoft Excel 2007+'
file ~/Downloads/park_anomaly_map.geojson # should report JSON
file ~/Downloads/inspection_report.pdf    # should report 'PDF document'
```

- [ ] **Step 3: If PDF fails because WeasyPrint system libs are missing, do NOT install them. Instead, surface the failure as a toast** (`api.reportUrl` returns a URL, so the failure shows in the browser). Add a fallback in the UI: catch a 5xx on PDF and toast a useful message including the instruction "install libpango per docs/INSTALLATION.md".

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix(reports): visible failure when PDF deps missing" || true
```

---

## Task 12: Write the Operator Runbook

**Files:**
- Create: `docs/OPERATOR_RUNBOOK.md`

- [ ] **Step 1: Write the runbook**

```markdown
# Operator Runbook — Axalon Inspection Platform

The 10-minute walk through a real local inspection from zero.

## Prereqs

- `./run.sh setup` has completed once
- `ml/checkpoints/best.pt` exists (~22 MB)
- Optional: WeasyPrint system libs (for PDF reports). See `docs/INSTALLATION.md`.

## 1. Generate the sample mission

```bash
python scripts/make_sample_mission.py
cd tests/fixtures && zip -rq sample_mission.zip sample_mission/ && cd -
```

You should see `tests/fixtures/sample_mission.zip` (~1–5 MB).

## 2. Start the services

```bash
./run.sh all
```

In another terminal, verify:

```bash
curl -fsS http://localhost:8000/health
curl -fsS -o /dev/null -w '%{http_code}\n' http://localhost:3000/platform
```

Both should return `200`.

## 3. Open the platform UI

Open `http://localhost:3000/platform` in a browser.

## 4. Run a batch inspection

On the **Operations** tab:

1. Park ID: `SOLAR_PARK_DEMO`
2. Altitude: `42`
3. Choose file: `tests/fixtures/sample_mission.zip`
4. Click **Start batch**.
5. Wait for progress to reach 100% (~30–90 seconds depending on GPU/CPU).
6. The map below should show markers from the detected anomalies.

## 5. Download reports

Click each of the four report buttons. Files land in your default Downloads folder.

## 6. Inspect a single image

On the **Inspect** tab:

1. Choose file: `tests/fixtures/sample_mission/thermal/img_001.jpg`.
2. Submit. Annotated image + detection list appear.

## 7. Browse history

On the **History** tab:

1. Park dropdown should include `SOLAR_PARK_DEMO`.
2. Select it. You should see the inspection from step 4.

## 8. Tweak settings

On the **Settings** tab:

1. Change confidence to `0.30`.
2. Save.
3. Reload page — value persists.

## Troubleshooting

- **Any silent failure** is a bug. Every failure should produce a visible toast bottom-right of the screen. If it didn't, that's a Phase 1 regression — file it.
- **PDF download fails** — likely WeasyPrint libs missing. Install per `docs/INSTALLATION.md` or use JSON / Excel / GeoJSON instead.
- **No detections in the map** — the synthetic hotspots may not match the trained model distribution. Re-run `python scripts/make_sample_mission.py --seed 12345` to get a fresh batch.
```

- [ ] **Step 2: Commit**

```bash
git add docs/OPERATOR_RUNBOOK.md
git commit -m "docs: operator runbook for platform Phase 1 golden path"
```

---

## Task 13: Final acceptance pass

**Files:** none.

- [ ] **Step 1: Stop and restart everything cleanly**

```bash
./run.sh stop
rm -rf website/nextjs/.next
./run.sh all
```

- [ ] **Step 2: From a fresh checkout-like state, follow `docs/OPERATOR_RUNBOOK.md` verbatim**

If anything in the runbook fails or is ambiguous, fix the underlying issue OR fix the runbook. Commit each.

- [ ] **Step 3: Check the acceptance list from the spec**

```
- [ ] `./run.sh all` boots clean
- [ ] make_sample_mission.py regenerates without errors
- [ ] Operations: upload → 100% → map markers → 4 reports
- [ ] Inspect: single-image annotated result
- [ ] History: park list + selected-park summary
- [ ] Settings: load + save round-trip
- [ ] Every fetch error produces a visible toast
- [ ] OPERATOR_RUNBOOK.md matches reality
```

For each unchecked item, fix and re-verify. Do not mark Phase 1 done until all are ticked.

- [ ] **Step 4: Final commit (if any)**

```bash
git add -A
git commit -m "chore(platform): Phase 1 acceptance pass" || echo "nothing to commit"
```

- [ ] **Step 5: Stop services**

```bash
./run.sh stop
```

---

## Done

When Task 13 passes, Phase 1 is complete. Move to Phase 2 (Park Map detail page + automated tests) via a fresh brainstorming session.
