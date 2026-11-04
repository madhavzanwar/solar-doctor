# Plan 01 — Split `app.py` into FastAPI Routers
**Priority:** P0 | **Effort:** Large
**Goal:** Break `platform/api/app.py` (2,976 lines, 68 endpoints) into focused router modules.

---

## Why

A 3,000-line single file is impossible to navigate, review, or test in isolation. FastAPI's `APIRouter` makes splitting trivial — each router is mounted back into the main `app` with a prefix.

---

## Target Structure

```
platform/api/
├── app.py              ← thin shell: creates FastAPI app, mounts routers, lifespan
├── deps.py             ← shared dependencies: require_auth, get_session, get_orchestrator
├── routers/
│   ├── __init__.py
│   ├── inspection.py   ← POST /inspect, POST /batch, GET /status/{job_id}, GET /report/{job_id}
│   ├── results.py      ← GET /results/{job_id}/{filename}, GET /image/{job_id}/{filename}
│   ├── map.py          ← GET /map/{job_id}
│   ├── park.py         ← GET /park/{id}, GET /parks, GET /park/{id}/grid, /trend, /recurring, /grid/png, PATCH /park/{id}
│   ├── ortho.py        ← POST /park/{id}/ortho, GET /park/{id}/orthos, GET+DELETE /park/{id}/ortho/{name}, GET tiles
│   ├── diff.py         ← GET /parks/{id}/inspections/{a}/diff/{b}
│   ├── corrections.py  ← All /corrections/* endpoints
│   ├── missions.py     ← All /missions/* endpoints
│   ├── inventory.py    ← All /inventory/* endpoints
│   ├── projects.py     ← All /projects/* endpoints
│   ├── analytics.py    ← GET /analytics/overview
│   ├── track.py        ← POST /track/login, /track/password, /track/notes/*, /track/files/*
│   └── health.py       ← GET /health
```

---

## Steps

### Step 1 — Create `platform/api/deps.py`

Move these shared helpers out of app.py:

```python
# platform/api/deps.py
import os
from fastapi import Security, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from axalon.pipeline.orchestrator import InspectionOrchestrator

_bearer = HTTPBearer(auto_error=False)
_API_KEY: str = os.environ.get("AXALON_API_KEY", "")
_orchestrator: InspectionOrchestrator | None = None

def require_auth(creds: HTTPAuthorizationCredentials | None = Security(_bearer)) -> None:
    # copy exact body from app.py:92
    ...

def get_orchestrator() -> InspectionOrchestrator:
    # copy exact body from app.py:224
    ...
```

Also move private helpers used only within one domain into that router's file.

### Step 2 — Create `platform/api/routers/__init__.py`

Empty file.

### Step 3 — Create each router file

For each router, the pattern is:

```python
# platform/api/routers/inspection.py
from fastapi import APIRouter, BackgroundTasks, File, Form, UploadFile
from ..deps import require_auth, get_orchestrator

router = APIRouter(tags=["inspection"])

@router.post("/inspect")
async def inspect_pair(...):
    # verbatim body from app.py
    ...
```

**Domain → lines in app.py mapping:**

| Router | Approximate lines to move |
|--------|--------------------------|
| `inspection.py` | 361–666 (inspect + batch + helpers) |
| `results.py` | 749–835 (result images) |
| `map.py` | 836–965 (job map) |
| `park.py` | 1227–1560 (park summary, grid, trend, recurring) |
| `ortho.py` | 1064–1226 (ortho upload, list, tiles) |
| `diff.py` | 2904–2955 (diff inspections) |
| `inventory.py` | 2041–2424 (components, prototypes, assignments, orders, summary) |
| `projects.py` | 2459–2556 (projects CRUD) |
| `analytics.py` | 2590–2644 (overview) |
| `track.py` | 2645–2903 (login, notes, files) |
| `health.py` | 2956–2976 (health) |

### Step 4 — Rewrite `platform/api/app.py` as thin shell

```python
# platform/api/app.py  (target: ~80 lines)
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import (
    inspection, results, map as map_router, park, ortho,
    diff, inventory, projects, analytics, track, health
)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # run migrations, schedule cleanup — copy from app.py:142
    yield

app = FastAPI(title="Axalon Platform API", lifespan=lifespan)
app.add_middleware(CORSMiddleware, ...)

app.include_router(inspection.router)
app.include_router(results.router)
app.include_router(map_router.router)
app.include_router(park.router)
app.include_router(ortho.router)
app.include_router(diff.router)
app.include_router(inventory.router)
app.include_router(projects.router)
app.include_router(analytics.router)
app.include_router(track.router)
app.include_router(health.router)
```

### Step 5 — Move private helpers to the right place

Each private function (e.g. `_safe_filename`, `_validate_park_id`, `_serialize_project`) should live in the router file that uses it, or in `deps.py` if used by multiple routers.

### Step 6 — Verify no regressions

```bash
python3 -m pytest tests/backend/ -ra -v
uvicorn platform.api.app:app --host 0.0.0.0 --port 8000 &
curl http://localhost:8000/health
```

---

## Rules

- **Do not change any endpoint behavior** — only move code.
- Keep all `_private` helper functions in the same file as the endpoints that call them.
- Do NOT change import paths visible to `tests/backend/conftest.py`.
- Keep the existing auth middleware exactly as-is (app.py:197).

---

## Done When

- [ ] `app.py` is ≤ 100 lines
- [ ] Each router file is ≤ 400 lines
- [ ] `python3 -m pytest tests/backend/ -ra` passes unchanged
- [ ] `GET /health` returns 200
