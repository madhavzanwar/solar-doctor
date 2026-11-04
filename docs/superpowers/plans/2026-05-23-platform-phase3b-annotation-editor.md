# Platform Phase 3b — Annotation Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a canvas-based bounding box editor to the Inspect tab, letting operators draw correction boxes over thermal images, assign classes from the 11 canonical classes, and persist them to the database.

**Architecture:** A new `Correction` DB table stores user-drawn boxes keyed by inspect `job_id` (the UUID returned by `POST /inspect` — these live in-memory, so Correction uses a plain VARCHAR key with no FK constraint). Four CRUD REST endpoints expose corrections. A pure `canvasCoords.ts` utility module is extracted for testability. The `AnnotationCanvas` component renders the thermal image on a `<canvas>`, overlays YOLO detections (blue) and user corrections (green), handles drag-to-draw, click-to-select, and delete. A class picker appears inline after each new box is drawn.

**Tech Stack:** SQLAlchemy (SQLite), FastAPI, React `<canvas>` API, TypeScript, Vitest

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `platform/db/models.py` | Modify | Add `Correction` ORM model |
| `platform/db/migrate.py` | Modify | Ensure `corrections` table is created on startup |
| `platform/api/app.py` | Modify | Add 4 CRUD endpoints + `_serialize_correction` helper |
| `website/nextjs/lib/api.ts` | Modify | Add `Correction`, `CorrectionCreate` types + 3 API methods |
| `website/nextjs/components/Platform/canvasCoords.ts` | Create | Pure `normalizeBox`, `yoloToCanvas`, `isTooSmall` utilities |
| `website/nextjs/components/Platform/AnnotationCanvas.tsx` | Create | Canvas component: image + boxes + draw/select/delete/save |
| `website/nextjs/components/Platform/InspectTab.tsx` | Modify | Add `natDims` state, pass `onNatSize` to InspectPreview, render AnnotationCanvas |
| `tests/backend/test_corrections.py` | Create | CRUD endpoint tests |
| `website/nextjs/tests/unit/canvasCoords.test.ts` | Create | Coordinate utility unit tests |

---

### Task 1: Correction DB model

**Files:**
- Modify: `platform/db/models.py`
- Test: `tests/backend/test_corrections.py`

- [ ] **Step 1: Write a failing test that checks the corrections table exists**

```python
# tests/backend/test_corrections.py
import pytest
from sqlalchemy import create_engine, text


@pytest.fixture
def engine():
    from axalon.db.session import init_db, get_engine
    init_db("sqlite:///:memory:")
    return get_engine()


def test_corrections_table_exists(engine):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='corrections'")
        ).fetchone()
    assert row is not None, "corrections table must exist after init_db"
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd /home/parakh/Desktop/AxalonSystems
python3 -m pytest tests/backend/test_corrections.py::test_corrections_table_exists -v
```

Expected: FAIL — `AssertionError: corrections table must exist after init_db`

- [ ] **Step 3: Add Correction model to models.py**

Open `platform/db/models.py`. After the closing line of `PanelFault`, add:

```python
class Correction(Base):
    """User-drawn annotation box on a single-image inspect result."""
    __tablename__ = "corrections"
    id         = Column(Integer, primary_key=True, autoincrement=True)
    job_id     = Column(String, nullable=False, index=True)  # from /inspect job_id UUID
    image_id   = Column(String, nullable=True)               # thermal filename stem
    panel_id   = Column(String, nullable=True)               # "R3-C7" if known
    class_     = Column("class", String, nullable=False)
    class_id   = Column(Integer, nullable=True)
    severity   = Column(String, nullable=True)
    bbox_norm  = Column(Text, nullable=False)                # JSON "[x1n,y1n,x2n,y2n]" 0-1 coords
    notes      = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

- [ ] **Step 4: Run test to verify it passes**

```bash
python3 -m pytest tests/backend/test_corrections.py::test_corrections_table_exists -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add platform/db/models.py tests/backend/test_corrections.py
git commit -m "feat(db): add Correction model for annotation editor"
```

---

### Task 2: Backend CRUD endpoints

**Files:**
- Modify: `platform/api/app.py`
- Test: `tests/backend/test_corrections.py`

- [ ] **Step 1: Write failing tests for all 4 endpoints**

Append to `tests/backend/test_corrections.py`:

```python
from fastapi.testclient import TestClient
from unittest.mock import patch


@pytest.fixture
def client(engine):
    from axalon.db.session import _SessionLocal
    with patch("axalon.api.app.get_session", lambda: _SessionLocal()):
        from axalon.api.app import app
        with TestClient(app) as c:
            yield c


def test_list_corrections_empty(client):
    r = client.get("/corrections/job-abc")
    assert r.status_code == 200
    assert r.json() == []


def test_create_correction(client):
    payload = {"class_": "cell", "class_id": 0, "severity": "MEDIUM", "bbox_norm": [0.1, 0.2, 0.4, 0.5]}
    r = client.post("/corrections/job-abc", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["id"] > 0
    assert body["class"] == "cell"
    assert body["job_id"] == "job-abc"
    assert body["bbox_norm"] == [0.1, 0.2, 0.4, 0.5]


def test_delete_correction(client):
    payload = {"class_": "module", "class_id": 2, "severity": "MEDIUM", "bbox_norm": [0.0, 0.0, 0.5, 0.5]}
    created_id = client.post("/corrections/job-del", json=payload).json()["id"]
    r = client.delete(f"/corrections/job-del/{created_id}")
    assert r.status_code == 204
    assert client.get("/corrections/job-del").json() == []


def test_invalid_job_id_rejected(client):
    r = client.get("/corrections/../etc/passwd")
    assert r.status_code == 400
```

- [ ] **Step 2: Run to confirm they all fail**

```bash
python3 -m pytest tests/backend/test_corrections.py -v
```

Expected: 4 FAILs (routes not implemented)

- [ ] **Step 3: Add Correction to the models import in app.py**

Find the line in `platform/api/app.py` (~line 37) that reads:

```python
from axalon.db.models import Park, Inspection, PanelFault, Detection as DbDetection, FAULT_OPEN, FAULT_STALE, FAULT_RESOLVED
```

Add `Correction` to it:

```python
from axalon.db.models import Park, Inspection, PanelFault, Detection as DbDetection, FAULT_OPEN, FAULT_STALE, FAULT_RESOLVED, Correction
```

- [ ] **Step 4: Add `_serialize_correction` helper and the 3 new endpoints to app.py**

Insert after the `/park/{park_id}/diff` endpoint and before `/parks`:

```python
# ── Corrections (annotation editor) ──────────────────────────────────────────

def _serialize_correction(c: Correction) -> dict:
    import json as _json
    return {
        "id": c.id,
        "job_id": c.job_id,
        "class": c.class_,
        "class_id": c.class_id,
        "severity": c.severity,
        "bbox_norm": _json.loads(c.bbox_norm) if c.bbox_norm else [],
        "notes": c.notes,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


@app.get("/corrections/{job_id}")
def list_corrections(job_id: str):
    """List all user correction boxes for an inspect job."""
    job_id = _validate_job_id(job_id)
    session = get_session()
    try:
        rows = session.query(Correction).filter(Correction.job_id == job_id).all()
        return [_serialize_correction(r) for r in rows]
    finally:
        session.close()


@app.post("/corrections/{job_id}", status_code=201)
def create_correction(job_id: str, body: dict):
    """Persist a user-drawn bounding box correction."""
    import json as _json
    job_id = _validate_job_id(job_id)
    class_ = str(body.get("class_", ""))[:64]
    if not class_:
        raise HTTPException(status_code=400, detail="class_ is required")
    class_id = int(body.get("class_id", 0))
    severity = str(body.get("severity", "MEDIUM"))[:16]
    bbox = body.get("bbox_norm", [0, 0, 1, 1])
    notes = str(body.get("notes", ""))[:500] if body.get("notes") else None
    session = get_session()
    try:
        c = Correction(
            job_id=job_id,
            class_=class_,
            class_id=class_id,
            severity=severity,
            bbox_norm=_json.dumps(bbox),
            notes=notes,
        )
        session.add(c)
        session.commit()
        session.refresh(c)
        return JSONResponse(content=_serialize_correction(c), status_code=201)
    finally:
        session.close()


@app.delete("/corrections/{job_id}/{correction_id}", status_code=204)
def delete_correction(job_id: str, correction_id: int):
    """Delete a user correction by ID."""
    job_id = _validate_job_id(job_id)
    session = get_session()
    try:
        c = session.query(Correction).filter(
            Correction.id == correction_id,
            Correction.job_id == job_id,
        ).first()
        if c is None:
            raise HTTPException(status_code=404, detail="Correction not found")
        session.delete(c)
        session.commit()
        from fastapi import Response as _Resp
        return _Resp(status_code=204)
    finally:
        session.close()
```

- [ ] **Step 5: Run tests to verify they all pass**

```bash
python3 -m pytest tests/backend/test_corrections.py -v
```

Expected: 4 PASSes

- [ ] **Step 6: Commit**

```bash
git add platform/api/app.py tests/backend/test_corrections.py
git commit -m "feat(api): CRUD endpoints for annotation corrections"
```

---

### Task 3: API client additions

**Files:**
- Modify: `website/nextjs/lib/api.ts`

- [ ] **Step 1: Add types after the `ParkDiff` type in api.ts**

```typescript
export type Correction = {
  id: number
  job_id: string
  class: string
  class_id: number | null
  severity: string | null
  bbox_norm: [number, number, number, number]
  notes: string | null
  created_at: string | null
}

export type CorrectionCreate = {
  class_: string
  class_id: number
  severity: string
  bbox_norm: [number, number, number, number]
  notes?: string
}
```

- [ ] **Step 2: Add methods to the `api` object after `parkDiff`**

```typescript
  corrections: (jobId: string) =>
    request<Correction[]>(`/corrections/${encodeURIComponent(jobId)}`),
  addCorrection: (jobId: string, body: CorrectionCreate) =>
    request<Correction>(`/corrections/${encodeURIComponent(jobId)}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    }),
  deleteCorrection: (jobId: string, id: number) =>
    request<void>(`/corrections/${encodeURIComponent(jobId)}/${id}`, { method: 'DELETE' }),
```

- [ ] **Step 3: Verify TypeScript compiles**

```bash
cd website/nextjs && npx tsc --noEmit 2>&1
```

Expected: no output (zero errors)

- [ ] **Step 4: Commit**

```bash
git add website/nextjs/lib/api.ts
git commit -m "feat(api-client): Correction types and correction methods"
```

---

### Task 4: Canvas coordinate utilities

**Files:**
- Create: `website/nextjs/components/Platform/canvasCoords.ts`
- Create: `website/nextjs/tests/unit/canvasCoords.test.ts`

- [ ] **Step 1: Write failing tests**

```typescript
// website/nextjs/tests/unit/canvasCoords.test.ts
import { describe, it, expect } from 'vitest'
import { normalizeBox, yoloToCanvas, isTooSmall } from '@/components/Platform/canvasCoords'

describe('normalizeBox', () => {
  it('normalizes drag coords to 0-1 range', () => {
    const r = normalizeBox(10, 20, 110, 120, 200, 200)
    expect(r).toEqual({ x1n: 0.05, y1n: 0.1, x2n: 0.55, y2n: 0.6 })
  })

  it('handles reversed drag (right-to-left)', () => {
    const r = normalizeBox(110, 120, 10, 20, 200, 200)
    expect(r.x1n).toBeLessThan(r.x2n)
    expect(r.y1n).toBeLessThan(r.y2n)
  })

  it('clamps to [0,1]', () => {
    const r = normalizeBox(0, 0, 200, 200, 200, 200)
    expect(r.x2n).toBe(1)
    expect(r.y2n).toBe(1)
  })
})

describe('yoloToCanvas', () => {
  it('scales pixel coords from natural image size to canvas size', () => {
    const r = yoloToCanvas(100, 50, 200, 150, 400, 300, 800, 600)
    expect(r).toEqual({ x1c: 200, y1c: 100, x2c: 400, y2c: 300 })
  })

  it('handles non-square canvas scaling', () => {
    const r = yoloToCanvas(0, 0, 100, 100, 100, 200, 50, 50)
    expect(r.x2c).toBe(50)
    expect(r.y2c).toBe(25)
  })
})

describe('isTooSmall', () => {
  it('returns true when box width < 1% of canvas', () => {
    expect(isTooSmall(0.0, 0.0, 0.005, 0.1)).toBe(true)
  })

  it('returns true when box height < 1% of canvas', () => {
    expect(isTooSmall(0.0, 0.0, 0.1, 0.005)).toBe(true)
  })

  it('returns false for a valid box', () => {
    expect(isTooSmall(0.1, 0.1, 0.4, 0.4)).toBe(false)
  })
})
```

- [ ] **Step 2: Run to confirm they fail**

```bash
cd website/nextjs && npm test -- tests/unit/canvasCoords.test.ts
```

Expected: FAIL — cannot find module `@/components/Platform/canvasCoords`

- [ ] **Step 3: Create canvasCoords.ts**

```typescript
// website/nextjs/components/Platform/canvasCoords.ts

export function normalizeBox(
  x0: number, y0: number,
  x1: number, y1: number,
  canvasW: number, canvasH: number,
): { x1n: number; y1n: number; x2n: number; y2n: number } {
  return {
    x1n: Math.min(x0, x1) / canvasW,
    y1n: Math.min(y0, y1) / canvasH,
    x2n: Math.max(x0, x1) / canvasW,
    y2n: Math.max(y0, y1) / canvasH,
  }
}

export function yoloToCanvas(
  x1: number, y1: number, x2: number, y2: number,
  natW: number, natH: number,
  canvasW: number, canvasH: number,
): { x1c: number; y1c: number; x2c: number; y2c: number } {
  const sx = canvasW / natW
  const sy = canvasH / natH
  return { x1c: x1 * sx, y1c: y1 * sy, x2c: x2 * sx, y2c: y2 * sy }
}

export function isTooSmall(x1n: number, y1n: number, x2n: number, y2n: number): boolean {
  return (x2n - x1n) < 0.01 || (y2n - y1n) < 0.01
}
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd website/nextjs && npm test -- tests/unit/canvasCoords.test.ts
```

Expected: 7 PASSes

- [ ] **Step 5: Commit**

```bash
git add website/nextjs/components/Platform/canvasCoords.ts website/nextjs/tests/unit/canvasCoords.test.ts
git commit -m "feat(canvas): coordinate utilities + tests"
```

---

### Task 5: AnnotationCanvas component

**Files:**
- Create: `website/nextjs/components/Platform/AnnotationCanvas.tsx`

- [ ] **Step 1: Create AnnotationCanvas.tsx**

```typescript
// website/nextjs/components/Platform/AnnotationCanvas.tsx
'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { api, ApiError, type Correction } from '@/lib/api'
import { useToast } from '@/components/Platform/Toast'
import { normalizeBox, yoloToCanvas, isTooSmall } from '@/components/Platform/canvasCoords'

export const CANONICAL_CLASSES = [
  'cell', 'cell-multi', 'module', 'string', 'bypass-diode',
  'offline-module', 'vegetation-shading', 'soiling', 'short-circuit',
  'hot-spot-low', 'hot-spot-high',
] as const

const SEVERITY_FOR_CLASS: Record<string, string> = {
  cell: 'MEDIUM', 'cell-multi': 'MEDIUM', module: 'MEDIUM',
  string: 'CRITICAL', 'bypass-diode': 'CRITICAL',
  'offline-module': 'HIGH', 'vegetation-shading': 'LOW', soiling: 'LOW',
  'short-circuit': 'HIGH', 'hot-spot-low': 'HIGH', 'hot-spot-high': 'CRITICAL',
}

type YoloBox = {
  x1: number; y1: number; x2: number; y2: number
  class_: string; severity: string; confidence: number
}

type LocalBox = {
  id: string
  serverId?: number
  x1n: number; y1n: number; x2n: number; y2n: number
  class_: string; class_id: number; severity: string
}

type Drawing = { x0: number; y0: number; x1: number; y1: number }

interface Props {
  jobId: string
  imageFile: File
  natW: number
  natH: number
  yoloBoxes: YoloBox[]
}

export function AnnotationCanvas({ jobId, imageFile, natW, natH, yoloBoxes }: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const imgRef = useRef<HTMLImageElement | null>(null)
  const toast = useToast()

  const [boxes, setBoxes] = useState<LocalBox[]>([])
  const [drawing, setDrawing] = useState<Drawing | null>(null)
  const [picker, setPicker] = useState<{ id: string; class_: string } | null>(null)
  const [selected, setSelected] = useState<string | null>(null)

  // Load image blob → HTMLImageElement
  useEffect(() => {
    const url = URL.createObjectURL(imageFile)
    const img = new Image()
    img.src = url
    img.onload = () => { imgRef.current = img }
    return () => URL.revokeObjectURL(url)
  }, [imageFile])

  // Load existing corrections from server
  useEffect(() => {
    api.corrections(jobId)
      .then((list) =>
        setBoxes(
          list.map((c: Correction) => ({
            id: String(c.id),
            serverId: c.id,
            x1n: c.bbox_norm[0], y1n: c.bbox_norm[1],
            x2n: c.bbox_norm[2], y2n: c.bbox_norm[3],
            class_: c.class, class_id: c.class_id ?? 0,
            severity: c.severity ?? 'MEDIUM',
          })),
        ),
      )
      .catch(() => {}) // no prior corrections — ignore
  }, [jobId])

  const redraw = useCallback(() => {
    const canvas = canvasRef.current
    const img = imgRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    canvas.width = canvas.offsetWidth || 640
    canvas.height = canvas.offsetHeight || 480
    const cw = canvas.width, ch = canvas.height

    if (img) ctx.drawImage(img, 0, 0, cw, ch)
    else { ctx.fillStyle = '#0f172a'; ctx.fillRect(0, 0, cw, ch) }

    // YOLO detections (blue)
    ctx.font = 'bold 10px Inter,sans-serif'
    for (const b of yoloBoxes) {
      const { x1c, y1c, x2c, y2c } = yoloToCanvas(b.x1, b.y1, b.x2, b.y2, natW, natH, cw, ch)
      ctx.strokeStyle = '#3b82f6'; ctx.lineWidth = 2
      ctx.strokeRect(x1c, y1c, x2c - x1c, y2c - y1c)
      ctx.fillStyle = 'rgba(59,130,246,0.1)'
      ctx.fillRect(x1c, y1c, x2c - x1c, y2c - y1c)
      ctx.fillStyle = '#3b82f6'
      ctx.fillText(`${b.class_} ${Math.round(b.confidence * 100)}%`, x1c + 2, y1c - 3)
    }

    // User corrections (green / dark-bordered if selected)
    for (const b of boxes) {
      const x1c = b.x1n * cw, y1c = b.y1n * ch
      const x2c = b.x2n * cw, y2c = b.y2n * ch
      const isSel = b.id === selected
      ctx.strokeStyle = isSel ? '#0f172a' : '#16a34a'
      ctx.lineWidth = isSel ? 3 : 2
      ctx.strokeRect(x1c, y1c, x2c - x1c, y2c - y1c)
      ctx.fillStyle = 'rgba(22,163,74,0.1)'
      ctx.fillRect(x1c, y1c, x2c - x1c, y2c - y1c)
      ctx.fillStyle = '#16a34a'
      ctx.fillText(b.class_, x1c + 2, y1c - 3)
    }

    // Active drag (amber dashed)
    if (drawing) {
      const { x0, y0, x1, y1 } = drawing
      ctx.strokeStyle = '#f59e0b'; ctx.lineWidth = 2
      ctx.setLineDash([4, 3])
      ctx.strokeRect(x0, y0, x1 - x0, y1 - y0)
      ctx.setLineDash([])
    }
  }, [yoloBoxes, boxes, drawing, selected, natW, natH])

  useEffect(() => { redraw() }, [redraw])

  function pt(e: React.MouseEvent<HTMLCanvasElement>) {
    const r = canvasRef.current!.getBoundingClientRect()
    return { x: e.clientX - r.left, y: e.clientY - r.top }
  }

  function onMouseDown(e: React.MouseEvent<HTMLCanvasElement>) {
    const { x, y } = pt(e)
    setDrawing({ x0: x, y0: y, x1: x, y1: y })
    setSelected(null)
    setPicker(null)
  }

  function onMouseMove(e: React.MouseEvent<HTMLCanvasElement>) {
    if (!drawing) return
    const { x, y } = pt(e)
    setDrawing((d) => d ? { ...d, x1: x, y1: y } : null)
  }

  function onMouseUp() {
    if (!drawing) return
    const canvas = canvasRef.current!
    const norm = normalizeBox(drawing.x0, drawing.y0, drawing.x1, drawing.y1, canvas.width, canvas.height)
    setDrawing(null)
    if (isTooSmall(norm.x1n, norm.y1n, norm.x2n, norm.y2n)) return
    const id = Math.random().toString(36).slice(2)
    setBoxes((b) => [...b, { id, ...norm, class_: 'cell', class_id: 0, severity: 'MEDIUM' }])
    setSelected(id)
    setPicker({ id, class_: 'cell' })
  }

  async function saveCorrection(id: string, class_: string) {
    const class_id = CANONICAL_CLASSES.indexOf(class_ as typeof CANONICAL_CLASSES[number])
    const severity = SEVERITY_FOR_CLASS[class_] ?? 'MEDIUM'
    setBoxes((b) => b.map((x) => x.id === id ? { ...x, class_, class_id, severity } : x))
    setPicker(null)
    const box = boxes.find((b) => b.id === id)
    if (!box) return
    try {
      const saved = await api.addCorrection(jobId, {
        class_, class_id, severity,
        bbox_norm: [box.x1n, box.y1n, box.x2n, box.y2n],
      })
      setBoxes((b) => b.map((x) => x.id === id ? { ...x, serverId: saved.id } : x))
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : 'Failed to save correction')
    }
  }

  async function deleteSelected() {
    const box = boxes.find((b) => b.id === selected)
    if (!box) return
    if (box.serverId) {
      try { await api.deleteCorrection(jobId, box.serverId) } catch { /* swallow network errors */ }
    }
    setBoxes((b) => b.filter((x) => x.id !== selected))
    setSelected(null)
  }

  return (
    <div style={{ position: 'relative', marginTop: 14 }}>
      <canvas
        ref={canvasRef}
        style={{ width: '100%', maxHeight: 480, display: 'block', cursor: 'crosshair', borderRadius: 8, background: '#0f172a' }}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUp}
      />

      {picker && (
        <div style={{ position: 'absolute', top: 8, right: 8, background: '#fff', border: '1px solid #e2e8f0', borderRadius: 8, padding: 12, zIndex: 10, minWidth: 200, boxShadow: '0 4px 12px rgba(0,0,0,0.1)' }}>
          <div style={{ fontSize: 12, fontWeight: 700, marginBottom: 8 }}>Assign class</div>
          <select
            value={picker.class_}
            onChange={(e) => setPicker((p) => p ? { ...p, class_: e.target.value } : null)}
            style={{ width: '100%', marginBottom: 8 }}
          >
            {CANONICAL_CLASSES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
          <button
            className="primary"
            style={{ height: 30, marginTop: 0, fontSize: 12 }}
            onClick={() => saveCorrection(picker.id, picker.class_)}
          >
            Save
          </button>
          <button
            style={{ marginLeft: 6, height: 30, fontSize: 12, border: '1px solid #cbd5e1', borderRadius: 6, background: '#fff', cursor: 'pointer', padding: '0 10px' }}
            onClick={() => {
              setPicker(null)
              setBoxes((b) => b.filter((x) => x.id !== picker.id))
              setSelected(null)
            }}
          >
            Cancel
          </button>
        </div>
      )}

      {selected && !picker && (
        <button
          style={{ position: 'absolute', top: 8, right: 8, background: '#fee2e2', border: '1px solid #fecaca', color: '#991b1b', borderRadius: 6, padding: '4px 10px', fontSize: 12, fontWeight: 700, cursor: 'pointer' }}
          onClick={deleteSelected}
        >
          Delete
        </button>
      )}

      <p style={{ fontSize: 11, color: '#64748b', marginTop: 6 }}>
        Drag to draw a correction · click a green box to select · Blue = model · Green = correction
      </p>
    </div>
  )
}
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
cd website/nextjs && npx tsc --noEmit 2>&1
```

Expected: no output

- [ ] **Step 3: Commit**

```bash
git add website/nextjs/components/Platform/AnnotationCanvas.tsx
git commit -m "feat(ui): AnnotationCanvas component"
```

---

### Task 6: Wire AnnotationCanvas into InspectTab

**Files:**
- Modify: `website/nextjs/components/Platform/InspectTab.tsx`

- [ ] **Step 1: Read InspectTab.tsx**

Identify:
- Where `InspectPreview` component is defined (likely an inline function near the bottom)
- Where `InspectPreview` is rendered in the result panel section
- The `inspectResult` and `inspectFile` state variables

- [ ] **Step 2: Add `onNatSize` prop to InspectPreview**

Find the `InspectPreview` function inside InspectTab.tsx. It currently has props `{ file, detections }`. Update its props interface to:

```typescript
function InspectPreview({
  file,
  detections,
  onNatSize,
}: {
  file: File
  detections: InspectDetection[]
  onNatSize?: (w: number, h: number) => void
}) {
```

In the `<img>` element's `onLoad` handler, add the callback:

```typescript
onLoad={(e) => {
  const img = e.currentTarget
  setNat({ w: img.naturalWidth, h: img.naturalHeight })
  onNatSize?.(img.naturalWidth, img.naturalHeight)
}}
```

- [ ] **Step 3: Add `natDims` state and AnnotationCanvas import to InspectTab**

At the top of InspectTab.tsx, add:

```typescript
import { AnnotationCanvas } from '@/components/Platform/AnnotationCanvas'
```

Inside the `InspectTab` function body, add:

```typescript
const [natDims, setNatDims] = useState<{ w: number; h: number } | null>(null)
```

- [ ] **Step 4: Pass `onNatSize` to InspectPreview and render AnnotationCanvas**

Find where `<InspectPreview file={inspectFile} detections={...} />` is rendered. Update to:

```tsx
<InspectPreview
  file={inspectFile}
  detections={inspectResult?.detections ?? []}
  onNatSize={(w, h) => setNatDims({ w, h })}
/>
```

Immediately after InspectPreview (still inside the result panel section), add:

```tsx
{inspectResult && natDims && inspectFile && (
  <AnnotationCanvas
    jobId={inspectResult.job_id}
    imageFile={inspectFile}
    natW={natDims.w}
    natH={natDims.h}
    yoloBoxes={(inspectResult.detections ?? []).map((d) => ({
      x1: d.bbox[0], y1: d.bbox[1], x2: d.bbox[2], y2: d.bbox[3],
      class_: d.class, severity: d.severity, confidence: d.confidence,
    }))}
  />
)}
```

- [ ] **Step 5: Verify TypeScript**

```bash
cd website/nextjs && npx tsc --noEmit 2>&1
```

Expected: no output

- [ ] **Step 6: Run full test suite**

```bash
cd website/nextjs && npm test
```

Expected: all tests pass

- [ ] **Step 7: Commit**

```bash
git add website/nextjs/components/Platform/InspectTab.tsx
git commit -m "feat(inspect): wire AnnotationCanvas for correction drawing"
```

---

## Acceptance Criteria

- [ ] `GET /corrections/{job_id}` returns `[]` for a fresh job
- [ ] `POST /corrections/{job_id}` returns 201 with the saved row
- [ ] `DELETE /corrections/{job_id}/{id}` returns 204 and removes the row
- [ ] `GET /corrections/../etc/passwd` returns 400
- [ ] Dragging on the Inspect canvas creates an amber dashed box while dragging, finalizes as green
- [ ] Class picker appears after drag-release; Cancel removes the box without saving
- [ ] Save calls `POST /corrections` and the box persists after page reload
- [ ] Clicking a saved green box shows Delete button; clicking Delete calls `DELETE /corrections/{job_id}/{id}`
- [ ] YOLO detections remain visible as blue boxes alongside user corrections
- [ ] `npx tsc --noEmit` → 0 errors
- [ ] `pytest tests/backend/test_corrections.py` → all pass
- [ ] `npm test` → all pass (including new canvasCoords tests)
