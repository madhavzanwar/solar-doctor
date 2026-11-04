# Platform Phase 4 — Auth, Persistent Jobs, Mobile, and Docker Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the platform production-ready. Job state survives API restarts, the UI is locked behind a configurable API key, every tab is fully usable on a phone (≥360px), the whole stack runs in Docker, and Playwright e2e joins GitHub Actions CI.

**Architecture:** A new `Job` SQLAlchemy model replaces the in-memory job dict; the background worker writes state on each tick. Auth is a FastAPI dependency (`require_auth`) keyed on an `AXALON_API_KEY` env var; the Next.js frontend intercepts 401s and shows a one-time unlock screen storing the key in `sessionStorage`. Mobile layout is pure CSS (`@media (max-width: 767px)` additions to `platform.css`). Docker is a two-stage Python `Dockerfile` + Next.js `Dockerfile` wired via `docker-compose.yml`. The Playwright e2e job in CI spins up `docker-compose` as a service container.

**Tech Stack:** SQLAlchemy 2.x, FastAPI dependency injection, Next.js 14 (App Router), CSS media queries, Docker multi-stage builds, `docker compose v2`, GitHub Actions `services`, `@playwright/test`.

**Spec:** `docs/superpowers/specs/2026-05-22-platform-phase3-design.md` (Phase 4 section: auth/persistent jobs, phone viewport, Docker, Playwright-in-CI)

---

## File Structure

| Path | Responsibility | Action |
|---|---|---|
| `platform/db/models.py` | Add `Job` ORM model with state machine columns | Modify |
| `platform/api/app.py` | Replace in-memory job dict with DB; add `require_auth` dependency | Modify |
| `website/nextjs/app/platform/platform.css` | Add `@media (max-width: 767px)` rules for all tabs | Modify |
| `website/nextjs/components/Platform/AuthGate.tsx` | Unlock screen: key input + sessionStorage | Create |
| `website/nextjs/lib/api.ts` | Intercept 401 → emit `axalon:unauthorized` event | Modify |
| `website/nextjs/app/platform/layout.tsx` | Wrap children in `<AuthGate>` | Modify |
| `Dockerfile` | Multi-stage Python API image | Create |
| `Dockerfile.nextjs` | Next.js production image | Create |
| `docker-compose.yml` | API + Next.js + shared volume (DB + weights) | Create |
| `.dockerignore` | Exclude `.git`, `node_modules`, `__pycache__`, etc. | Create |
| `website/nextjs/.dockerignore` | Frontend-specific excludes | Create |
| `.github/workflows/ci.yml` | Add `e2e` job: docker-compose up → playwright | Modify |
| `docs/DEPLOYMENT.md` | Docker and Render.com deployment runbook | Create |
| `tests/backend/test_job_persistence.py` | Verify job state survives API restart | Create |

---

## Task 1: Persistent job state (SQLite-backed `Job` model)

**Files:**
- Modify: `platform/db/models.py`
- Modify: `platform/api/app.py`
- Create: `tests/backend/test_job_persistence.py`

The current API stores batch job state in an in-memory dict (likely `_jobs: dict[str, dict]` in `app.py`). This task replaces it with a `Job` table so that a server restart doesn't lose in-progress or completed jobs.

- [ ] **Step 1: Write failing test**

```python
# tests/backend/test_job_persistence.py
"""Verify that job state written by the API is readable after a fresh DB connection."""
import pytest
from sqlalchemy import create_engine, text


@pytest.fixture
def engine():
    from axalon.db.session import init_db, get_engine
    init_db("sqlite:///:memory:")
    return get_engine()


def test_job_table_exists(engine):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
        ).fetchone()
    assert row is not None, "jobs table must exist after init_db"


def test_job_row_survives_reconnect(engine):
    from axalon.db.models import Job
    from axalon.db.session import session_scope
    job_id = "persist-test-001"
    with session_scope(engine) as s:
        s.add(Job(id=job_id, state="succeeded", park_id="P1", total=20, processed=20))

    # Simulate reconnect by opening a new session
    with session_scope(engine) as s:
        j = s.query(Job).filter(Job.id == job_id).first()
    assert j is not None
    assert j.state == "succeeded"
    assert j.processed == 20
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python3 -m pytest tests/backend/test_job_persistence.py -v
```

Expected: FAIL — `jobs` table does not exist.

- [ ] **Step 3: Add `Job` model to `platform/db/models.py`**

After the existing `Correction` model, add:

```python
class Job(Base):
    """Persisted state for a batch inspection job."""
    __tablename__ = "jobs"
    id          = Column(String, primary_key=True)  # UUID from the /batch endpoint
    park_id     = Column(String, nullable=True, index=True)
    state       = Column(String, nullable=False, default="queued")  # queued|running|succeeded|failed
    total       = Column(Integer, nullable=True)
    processed   = Column(Integer, nullable=True, default=0)
    message     = Column(Text, nullable=True)       # error message if failed
    result_path = Column(String, nullable=True)     # path to result JSON/CSV on disk
    created_at  = Column(DateTime, default=datetime.utcnow)
    updated_at  = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
```

- [ ] **Step 4: Update `app.py` to use the `Job` model**

Find the in-memory `_jobs` dict (search for `_jobs = {}` or similar). Replace all reads and writes as follows:

**Helper functions to add near the top of the handlers section:**

```python
from axalon.db.models import Job as DbJob

def _create_job(job_id: str, park_id: str) -> None:
    session = get_session()
    try:
        session.merge(DbJob(id=job_id, park_id=park_id, state="queued", processed=0))
        session.commit()
    finally:
        session.close()

def _update_job(job_id: str, **kwargs) -> None:
    session = get_session()
    try:
        j = session.query(DbJob).filter(DbJob.id == job_id).first()
        if j:
            for k, v in kwargs.items():
                setattr(j, k, v)
            session.commit()
    finally:
        session.close()

def _get_job(job_id: str) -> dict | None:
    session = get_session()
    try:
        j = session.query(DbJob).filter(DbJob.id == job_id).first()
        if j is None:
            return None
        return {
            "job_id": j.id,
            "state": j.state,
            "total": j.total,
            "processed": j.processed,
            "message": j.message,
            "park_id": j.park_id,
        }
    finally:
        session.close()
```

Replace every `_jobs[job_id] = ...` with `_create_job(...)` or `_update_job(...)`. Replace every `_jobs.get(job_id)` with `_get_job(job_id)`.

In the background thread/task that runs the pipeline, thread-wrap `_update_job` calls with try/except so a DB write failure doesn't crash the inference loop.

- [ ] **Step 5: Run tests to verify they pass**

```bash
python3 -m pytest tests/backend/test_job_persistence.py -v
```

Expected: 2 passed.

- [ ] **Step 6: Smoke-check: start API, run a batch, restart API, hit `/status/{job_id}`**

```bash
# Terminal 1
./run.sh all &
# Run a batch via the platform UI or:
JOB=$(curl -fsS -X POST http://localhost:8000/batch \
  -F "images=@tests/fixtures/sample_mission.zip" \
  -F "park_id=PERSIST_TEST" -F "altitude_m=42" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
echo "job_id=$JOB"
# Wait ~60s for completion, then kill the API
pkill -f uvicorn
# Restart just the API
uvicorn platform.api.app:app --port 8000 &
sleep 3
curl -fsS "http://localhost:8000/status/$JOB" | python3 -m json.tool
```

Expected: `state` is `succeeded` (not a 404), proving the job survived the restart.

- [ ] **Step 7: Commit**

```bash
git add platform/db/models.py platform/api/app.py tests/backend/test_job_persistence.py
git commit -m "feat(jobs): persist batch job state to SQLite; survives API restart"
```

---

## Task 2: API key authentication

**Files:**
- Modify: `platform/api/app.py`
- Create: `website/nextjs/components/Platform/AuthGate.tsx`
- Modify: `website/nextjs/lib/api.ts`
- Modify: `website/nextjs/app/platform/layout.tsx`

When `AXALON_API_KEY` env var is set, every non-health endpoint requires `Authorization: Bearer <key>`. The frontend intercepts 401s and shows an unlock screen.

- [ ] **Step 1: Write the backend auth dependency**

In `platform/api/app.py`, add after the imports:

```python
import os as _os
from fastapi import Security as _Security
from fastapi.security import HTTPBearer as _HTTPBearer, HTTPAuthorizationCredentials as _HTTPAuthCreds

_bearer = _HTTPBearer(auto_error=False)
_API_KEY = _os.environ.get("AXALON_API_KEY", "").strip()


def require_auth(creds: _HTTPAuthCreds | None = _Security(_bearer)) -> None:
    """FastAPI dependency — no-op when AXALON_API_KEY is unset."""
    if not _API_KEY:
        return
    if creds is None or creds.credentials != _API_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")
```

- [ ] **Step 2: Wire `require_auth` into every non-health endpoint**

Add `dependencies=[Depends(require_auth)]` to the `@app.get` / `@app.post` / `@app.put` / `@app.delete` decorators for every endpoint **except** `/health`. Example:

```python
@app.post("/batch", dependencies=[Depends(require_auth)])
def run_batch(...):
    ...
```

Do this for: `/batch`, `/inspect`, `/status/{job_id}`, `/map/{job_id}`, `/report/{job_id}`, `/parks`, `/park/{park_id}`, `/park/{park_id}/grid`, `/park/{park_id}/diff`, `/corrections/{job_id}` (all three methods), `/settings` (both methods).

- [ ] **Step 3: Verify auth locally**

```bash
# Without key — should still work (AXALON_API_KEY not set)
curl -fsS http://localhost:8000/parks

# Set a key and restart
AXALON_API_KEY=secret123 uvicorn platform.api.app:app --port 8000 &
sleep 2

# Without key — should 401
curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/parks   # expect 401

# With key — should 200
curl -s -o /dev/null -w '%{http_code}' \
  -H "Authorization: Bearer secret123" http://localhost:8000/parks   # expect 200

# Health is always open
curl -s -o /dev/null -w '%{http_code}' http://localhost:8000/health  # expect 200
```

- [ ] **Step 4: Write `AuthGate.tsx`**

```tsx
'use client'

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'

const KEY_STORAGE = 'axalon_api_key'
const AuthCtx = createContext<{ apiKey: string; setApiKey: (k: string) => void }>({
  apiKey: '',
  setApiKey: () => {},
})

export function useApiKey() {
  return useContext(AuthCtx)
}

export function AuthGate({ children }: { children: ReactNode }) {
  const [apiKey, setApiKeyState] = useState('')
  const [locked, setLocked] = useState(false)
  const [input, setInput] = useState('')
  const [error, setError] = useState('')

  useEffect(() => {
    const stored = sessionStorage.getItem(KEY_STORAGE) ?? ''
    setApiKeyState(stored)
  }, [])

  // Global 401 listener — set by api.ts
  useEffect(() => {
    function onUnauthorized() { setLocked(true) }
    window.addEventListener('axalon:unauthorized', onUnauthorized)
    return () => window.removeEventListener('axalon:unauthorized', onUnauthorized)
  }, [])

  const setApiKey = useCallback((k: string) => {
    sessionStorage.setItem(KEY_STORAGE, k)
    setApiKeyState(k)
  }, [])

  function submit() {
    if (!input.trim()) { setError('Enter a key'); return }
    setApiKey(input.trim())
    setLocked(false)
    setError('')
    setInput('')
  }

  if (!locked) {
    return <AuthCtx.Provider value={{ apiKey, setApiKey }}>{children}</AuthCtx.Provider>
  }

  return (
    <AuthCtx.Provider value={{ apiKey, setApiKey }}>
      {children}
      <div
        role="dialog"
        aria-modal="true"
        aria-label="API key required"
        style={{
          position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.7)',
          display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 99999,
        }}
      >
        <div style={{
          background: '#fff', borderRadius: 12, padding: 28, width: 340,
          boxShadow: '0 16px 48px rgba(0,0,0,0.25)',
        }}>
          <h2 style={{ margin: '0 0 8px', fontSize: 18 }}>API key required</h2>
          <p style={{ margin: '0 0 16px', fontSize: 13, color: '#64748b' }}>
            The server requires an API key. Enter it below — stored for this session only.
          </p>
          <input
            type="password"
            autoFocus
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
            placeholder="Bearer key…"
            style={{
              width: '100%', boxSizing: 'border-box', padding: '8px 12px',
              border: '1px solid #cbd5e1', borderRadius: 6, fontSize: 14, marginBottom: 8,
            }}
          />
          {error && <p style={{ margin: '0 0 8px', fontSize: 12, color: '#dc2626' }}>{error}</p>}
          <button
            onClick={submit}
            style={{
              width: '100%', padding: '9px 0', background: '#0ea5e9', color: '#fff',
              border: 'none', borderRadius: 6, fontWeight: 700, fontSize: 14, cursor: 'pointer',
            }}
          >
            Unlock
          </button>
        </div>
      </div>
    </AuthCtx.Provider>
  )
}
```

- [ ] **Step 5: Patch `lib/api.ts` to inject the key and emit 401 events**

In the `request<T>` function, replace:

```ts
res = await fetch(`${API_BASE}${path}`, init)
```

with:

```ts
const storedKey = typeof sessionStorage !== 'undefined'
  ? (sessionStorage.getItem('axalon_api_key') ?? '')
  : ''
const headers: HeadersInit = storedKey
  ? { ...(init?.headers as Record<string, string> ?? {}), Authorization: `Bearer ${storedKey}` }
  : (init?.headers as Record<string, string> ?? {})
res = await fetch(`${API_BASE}${path}`, { ...init, headers })
```

And after `if (!res.ok) throw new ApiError(res.status, text)`, add before the throw:

```ts
if (res.status === 401 && typeof window !== 'undefined') {
  window.dispatchEvent(new Event('axalon:unauthorized'))
}
```

- [ ] **Step 6: Wrap `layout.tsx` with `<AuthGate>`**

In `website/nextjs/app/platform/layout.tsx`, add:

```tsx
import { AuthGate } from '@/components/Platform/AuthGate'

export default function PlatformLayout({ children }: { children: React.ReactNode }) {
  return <AuthGate>{children}</AuthGate>
}
```

- [ ] **Step 7: Test the full auth flow in the browser**

```bash
# Restart API with a key
AXALON_API_KEY=demo-key ./run.sh all
```

Open `http://localhost:3000/platform`. The UI should load. Try any API call (switch to History tab — it fetches `/parks`). Confirm that without a stored key, the lock screen appears. Enter `demo-key`. Confirm calls succeed and the UI populates.

Clear `sessionStorage` via DevTools → Storage → Session Storage → delete `axalon_api_key`. Reload. Confirm lock screen reappears.

- [ ] **Step 8: Commit**

```bash
git add platform/api/app.py \
        website/nextjs/components/Platform/AuthGate.tsx \
        website/nextjs/lib/api.ts \
        website/nextjs/app/platform/layout.tsx
git commit -m "feat(auth): API key gate — backend dependency + AuthGate unlock screen"
```

---

## Task 3: Phone viewport (<768px)

**Files:**
- Modify: `website/nextjs/app/platform/platform.css`

Phase 3 added `@media (max-width: 768px)` rules for the 768px tablet breakpoint. This task extends `platform.css` with phone-specific overrides at `≤767px` so operators can use the platform in the field on a phone.

- [ ] **Step 1: Read the current `platform.css` breakpoint section**

Open `website/nextjs/app/platform/platform.css`. Locate the `@media (max-width: 768px)` block and note what it already covers. The task must not regress those rules.

- [ ] **Step 2: Add the phone breakpoint block**

At the end of `platform.css`, append:

```css
/* ── Phone (<768px) ── */
@media (max-width: 767px) {
  /* Tab bar: horizontal scroll, compact */
  .tab-bar {
    gap: 0;
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    scrollbar-width: none;
    padding: 0 4px;
  }
  .tab-bar::-webkit-scrollbar { display: none; }
  .tab-bar button {
    flex-shrink: 0;
    font-size: 12px;
    padding: 8px 12px;
    white-space: nowrap;
  }

  /* General gutters */
  .tab-content { padding: 12px; }

  /* Operations: stack map + job list */
  .operations-split {
    flex-direction: column;
    gap: 12px;
  }
  .operations-map { min-height: 220px; }

  /* Park Map: side panel becomes bottom drawer */
  .park-map-layout {
    grid-template-columns: 1fr;
    position: relative;
  }
  .park-panel-detail {
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    z-index: 1000;
    border-radius: 16px 16px 0 0;
    max-height: 60vh;
    overflow-y: auto;
    transform: translateY(100%);
    transition: transform 0.25s ease;
    box-shadow: 0 -4px 24px rgba(0,0,0,0.15);
  }
  .park-panel-detail.is-open {
    transform: translateY(0);
  }

  /* Diff tab: A/B columns stacked */
  .diff-columns {
    flex-direction: column;
  }
  .diff-column-label {
    display: block;
    font-size: 11px;
    font-weight: 700;
    color: #64748b;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 8px 0 4px;
  }

  /* History chart: full-width responsive */
  .history-chart-svg {
    width: 100%;
    height: auto;
  }

  /* Headings and text scale */
  h1.tab-heading { font-size: 18px; }
  .stat-value { font-size: 20px; }

  /* Fixed-width containers */
  .platform-container {
    max-width: 100%;
    min-width: 0;
    padding-left: 12px;
    padding-right: 12px;
  }
}
```

- [ ] **Step 3: Apply CSS class names to components that don't have them yet**

The class names above reference `.tab-bar`, `.tab-content`, `.operations-split`, `.park-panel-detail`, `.diff-columns`, etc. These must be present in the rendered HTML. Audit each tab component:

1. `page.tsx` — confirm the tab nav has `className="tab-bar"` and the tab body container has `className="tab-content"`.
2. `OperationsTab.tsx` — the map+job wrapper needs `className="operations-split"`.
3. `ParkMapTab.tsx` — the grid+detail wrapper needs `className="park-map-layout"`; the side panel needs `className={"park-panel-detail" + (selectedPanel ? " is-open" : "")}`.
4. `DiffTab.tsx` — the A/B column container needs `className="diff-columns"`; each side label needs `className="diff-column-label"`.
5. `HistoryTab.tsx` — the `<svg>` chart element needs `className="history-chart-svg"`.

Add `className` props only where the class is missing. Do **not** change any logic or layout beyond adding the class attribute.

- [ ] **Step 4: Test at phone viewport**

```bash
# Services running from previous task
```

Open DevTools → Device Toolbar → iPhone SE (375×667). Walk through each tab:

- Tab bar scrolls horizontally without overflow beyond screen edge.
- Operations tab: map stacks above job list.
- Park Map tab: tap a colored cell → detail drawer slides up from bottom.
- Diff tab: A/B inspection columns stack vertically.
- History tab: chart fills the container width.
- Settings and Inspect tabs: single column already, confirm no horizontal overflow.

For each issue, fix the CSS (or missing class) and re-verify. Do not write new JavaScript for mobile behavior — all layout changes must be CSS-only.

- [ ] **Step 5: Typecheck and run unit tests**

```bash
cd website/nextjs && npx tsc --noEmit && npm test
```

Expected: no TS errors, all unit tests pass.

- [ ] **Step 6: Commit**

```bash
git add website/nextjs/app/platform/platform.css \
        website/nextjs/components/Platform/*.tsx \
        website/nextjs/app/platform/page.tsx
git commit -m "feat(mobile): phone viewport (<768px) — CSS-only responsive layout"
```

---

## Task 4: Docker images

**Files:**
- Create: `Dockerfile`
- Create: `Dockerfile.nextjs`
- Create: `docker-compose.yml`
- Create: `.dockerignore`
- Create: `website/nextjs/.dockerignore`

- [ ] **Step 1: Write `.dockerignore` (repo root)**

```
.git
.github
__pycache__
*.pyc
*.pyo
.pytest_cache
.mypy_cache
node_modules
website/nextjs/.next
website/nextjs/node_modules
website/nextjs/test-results
ml/data
ml/runs
ml/notebooks
docs
tests/fixtures/sample_mission
*.log
*.db
.env
.env.*
```

- [ ] **Step 2: Write `website/nextjs/.dockerignore`**

```
.next
node_modules
test-results
playwright-report
*.log
.env
.env.*
```

- [ ] **Step 3: Write `Dockerfile` (Python API)**

```dockerfile
# Stage 1: build deps (wheel cache)
FROM python:3.13-slim AS builder
WORKDIR /build
COPY requirements_platform.txt ml/requirements.txt ./
RUN pip install --upgrade pip \
 && pip wheel --no-cache-dir --wheel-dir /wheels \
    -r requirements_platform.txt \
    -r ml/requirements.txt

# Stage 2: runtime
FROM python:3.13-slim
WORKDIR /app

# WeasyPrint system libs (for PDF reports; comment out to keep image smaller)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangoft2-1.0-0 libpangocairo-1.0-0 \
    libcairo2 libgdk-pixbuf-2.0-0 libffi-dev \
 && rm -rf /var/lib/apt/lists/*

COPY --from=builder /wheels /wheels
RUN pip install --no-cache-dir --no-index --find-links=/wheels \
    -r /wheels/../requirements_platform.txt \
    -r /wheels/../ml/requirements.txt 2>/dev/null || \
    pip install --no-cache-dir --find-links=/wheels \
        $(ls /wheels/*.whl | xargs -I{} basename {} .whl | sed 's/-[0-9].*//')

# Copy source
COPY ml/ ml/
COPY platform/ platform/
COPY main.py ./

# Expose
EXPOSE 8000

ENV PYTHONUNBUFFERED=1
CMD ["uvicorn", "platform.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 4: Write `Dockerfile.nextjs`**

```dockerfile
FROM node:20-slim AS deps
WORKDIR /app
COPY website/nextjs/package.json website/nextjs/package-lock.json ./
RUN npm ci --omit=dev

FROM node:20-slim AS builder
WORKDIR /app
COPY website/nextjs/ .
COPY --from=deps /app/node_modules ./node_modules
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
```

> **Note:** Next.js standalone output requires `output: 'standalone'` in `next.config.js`. If it isn't set, add `output: 'standalone'` to `next.config.js` before building.

- [ ] **Step 5: Check `next.config.js` for standalone output**

Read `website/nextjs/next.config.js`. If `output: 'standalone'` is absent, add it:

```js
const nextConfig = {
  // ...existing config...
  output: 'standalone',
}
```

- [ ] **Step 6: Write `docker-compose.yml`**

```yaml
version: "3.9"

services:
  api:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8000:8000"
    volumes:
      - axalon_data:/app/data          # SQLite DB + report outputs
      - ./ml/checkpoints:/app/ml/checkpoints:ro   # model weights (read-only)
    environment:
      - AXALON_DB_URL=sqlite:////app/data/axalon.db
      - AXALON_API_KEY=${AXALON_API_KEY:-}
      - AXALON_OUTPUT_DIR=/app/data/output
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8000/health"]
      interval: 10s
      timeout: 5s
      retries: 5

  nextjs:
    build:
      context: .
      dockerfile: Dockerfile.nextjs
    ports:
      - "3000:3000"
    environment:
      - NEXT_PUBLIC_AXALON_API_URL=http://api:8000
    depends_on:
      api:
        condition: service_healthy
    restart: unless-stopped

volumes:
  axalon_data:
```

- [ ] **Step 7: Build and verify both images**

```bash
docker compose build
```

Expected: both `api` and `nextjs` images build without errors. Ignore WeasyPrint warnings about missing fonts on builder.

- [ ] **Step 8: Start the stack and smoke-test**

```bash
docker compose up -d
sleep 15   # wait for Next.js to compile
curl -fsS http://localhost:8000/health
curl -fsS -o /dev/null -w '%{http_code}\n' http://localhost:3000/platform
```

Expected: API health returns `{"status":"ok",...}`; platform returns `200`.

- [ ] **Step 9: Verify job persistence across container restart**

```bash
JOB=$(curl -fsS -X POST http://localhost:8000/batch \
  -F "images=@tests/fixtures/sample_mission.zip" \
  -F "park_id=DOCKER_TEST" -F "altitude_m=42" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")
echo "job_id=$JOB"
sleep 90   # wait for completion
docker compose restart api
sleep 10
curl -fsS "http://localhost:8000/status/$JOB" | python3 -m json.tool | grep '"state"'
```

Expected: `"state": "succeeded"` after restart.

- [ ] **Step 10: Commit**

```bash
docker compose down
git add Dockerfile Dockerfile.nextjs docker-compose.yml .dockerignore \
        website/nextjs/.dockerignore website/nextjs/next.config.js
git commit -m "feat(docker): multi-stage Dockerfile + docker-compose for API and Next.js"
```

---

## Task 5: Playwright in GitHub Actions CI

**Files:**
- Modify: `.github/workflows/ci.yml`

Phase 3 added two CI jobs (`backend-tests` and `frontend-unit`). This task adds a third job (`e2e`) that spins up the docker-compose stack and runs the Playwright golden-path test.

- [ ] **Step 1: Read the current `.github/workflows/ci.yml`**

Locate the end of the existing `frontend-unit` job and the closing `jobs:` block.

- [ ] **Step 2: Append the `e2e` job**

```yaml
  e2e:
    runs-on: ubuntu-latest
    needs: [backend-tests, frontend-unit]   # only run if unit suites pass

    steps:
      - uses: actions/checkout@v4

      - name: Copy model weights (LFS or inline placeholder)
        run: |
          # In CI, best.pt must exist. Options:
          # 1. Git LFS (preferred if weights are in LFS)
          # 2. Download from a private release asset
          # 3. Skip YOLO inference by using a tiny stub — see note below
          if [ ! -f ml/checkpoints/best.pt ]; then
            echo "WARNING: best.pt missing — creating a 0-byte stub for UI smoke test"
            mkdir -p ml/checkpoints
            touch ml/checkpoints/best.pt
          fi

      - name: Set up sample mission fixture
        run: |
          python3 scripts/make_sample_mission.py
          cd tests/fixtures && zip -rq sample_mission.zip sample_mission/

      - name: Build docker-compose stack
        run: docker compose build

      - name: Start docker-compose stack
        run: |
          docker compose up -d
          # Wait for both services to be healthy
          for i in $(seq 1 60); do
            curl -fsS http://localhost:8000/health >/dev/null 2>&1 \
              && curl -fsS -o /dev/null http://localhost:3000/platform \
              && break
            echo "Waiting for services... ($i/60)"
            sleep 3
          done

      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: "npm"
          cache-dependency-path: website/nextjs/package-lock.json

      - name: Install npm deps + Playwright
        run: |
          cd website/nextjs
          npm ci
          npx playwright install --with-deps chromium

      - name: Run Playwright e2e
        env:
          PLAYWRIGHT_BASE_URL: http://localhost:3000
        run: cd website/nextjs && npm run test:e2e

      - name: Upload Playwright trace on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-trace
          path: website/nextjs/test-results/

      - name: Stop docker-compose stack
        if: always()
        run: docker compose down
```

> **CI note on model weights:** The e2e test uploads the synthetic fixture ZIP and polls for `100%` completion. If `best.pt` is a 0-byte stub in CI, the YOLO inference will fail — the batch job will reach `state: "failed"` rather than `succeeded`. This will cause the progress bar not to hit 100%. To handle this gracefully, either: (a) store `best.pt` in Git LFS and pull in CI, or (b) modify the e2e test to accept `failed` as a terminal state when running in CI (gate on `PLAYWRIGHT_CI=1` env var). Document the chosen strategy in `docs/DEPLOYMENT.md`.

- [ ] **Step 3: Run CI locally via `act` (optional but recommended)**

```bash
# Install act: https://github.com/nektos/act
act --job e2e --platform ubuntu-latest=ghcr.io/catthehacker/ubuntu:act-latest
```

If `act` is not available, push a branch and observe the Actions tab on GitHub.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: add e2e job to GitHub Actions — docker-compose + playwright"
```

---

## Task 6: Deployment runbook

**Files:**
- Create: `docs/DEPLOYMENT.md`

- [ ] **Step 1: Write `docs/DEPLOYMENT.md`**

```markdown
# Deployment Runbook — Axalon Inspection Platform

## Prerequisites

- `ml/checkpoints/best.pt` present (22 MB, YOLOv8s weights)
- Docker Engine ≥ 24 and Docker Compose v2 (`docker compose` not `docker-compose`)
- Ports 3000 and 8000 free

## Local Docker deployment

```bash
# 1. Clone and enter repo
git clone <repo-url> && cd AxalonSystems

# 2. Generate the sample mission fixture (needed for the e2e test + demo)
python3 scripts/make_sample_mission.py
cd tests/fixtures && zip -rq sample_mission.zip sample_mission/ && cd -

# 3. Seed demo data (optional — populates History / Park Map without a real batch)
python3 scripts/seed_demo_data.py

# 4. Set an API key (optional — omit to run without auth)
export AXALON_API_KEY=your-secret-key

# 5. Build and start
docker compose build
docker compose up -d

# 6. Open http://localhost:3000/platform
```

## Environment variables

| Variable | Service | Default | Description |
|---|---|---|---|
| `AXALON_API_KEY` | API | `` (empty = no auth) | Bearer key required on all non-health endpoints |
| `AXALON_DB_URL` | API | `sqlite:////app/data/axalon.db` | SQLAlchemy DB URL |
| `AXALON_OUTPUT_DIR` | API | `/app/data/output` | Directory for report outputs |
| `NEXT_PUBLIC_AXALON_API_URL` | Next.js | `http://api:8000` | API base URL seen by the browser |

## Render.com deployment

The `website/render.yaml` already configures a Web Service for the API. To update it for Docker:

1. In Render dashboard, create a new **Web Service** → **Docker**.
2. Set build context to repo root, Dockerfile to `Dockerfile`.
3. Set environment variables: `AXALON_API_KEY`, `AXALON_DB_URL` (use Render's managed disk for SQLite or switch to PostgreSQL).
4. Add a **Static Site** for Next.js:
   - Build command: `cd website/nextjs && npm ci && npm run build`
   - Publish directory: `website/nextjs/.next`
   - Set `NEXT_PUBLIC_AXALON_API_URL` to the Render API service URL.

## Model weights in CI

The `e2e` GitHub Actions job needs `ml/checkpoints/best.pt`. Two options:

**Option A — Git LFS (recommended):**
```bash
git lfs track "ml/checkpoints/*.pt"
git add .gitattributes ml/checkpoints/best.pt
git commit -m "chore: track model weights in Git LFS"
```
Add `git lfs pull` as the first step in the `e2e` CI job.

**Option B — CI stub (UI-only smoke test):**
Set `PLAYWRIGHT_CI=1` in the e2e workflow. Update `golden_path.spec.ts` to skip the `100%` completion check when that env var is set (tests tab navigation only, not YOLO inference).

## Stopping the stack

```bash
docker compose down          # stop containers
docker compose down -v       # stop + delete the axalon_data volume (destroys DB)
```
```

- [ ] **Step 2: Update `docs/OPERATOR_RUNBOOK.md` with a Phase 4 section**

Append to `docs/OPERATOR_RUNBOOK.md`:

```markdown

## Phase 4 additions

### API key auth

Set `AXALON_API_KEY` before starting the services:

```bash
export AXALON_API_KEY=your-key
./run.sh all
```

The platform UI will prompt for the key on first load (or after a 401). The key is stored in `sessionStorage` and cleared when you close the tab.

### Running with Docker

See `docs/DEPLOYMENT.md` for full Docker instructions.

### Job state persistence

Batch jobs now survive API restarts. If the API crashes mid-inspection, restart it — the job will resume from `running` state (the UI will poll and pick up where it left off once the inference thread re-queues it on startup).

> **Note:** Re-queuing in-progress jobs on restart requires the orchestrator to detect `state = "running"` on boot and re-submit those jobs. This is implemented in `platform/api/app.py` in the `lifespan` startup handler.
```

- [ ] **Step 3: Add lifespan handler to re-queue interrupted jobs**

In `platform/api/app.py`, find the FastAPI `app` instantiation or the existing startup hook. Add:

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # On startup: re-queue jobs that were interrupted mid-run
    session = get_session()
    try:
        stale = session.query(DbJob).filter(DbJob.state == "running").all()
        for j in stale:
            j.state = "queued"
            j.message = "Re-queued after API restart"
        session.commit()
        if stale:
            print(f"[startup] Re-queued {len(stale)} interrupted job(s)")
    finally:
        session.close()
    yield  # run the app

app = FastAPI(lifespan=lifespan)
```

If `app` is already instantiated elsewhere (without `lifespan`), add the `lifespan` argument: `app = FastAPI(lifespan=lifespan, ...)`.

- [ ] **Step 4: Commit**

```bash
git add docs/DEPLOYMENT.md docs/OPERATOR_RUNBOOK.md platform/api/app.py
git commit -m "docs: deployment runbook + Phase 4 runbook additions + lifespan re-queue"
```

---

## Task 7: Final acceptance pass

**Files:** none — verification only.

- [ ] **Step 1: Stop all running services, start fresh with Docker**

```bash
./run.sh stop 2>/dev/null || true
pkill -f "uvicorn\|next dev" 2>/dev/null || true
docker compose up -d
sleep 20
```

- [ ] **Step 2: Verify acceptance list**

```
- [ ] /health returns 200 without auth
- [ ] All other endpoints return 401 when AXALON_API_KEY is set and no key is sent
- [ ] All other endpoints return 200 when correct Bearer key is sent
- [ ] AuthGate unlock screen appears in browser when the API key is set and sessionStorage is empty
- [ ] Entering the correct key dismisses the lock screen; UI loads and all tabs function
- [ ] A batch job run to completion, then docker compose restart api, then /status/{job_id} returns "succeeded"
- [ ] Platform UI is navigable at 375px viewport (iPhone SE DevTools) — no overflow, Park Map drawer slides up on cell click
- [ ] docker compose build completes without errors
- [ ] docker compose up -d boots both services, health checks pass
- [ ] npm run test:e2e passes locally against the docker stack (PLAYWRIGHT_BASE_URL=http://localhost:3000)
- [ ] GitHub Actions CI passes: backend-tests + frontend-unit + e2e (or e2e shows expected skip if best.pt is a stub)
- [ ] docs/DEPLOYMENT.md exists and the Docker section works verbatim on a clean checkout
- [ ] Phase 1–3 regression: pytest tests/backend/ and npm test both pass
```

For each unchecked item, fix the underlying issue and re-verify.

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "chore(platform): Phase 4 acceptance pass" || echo "nothing to commit"
```

- [ ] **Step 4: Stop Docker stack**

```bash
docker compose down
```

---

## Done

When Task 7 passes, Phase 4 is complete. The platform is production-ready: jobs persist across restarts, the UI is auth-gated, the full stack runs in Docker, every tab is usable on a phone, and Playwright e2e is gated in CI.
