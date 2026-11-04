# Platform Phase 5 — Gap Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close every planned gap left after Phase 4 — Alembic migrations, infrastructure fixes, corrections in reports, History trend charts and deterioration tracking, park mode selection, and full test coverage for AuthGate and the annotation editor.

**Architecture:** Alembic replaces raw `create_all()` for production schema management while tests keep using in-memory SQLite with `create_all()`. Two new pure-function modules (`platform/park/trend.py`, `platform/park/recurring.py`) power two new FastAPI endpoints. `TrendChart.tsx` is pure SVG — no new npm deps. The `/results/` endpoint URL mismatch is fixed with a one-line path change. Corrections are appended to the inspect-job JSON report and exposed via a new Download button in `InspectTab`. GPU support is one `deploy:` stanza in `docker-compose.yml`.

**Tech Stack:** Alembic 1.13+, FastAPI, SQLAlchemy 2.x, Next.js 14, TypeScript, Vitest, Playwright, pure SVG, Docker Compose GPU stanza.

**Deferred to Phase 6:** RGB+thermal fusion (`core/fusion.py`), orthomosaic upload UI.

---

## File Structure

| Path | Responsibility | Action |
|---|---|---|
| `alembic.ini` | Alembic CLI config pointing at `alembic/` scripts | Create |
| `alembic/env.py` | Alembic runtime: reads `AXALON_DB_URL`, imports `Base` | Create |
| `alembic/script.py.mako` | Standard Alembic migration template | Create |
| `alembic/versions/0001_initial_schema.py` | First migration — all tables up to and including Phase 4 | Create |
| `platform/park/trend.py` | Pure `build_trend(rows)` — normalises SQLAlchemy rows → trend JSON | Create |
| `platform/park/recurring.py` | Pure `build_recurring(rows)` — normalises recurring-fault rows | Create |
| `platform/api/app.py` | Add: `/park/{id}/trend`, `/park/{id}/recurring`, `/results/{id}/{file}` (fix URL), TTL cleanup in lifespan, GPU note comment, corrections included in `/report/` for inspect jobs | Modify |
| `platform/reporting/report.py` | Accept optional `corrections` list; include in JSON output | Modify |
| `docker-compose.yml` | Add GPU device reservation to `api` service | Modify |
| `website/nextjs/lib/api.ts` | Add `parkTrend()`, `parkRecurring()` methods + types | Modify |
| `website/nextjs/components/Platform/TrendChart.tsx` | Pure-SVG line chart — CRITICAL/HIGH/MEDIUM/LOW over time | Create |
| `website/nextjs/components/Platform/HistoryTab.tsx` | Render `<TrendChart>` + RecurringTable below existing park/inspection section | Modify |
| `website/nextjs/components/Platform/ParkPanelDetail.tsx` | Fix image URL: `/image/` → `/results/` | Modify |
| `website/nextjs/components/Platform/OperationsTab.tsx` | Add `park_mode` select (Auto / Numbered / Unnumbered) to batch form | Modify |
| `website/nextjs/components/Platform/InspectTab.tsx` | Add "Download Report" button after inspection result appears | Modify |
| `tests/backend/test_trend.py` | Unit tests for `build_trend` and `build_recurring` | Create |
| `tests/backend/test_trend_endpoint.py` | API contract tests for `/trend` and `/recurring` | Create |
| `website/nextjs/tests/unit/AuthGate.test.tsx` | Vitest coverage for lock screen, unlock flow, sessionStorage | Create |
| `website/nextjs/tests/e2e/annotation.spec.ts` | Playwright: draw correction, assign class, save, delete | Create |

---

## Task 1: Alembic migrations

**Files:**
- Create: `alembic.ini`
- Create: `alembic/env.py`
- Create: `alembic/script.py.mako`
- Create: `alembic/versions/0001_initial_schema.py`

- [ ] **Step 1: Install Alembic**

```bash
pip install "alembic>=1.13.1"
alembic --version   # expect: alembic 1.13.x
```

- [ ] **Step 2: Write `alembic.ini`**

```ini
[alembic]
script_location = alembic
prepend_sys_path = .
version_path_separator = os

[loggers]
keys = root,sqlalchemy,alembic

[handlers]
keys = console

[formatters]
keys = generic

[logger_root]
level = WARN
handlers = console
qualname =

[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine

[logger_alembic]
level = INFO
handlers =
qualname = alembic

[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic

[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
datefmt = %%H:%%M:%%S
```

- [ ] **Step 3: Write `alembic/env.py`**

```python
import os
from logging.config import fileConfig
from pathlib import Path
from sqlalchemy import engine_from_config, pool
from alembic import context

# Load alembic.ini logging config
config = context.config
if config.config_file_name:
    fileConfig(config.config_file_name)

# Import the metadata so Alembic can autogenerate migrations
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from axalon.db.models import Base
target_metadata = Base.metadata

# Read DB URL from env, fall back to alembic.ini value
_DB_URL = os.environ.get("AXALON_DB_URL", "sqlite:///axalon.db")


def run_migrations_offline() -> None:
    context.configure(
        url=_DB_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,  # required for SQLite ALTER TABLE support
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    cfg = config.get_section(config.config_ini_section, {})
    cfg["sqlalchemy.url"] = _DB_URL
    connectable = engine_from_config(cfg, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

- [ ] **Step 4: Write `alembic/script.py.mako`**

```mako
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}

"""
from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

- [ ] **Step 5: Generate the initial migration from the current model state**

Run from repo root:

```bash
alembic revision --autogenerate -m "initial_schema"
```

This creates `alembic/versions/<hash>_initial_schema.py`. Rename it for clarity:

```bash
mv alembic/versions/*_initial_schema.py alembic/versions/0001_initial_schema.py
```

Open the file and verify that `upgrade()` contains `op.create_table(...)` calls for every table: `parks`, `inspections`, `detections`, `panel_faults`, `corrections`, `jobs`. If any are missing, check that all models are imported in `alembic/env.py` via `Base.metadata`.

Edit the file header to fix the revision id (Alembic uses the hash; leave it — just verify the file looks correct).

- [ ] **Step 6: Test the migration on a fresh DB**

```bash
rm -f /tmp/alembic_test.db
AXALON_DB_URL="sqlite:////tmp/alembic_test.db" alembic upgrade head
sqlite3 /tmp/alembic_test.db ".tables"
```

Expected: output lists all tables including `jobs`, `corrections`, `alembic_version`.

- [ ] **Step 7: Test the migration on a pre-existing DB (upgrade path)**

```bash
# Create an old-style DB (no jobs/corrections table)
python3 -c "
import os; os.environ['AXALON_DB_URL'] = 'sqlite:////tmp/old_test.db'
from sqlalchemy import create_engine, text
e = create_engine('sqlite:////tmp/old_test.db')
e.execute = lambda *a, **k: None  # placeholder
from sqlalchemy.orm import declarative_base
B = declarative_base()
from sqlalchemy import Column, String, Integer, DateTime
import datetime
class Park(B):
    __tablename__ = 'parks'
    id = Column(String, primary_key=True)
B.metadata.create_all(e)
print('old DB created')
"
AXALON_DB_URL="sqlite:////tmp/old_test.db" alembic upgrade head
sqlite3 /tmp/old_test.db ".tables"
```

Expected: `jobs` and `corrections` tables now present; `parks` table unchanged.

- [ ] **Step 8: Wire Alembic into the API lifespan handler**

In `platform/api/app.py`, find the `lifespan` handler (added in Phase 4). Add migration call before the stale-job sweep:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Run DB migrations on startup
    _run_alembic_migrations()

    # Re-queue jobs interrupted mid-run
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
    yield
```

Add the helper near the top of `app.py`:

```python
def _run_alembic_migrations() -> None:
    """Run Alembic migrations programmatically. No-op on in-memory SQLite (used by tests)."""
    db_url = os.environ.get("AXALON_DB_URL", "sqlite:///axalon.db")
    if ":memory:" in db_url:
        return  # tests use create_all() directly
    try:
        from alembic.config import Config as _AlembicConfig
        from alembic import command as _alembic_cmd
        from pathlib import Path as _Path
        repo_root = _Path(__file__).resolve().parents[2]
        cfg = _AlembicConfig()
        cfg.set_main_option("script_location", str(repo_root / "alembic"))
        cfg.set_main_option("sqlalchemy.url", db_url)
        _alembic_cmd.upgrade(cfg, "head")
        print("[startup] Alembic migrations: up to date")
    except Exception as exc:
        print(f"[startup] Alembic migration warning: {exc}")
```

- [ ] **Step 9: Verify API starts cleanly**

```bash
AXALON_DB_URL="sqlite:////tmp/alembic_live.db" uvicorn platform.api.app:app --port 8001 &
sleep 3
curl -fsS http://localhost:8001/health
pkill -f "port 8001"
```

Expected: `[startup] Alembic migrations: up to date` in server log; health returns 200.

- [ ] **Step 10: Commit**

```bash
git add alembic.ini alembic/ platform/api/app.py
git commit -m "feat(db): Alembic migrations — production schema management"
```

---

## Task 2: Infrastructure quick fixes

**Files:**
- Modify: `platform/api/app.py` (add `/results/{job_id}/{filename}` endpoint + TTL cleanup)
- Modify: `website/nextjs/components/Platform/ParkPanelDetail.tsx` (fix `/image/` → `/results/`)
- Modify: `docker-compose.yml` (GPU device reservation)

### 2a — Fix `/results/` image serving endpoint

- [ ] **Step 1: Find the URL in `ParkPanelDetail.tsx`**

```bash
grep -n "API_BASE.*image\|/image/" website/nextjs/components/Platform/ParkPanelDetail.tsx
```

Expected: a line like `${API_BASE}/image/${encodeURIComponent(jobId)}/${encodeURIComponent(firstFile)}`.

- [ ] **Step 2: Check whether `/results/` endpoint exists in `app.py`**

```bash
grep -n '"/results/' platform/api/app.py
```

If no match, the endpoint is missing; add it in the next step.

- [ ] **Step 3: Add `GET /results/{job_id}/{filename}` endpoint to `app.py`**

Find a natural location (after the `/report/{job_id}` endpoint) and add:

```python
import mimetypes as _mimetypes

@app.get("/results/{job_id}/{filename}")
def serve_result_image(job_id: str, filename: str):
    """Serve an annotated image from a completed job's output directory."""
    job_id = _validate_job_id(job_id)
    if ".." in filename or filename.startswith("/"):
        raise HTTPException(status_code=400, detail="Invalid filename")
    output_dir = _os.environ.get("AXALON_OUTPUT_DIR", "output")
    image_path = _Path(output_dir) / job_id / filename
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    mime, _ = _mimetypes.guess_type(str(image_path))
    return FileResponse(str(image_path), media_type=mime or "image/jpeg")
```

(`_Path` and `FileResponse` may already be imported — check for duplicates and add only missing ones.)

- [ ] **Step 4: Update `ParkPanelDetail.tsx` to use `/results/`**

In `website/nextjs/components/Platform/ParkPanelDetail.tsx`, change:

```ts
// old
`${API_BASE}/image/${encodeURIComponent(jobId)}/${encodeURIComponent(firstFile)}`
// new
`${API_BASE}/results/${encodeURIComponent(jobId)}/${encodeURIComponent(firstFile)}`
```

- [ ] **Step 5: Smoke test**

Start the API with `AXALON_OUTPUT_DIR` pointing at the existing output directory, then navigate to Park Map, click a panel cell with a detection. The thumbnail in the detail panel should load (or 404 cleanly if there's no image — either is correct; no infinite spinner).

### 2b — Results TTL cleanup

- [ ] **Step 6: Add TTL cleanup to the lifespan handler**

In the `lifespan` handler in `app.py`, after the stale-job sweep and before `yield`:

```python
    # Delete output files for jobs older than results_ttl_hours
    _cleanup_old_results()
```

Add the helper:

```python
def _cleanup_old_results() -> None:
    import shutil as _shutil
    import datetime as _dt
    ttl_hours = int(_os.environ.get("AXALON_RESULTS_TTL_HOURS", "0"))
    if ttl_hours <= 0:
        return  # TTL disabled (default)
    cutoff = _dt.datetime.utcnow() - _dt.timedelta(hours=ttl_hours)
    session = get_session()
    try:
        old_jobs = session.query(DbJob).filter(
            DbJob.created_at < cutoff,
            DbJob.state.in_(["succeeded", "failed"]),
        ).all()
        output_dir = _os.environ.get("AXALON_OUTPUT_DIR", "output")
        for job in old_jobs:
            job_dir = _Path(output_dir) / job.id
            if job_dir.exists():
                _shutil.rmtree(job_dir, ignore_errors=True)
        if old_jobs:
            print(f"[startup] Cleaned up output for {len(old_jobs)} old job(s)")
    finally:
        session.close()
```

Set `AXALON_RESULTS_TTL_HOURS=0` in `docker-compose.yml` (disabled by default — operators enable it explicitly).

### 2c — GPU in Docker

- [ ] **Step 7: Add GPU device reservation to `docker-compose.yml`**

In the `api` service block, after `restart: unless-stopped`, add:

```yaml
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

This stanza is silently ignored on hosts without NVIDIA Container Toolkit, so it is safe on CPU-only machines.

Also update the `api` service's `environment:` block to pass through the CUDA device variable:

```yaml
    environment:
      - AXALON_DB_URL=sqlite:////app/data/axalon.db
      - AXALON_API_KEY=${AXALON_API_KEY:-}
      - AXALON_OUTPUT_DIR=/app/data/output
      - AXALON_RESULTS_TTL_HOURS=${AXALON_RESULTS_TTL_HOURS:-0}
      - CUDA_VISIBLE_DEVICES=${CUDA_VISIBLE_DEVICES:-0}
```

- [ ] **Step 8: Commit**

```bash
git add platform/api/app.py \
        website/nextjs/components/Platform/ParkPanelDetail.tsx \
        docker-compose.yml
git commit -m "fix: /results/ image endpoint, GPU Docker stanza, results TTL cleanup"
```

---

## Task 3: Corrections in inspect reports

**Files:**
- Modify: `platform/reporting/report.py`
- Modify: `platform/api/app.py`
- Modify: `website/nextjs/components/Platform/InspectTab.tsx`

When an operator draws corrections in the Inspect tab, those corrections are persisted to the DB under the inspect `job_id`. This task makes `GET /report/{job_id}?format=json` return those corrections, and adds a Download button to `InspectTab`.

- [ ] **Step 1: Write a failing test**

Create `tests/backend/test_corrections_in_report.py`:

```python
"""Corrections appear in the JSON report for an inspect job."""
import json
import pytest


@pytest.fixture
def engine():
    from axalon.db.session import init_db, get_engine
    init_db("sqlite:///:memory:")
    return get_engine()


@pytest.fixture
def client(engine):
    from axalon.api.app import app
    from fastapi.testclient import TestClient
    return TestClient(app)


def test_json_report_includes_corrections(client):
    # Simulate a completed inspect job in the DB
    from axalon.db.models import Correction
    from axalon.db.session import session_scope, get_engine
    job_id = "test-inspect-001"
    with session_scope(get_engine()) as s:
        s.add(Correction(
            job_id=job_id,
            class_="hot-spot-low",
            class_id=9,
            severity="HIGH",
            bbox_norm=json.dumps([0.1, 0.1, 0.4, 0.4]),
        ))

    r = client.get(f"/report/{job_id}?format=json")
    assert r.status_code == 200
    body = r.json()
    assert "corrections" in body
    assert len(body["corrections"]) == 1
    assert body["corrections"][0]["class"] == "hot-spot-low"
```

- [ ] **Step 2: Run to verify it fails**

```bash
python3 -m pytest tests/backend/test_corrections_in_report.py -v
```

Expected: FAIL — `"corrections"` key missing from report JSON.

- [ ] **Step 3: Update `platform/reporting/report.py` to accept corrections**

Find the function that generates the JSON report (likely `generate_json_report(detections, ...)` or similar). Add a `corrections` parameter:

```python
def generate_json_report(
    detections: list[dict],
    summary: dict,
    inspection_id: str,
    park_id: str | None = None,
    corrections: list[dict] | None = None,
) -> dict:
    return {
        "inspection_id": inspection_id,
        "park_id": park_id,
        "summary": summary,
        "detections": detections,
        "corrections": corrections or [],
    }
```

If the existing function signature is different, adapt accordingly — add `corrections` as a keyword-only argument with a default of `None`.

- [ ] **Step 4: Load corrections in the `/report/{job_id}` handler**

In `platform/api/app.py`, find the `GET /report/{job_id}` handler. After loading the job's detections (or reading the result JSON from disk), query corrections:

```python
# Inside the report handler, after loading `job_id`:
_corrections = []
try:
    _sess = get_session()
    _rows = _sess.query(Correction).filter(Correction.job_id == job_id).all()
    _corrections = [_serialize_correction(r) for r in _rows]
    _sess.close()
except Exception:
    pass  # corrections are best-effort; don't fail the report

# Then pass to the report generator:
report_data = generate_json_report(
    detections=detections,
    summary=summary,
    inspection_id=job_id,
    park_id=park_id,
    corrections=_corrections,
)
```

The exact location depends on how the existing handler is structured — add the correction query just before the report is assembled, for both batch and inspect job_ids.

- [ ] **Step 5: Run test to verify it passes**

```bash
python3 -m pytest tests/backend/test_corrections_in_report.py -v
```

Expected: PASS.

- [ ] **Step 6: Add Download Report button to `InspectTab.tsx`**

In `website/nextjs/components/Platform/InspectTab.tsx`, find where `inspectResult` is rendered (the section that shows detection list and annotated image). Add a download button immediately after the detection list:

```tsx
{inspectResult && (
  <a
    href={api.reportUrl(inspectResult.job_id, 'json')}
    download={`inspect_${inspectResult.job_id}.json`}
    style={{
      display: 'inline-block',
      marginTop: 12,
      padding: '8px 14px',
      background: '#0ea5e9',
      color: '#fff',
      borderRadius: 6,
      fontSize: 13,
      fontWeight: 600,
      textDecoration: 'none',
    }}
  >
    Download Report (JSON)
  </a>
)}
```

(`api.reportUrl` is already defined in `lib/api.ts` from Phase 1.)

- [ ] **Step 7: Manually verify**

Start the stack. Go to the Inspect tab. Upload an image, submit. Draw a correction box, assign a class, save. Click "Download Report (JSON)". Open the downloaded file — confirm `"corrections"` array contains your drawn box.

- [ ] **Step 8: Commit**

```bash
git add platform/reporting/report.py platform/api/app.py \
        website/nextjs/components/Platform/InspectTab.tsx \
        tests/backend/test_corrections_in_report.py
git commit -m "feat(reports): include operator corrections in inspect-job JSON report"
```

---

## Task 4: History trend charts

**Files:**
- Create: `platform/park/trend.py`
- Create: `tests/backend/test_trend.py`
- Modify: `platform/api/app.py`
- Create: `website/nextjs/components/Platform/TrendChart.tsx`
- Modify: `website/nextjs/lib/api.ts`
- Modify: `website/nextjs/components/Platform/HistoryTab.tsx`

### 4a — Backend pure function + endpoint

- [ ] **Step 1: Write failing tests**

Create `tests/backend/test_trend.py`:

```python
"""Unit tests for build_trend and build_recurring."""
from types import SimpleNamespace
from platform.park.trend import build_trend


def _row(id_, date, critical, high, medium, low):
    return SimpleNamespace(
        id=id_, flight_date=date,
        critical_count=critical, high_count=high,
        medium_count=medium, low_count=low,
    )


def test_build_trend_returns_sorted_list():
    rows = [
        _row("b2", "2026-05-07", 2, 4, 10, 6),
        _row("b1", "2026-04-22", 3, 5, 12, 4),
        _row("b3", "2026-05-22", 5, 8, 15, 3),
    ]
    result = build_trend(rows)
    assert [r["inspection_id"] for r in result] == ["b1", "b2", "b3"]


def test_build_trend_maps_severity_counts():
    rows = [_row("b1", "2026-04-22", 1, 2, 3, 4)]
    result = build_trend(rows)
    assert result[0] == {
        "inspection_id": "b1",
        "date": "2026-04-22",
        "CRITICAL": 1,
        "HIGH": 2,
        "MEDIUM": 3,
        "LOW": 4,
    }


def test_build_trend_handles_null_counts():
    rows = [_row("b1", "2026-04-22", None, None, None, None)]
    result = build_trend(rows)
    assert result[0]["CRITICAL"] == 0
    assert result[0]["HIGH"] == 0


def test_build_trend_empty_input():
    assert build_trend([]) == []
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd /tmp && PYTHONSAFEPATH=1 python -m pytest /home/parakh/Desktop/AxalonSystems/tests/backend/test_trend.py -v
```

Expected: FAIL — `No module named 'platform.park.trend'`.

- [ ] **Step 3: Create `platform/park/trend.py`**

```python
"""Trend aggregator — normalises per-inspection severity counts for history charts.

Pure function, no DB dependency. Receives SQLAlchemy Row objects (or SimpleNamespaces
with the same attributes) and returns a sorted list of dicts.
"""
from __future__ import annotations
from typing import Any


def build_trend(rows: list[Any]) -> list[dict]:
    """Convert a list of Row(id, flight_date, critical_count, high_count, medium_count, low_count)
    into a JSON-serialisable list sorted by date ascending.
    """
    result = []
    for row in rows:
        result.append({
            "inspection_id": row.id,
            "date": str(row.flight_date) if row.flight_date else None,
            "CRITICAL": int(row.critical_count or 0),
            "HIGH": int(row.high_count or 0),
            "MEDIUM": int(row.medium_count or 0),
            "LOW": int(row.low_count or 0),
        })
    return sorted(result, key=lambda x: x["date"] or "")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /tmp && PYTHONSAFEPATH=1 python -m pytest /home/parakh/Desktop/AxalonSystems/tests/backend/test_trend.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Add `GET /park/{park_id}/trend` endpoint to `app.py`**

Find the block where `/park/{park_id}/grid` is defined and add immediately after it:

```python
@app.get("/park/{park_id}/trend")
def get_park_trend(park_id: str):
    """Per-inspection severity count trend for a park, sorted oldest-first."""
    from platform.park.trend import build_trend as _build_trend
    from sqlalchemy import text as _text

    engine = _get_engine()
    with _session_scope(engine) as s:
        park = s.query(Park).filter(Park.id == park_id).first()
        if park is None:
            raise HTTPException(status_code=404, detail=f"Park {park_id!r} not found")

        rows = s.execute(
            _text("""
                SELECT i.id,
                       i.flight_date,
                       SUM(CASE WHEN d.severity = 'CRITICAL' THEN 1 ELSE 0 END) AS critical_count,
                       SUM(CASE WHEN d.severity = 'HIGH'     THEN 1 ELSE 0 END) AS high_count,
                       SUM(CASE WHEN d.severity = 'MEDIUM'   THEN 1 ELSE 0 END) AS medium_count,
                       SUM(CASE WHEN d.severity = 'LOW'      THEN 1 ELSE 0 END) AS low_count
                FROM inspections i
                LEFT JOIN detections d ON d.inspection_id = i.id
                WHERE i.park_id = :park_id
                GROUP BY i.id
                ORDER BY i.flight_date ASC
            """),
            {"park_id": park_id},
        ).fetchall()

    return _build_trend(rows)
```

- [ ] **Step 6: Smoke-test the endpoint**

```bash
curl -fsS "http://localhost:8000/park/SOLAR_PARK_DEMO/trend" | python3 -m json.tool
```

Expected: JSON array with one object per inspection, each having `CRITICAL`, `HIGH`, `MEDIUM`, `LOW` integer keys.

- [ ] **Step 7: Commit backend**

```bash
git add platform/park/trend.py tests/backend/test_trend.py platform/api/app.py
git commit -m "feat(history): build_trend + GET /park/{id}/trend endpoint"
```

### 4b — Frontend: API method + TrendChart + HistoryTab wiring

- [ ] **Step 8: Add `parkTrend` to `lib/api.ts`**

After the existing `ParkGrid` type block, add:

```ts
export type TrendPoint = {
  inspection_id: string
  date: string | null
  CRITICAL: number
  HIGH: number
  MEDIUM: number
  LOW: number
}

// Inside the `export const api = { ... }` object:
  parkTrend: (parkId: string) =>
    request<TrendPoint[]>(`/park/${encodeURIComponent(parkId)}/trend`),
```

- [ ] **Step 9: Create `TrendChart.tsx`**

```tsx
'use client'

import type { TrendPoint } from '@/lib/api'

const COLORS = {
  CRITICAL: '#dc2626',
  HIGH: '#ea580c',
  MEDIUM: '#ca8a04',
  LOW: '#2563eb',
} as const

const MARGINS = { top: 16, right: 24, bottom: 36, left: 44 }
const VIEW_W = 720
const VIEW_H = 220
const CHART_W = VIEW_W - MARGINS.left - MARGINS.right
const CHART_H = VIEW_H - MARGINS.top - MARGINS.bottom

export function TrendChart({ data }: { data: TrendPoint[] }) {
  if (data.length < 2) {
    return (
      <div style={{ padding: 24, color: '#64748b', fontSize: 13, textAlign: 'center' }}>
        Need at least 2 inspections to show a trend.
      </div>
    )
  }

  const severities = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'] as const
  const maxCount = Math.max(
    1,
    ...data.flatMap((d) => severities.map((s) => d[s])),
  )
  const yStep = niceStep(maxCount)
  const yMax = Math.ceil(maxCount / yStep) * yStep
  const yTicks = Array.from({ length: Math.ceil(yMax / yStep) + 1 }, (_, i) => i * yStep)

  function xPos(i: number) {
    return MARGINS.left + (i / (data.length - 1)) * CHART_W
  }
  function yPos(count: number) {
    return MARGINS.top + CHART_H - (count / yMax) * CHART_H
  }

  return (
    <svg
      viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
      preserveAspectRatio="xMinYMid meet"
      className="history-chart-svg"
      style={{ width: '100%', height: 'auto', display: 'block' }}
      role="img"
      aria-label="Anomaly trend over time"
    >
      {/* Grid lines */}
      {yTicks.map((tick) => (
        <g key={tick}>
          <line
            x1={MARGINS.left} y1={yPos(tick)}
            x2={MARGINS.left + CHART_W} y2={yPos(tick)}
            stroke="#e2e8f0" strokeWidth={1}
          />
          <text
            x={MARGINS.left - 6} y={yPos(tick) + 4}
            textAnchor="end" fontSize={10} fill="#94a3b8"
          >
            {tick}
          </text>
        </g>
      ))}

      {/* X-axis date labels */}
      {data.map((d, i) => (
        <text
          key={i}
          x={xPos(i)} y={MARGINS.top + CHART_H + 20}
          textAnchor="middle" fontSize={10} fill="#64748b"
        >
          {d.date ? d.date.slice(5) : '?'}  {/* MM-DD */}
        </text>
      ))}

      {/* Lines per severity */}
      {severities.map((sev) => {
        const points = data
          .map((d, i) => `${xPos(i)},${yPos(d[sev])}`)
          .join(' ')
        return (
          <polyline
            key={sev}
            points={points}
            fill="none"
            stroke={COLORS[sev]}
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        )
      })}

      {/* Data points */}
      {severities.map((sev) =>
        data.map((d, i) => (
          <circle
            key={`${sev}-${i}`}
            cx={xPos(i)} cy={yPos(d[sev])}
            r={3}
            fill={COLORS[sev]}
          >
            <title>{`${sev}: ${d[sev]} (${d.date ?? '?'})`}</title>
          </circle>
        )),
      )}

      {/* Legend */}
      {severities.map((sev, i) => (
        <g key={sev} transform={`translate(${MARGINS.left + i * 120}, ${VIEW_H - 6})`}>
          <rect x={0} y={-8} width={12} height={4} fill={COLORS[sev]} rx={1} />
          <text x={16} y={0} fontSize={10} fill="#64748b">{sev}</text>
        </g>
      ))}
    </svg>
  )
}

function niceStep(max: number): number {
  if (max <= 5) return 1
  if (max <= 20) return 5
  if (max <= 50) return 10
  return Math.ceil(max / 5 / 10) * 10
}
```

- [ ] **Step 10: Render TrendChart in `HistoryTab.tsx`**

In `website/nextjs/components/Platform/HistoryTab.tsx`, find where `historyParkId` is set and inspections are listed. Add state and effect for trend data:

```tsx
import { TrendChart } from '@/components/Platform/TrendChart'
import type { TrendPoint } from '@/lib/api'

// Inside HistoryTab function body, with the other useState calls:
const [trendData, setTrendData] = useState<TrendPoint[]>([])
const [trendLoading, setTrendLoading] = useState(false)
```

Add a `useEffect` that fetches trend data whenever `historyParkId` changes (alongside the existing park-summary effect):

```tsx
useEffect(() => {
  if (!historyParkId) { setTrendData([]); return }
  let cancelled = false
  setTrendLoading(true)
  api.parkTrend(historyParkId)
    .then((d) => { if (!cancelled) setTrendData(d) })
    .catch((err) => {
      if (!cancelled) toast.error(err instanceof ApiError ? err.message : String(err))
    })
    .finally(() => { if (!cancelled) setTrendLoading(false) })
  return () => { cancelled = true }
}, [historyParkId, toast])
```

Add the chart below the existing inspection list in the returned JSX:

```tsx
<section style={{ marginTop: 24 }}>
  <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>Anomaly Trend</h2>
  {trendLoading
    ? <div style={{ height: 180, background: '#f1f5f9', borderRadius: 8, animation: 'pulse 1.5s infinite' }} />
    : <TrendChart data={trendData} />}
</section>
```

- [ ] **Step 11: Typecheck**

```bash
cd website/nextjs && npx tsc --noEmit 2>&1 | grep -E "(TrendChart|HistoryTab|api\.ts)"
```

Expected: empty (no errors in these files).

- [ ] **Step 12: Manually verify**

Open the History tab, select `SOLAR_PARK_DEMO`. Confirm the trend chart renders 3 lines across 3 inspections (seeded in Phase 3). Resize to mobile width — chart should scale without overflow.

- [ ] **Step 13: Commit frontend**

```bash
git add website/nextjs/lib/api.ts \
        website/nextjs/components/Platform/TrendChart.tsx \
        website/nextjs/components/Platform/HistoryTab.tsx
git commit -m "feat(history): anomaly trend chart (pure SVG, no deps)"
```

---

## Task 5: Deterioration tracking

**Files:**
- Create: `platform/park/recurring.py`
- Test: `tests/backend/test_trend.py` (append)
- Modify: `platform/api/app.py`
- Modify: `website/nextjs/lib/api.ts`
- Modify: `website/nextjs/components/Platform/HistoryTab.tsx`

### 5a — Backend

- [ ] **Step 1: Write failing tests**

Append to `tests/backend/test_trend.py`:

```python
from platform.park.recurring import build_recurring


def _rec_row(panel_id, inspection_count, sev_rank, classes, first_seen, last_seen):
    return SimpleNamespace(
        panel_id=panel_id,
        inspection_count=inspection_count,
        sev_rank=sev_rank,
        classes=classes,
        first_seen=first_seen,
        last_seen=last_seen,
    )


def test_build_recurring_maps_fields():
    rows = [_rec_row("R2-C3", 3, 4, "hot-spot-low,hot-spot-high", "2026-04-22", "2026-05-22")]
    result = build_recurring(rows)
    assert result[0] == {
        "panel_id": "R2-C3",
        "inspection_count": 3,
        "worst_severity": "CRITICAL",
        "classes": ["hot-spot-low", "hot-spot-high"],
        "first_seen": "2026-04-22",
        "last_seen": "2026-05-22",
    }


def test_build_recurring_dedupes_classes():
    rows = [_rec_row("R1-C1", 2, 2, "soiling,soiling", "2026-04-22", "2026-05-07")]
    result = build_recurring(rows)
    assert result[0]["classes"] == ["soiling"]


def test_build_recurring_empty_input():
    assert build_recurring([]) == []


def test_build_recurring_severity_rank_mapping():
    rows = [_rec_row("R1-C1", 2, 3, "hot-spot-low", "2026-04-22", "2026-05-07")]
    assert build_recurring(rows)[0]["worst_severity"] == "HIGH"
```

- [ ] **Step 2: Run to confirm failures**

```bash
cd /tmp && PYTHONSAFEPATH=1 python -m pytest /home/parakh/Desktop/AxalonSystems/tests/backend/test_trend.py::test_build_recurring_maps_fields -v
```

Expected: FAIL — `No module named 'platform.park.recurring'`.

- [ ] **Step 3: Create `platform/park/recurring.py`**

```python
"""Recurring-fault aggregator — panels that appear in 2+ inspections.

Pure function. Receives SQLAlchemy Row objects (or SimpleNamespaces).
"""
from __future__ import annotations
from typing import Any

_RANK_TO_SEVERITY = {4: "CRITICAL", 3: "HIGH", 2: "MEDIUM", 1: "LOW"}


def build_recurring(rows: list[Any]) -> list[dict]:
    """Normalise recurring-fault rows into JSON-serialisable dicts.

    Each row must have: panel_id, inspection_count, sev_rank (int 1-4),
    classes (comma-separated string), first_seen, last_seen.
    """
    result = []
    for row in rows:
        raw_classes = (row.classes or "").split(",")
        unique_classes = list(dict.fromkeys(c.strip() for c in raw_classes if c.strip()))
        result.append({
            "panel_id": row.panel_id,
            "inspection_count": int(row.inspection_count or 0),
            "worst_severity": _RANK_TO_SEVERITY.get(int(row.sev_rank or 1), "LOW"),
            "classes": unique_classes,
            "first_seen": str(row.first_seen) if row.first_seen else None,
            "last_seen": str(row.last_seen) if row.last_seen else None,
        })
    return result
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /tmp && PYTHONSAFEPATH=1 python -m pytest /home/parakh/Desktop/AxalonSystems/tests/backend/test_trend.py -v
```

Expected: all pass (the 4 build_trend tests from Task 4 + 4 new build_recurring tests).

- [ ] **Step 5: Add `GET /park/{park_id}/recurring` endpoint to `app.py`**

Immediately after the `/park/{park_id}/trend` endpoint:

```python
@app.get("/park/{park_id}/recurring")
def get_park_recurring(park_id: str, min_inspections: int = 2):
    """Panels with anomalies in ≥ min_inspections inspections for a park."""
    from platform.park.recurring import build_recurring as _build_recurring
    from sqlalchemy import text as _text

    engine = _get_engine()
    with _session_scope(engine) as s:
        park = s.query(Park).filter(Park.id == park_id).first()
        if park is None:
            raise HTTPException(status_code=404, detail=f"Park {park_id!r} not found")

        rows = s.execute(
            _text("""
                SELECT d.panel_id,
                       COUNT(DISTINCT d.inspection_id) AS inspection_count,
                       MAX(CASE d.severity
                           WHEN 'CRITICAL' THEN 4
                           WHEN 'HIGH'     THEN 3
                           WHEN 'MEDIUM'   THEN 2
                           ELSE 1 END) AS sev_rank,
                       GROUP_CONCAT(DISTINCT d.class) AS classes,
                       MIN(i.flight_date) AS first_seen,
                       MAX(i.flight_date) AS last_seen
                FROM detections d
                JOIN inspections i ON i.id = d.inspection_id
                WHERE i.park_id = :park_id
                  AND d.panel_id IS NOT NULL
                GROUP BY d.panel_id
                HAVING inspection_count >= :min_inspections
                ORDER BY sev_rank DESC, inspection_count DESC
            """),
            {"park_id": park_id, "min_inspections": min_inspections},
        ).fetchall()

    return _build_recurring(rows)
```

- [ ] **Step 6: Commit backend**

```bash
git add platform/park/recurring.py platform/api/app.py tests/backend/test_trend.py
git commit -m "feat(history): build_recurring + GET /park/{id}/recurring endpoint"
```

### 5b — Frontend

- [ ] **Step 7: Add `parkRecurring` to `lib/api.ts`**

After the `TrendPoint` type, add:

```ts
export type RecurringPanel = {
  panel_id: string
  inspection_count: number
  worst_severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
  classes: string[]
  first_seen: string | null
  last_seen: string | null
}

// Inside the `api` object:
  parkRecurring: (parkId: string, minInspections = 2) =>
    request<RecurringPanel[]>(
      `/park/${encodeURIComponent(parkId)}/recurring?min_inspections=${minInspections}`
    ),
```

- [ ] **Step 8: Add RecurringTable to `HistoryTab.tsx`**

Add state and fetch alongside the trend fetch (same `historyParkId` dependency):

```tsx
import type { RecurringPanel } from '@/lib/api'

// State:
const [recurringData, setRecurringData] = useState<RecurringPanel[]>([])

// Effect (add after the trendData effect):
useEffect(() => {
  if (!historyParkId) { setRecurringData([]); return }
  let cancelled = false
  api.parkRecurring(historyParkId)
    .then((d) => { if (!cancelled) setRecurringData(d) })
    .catch(() => {}) // non-critical; silent on error
  return () => { cancelled = true }
}, [historyParkId])
```

Add the table below the TrendChart section:

```tsx
{recurringData.length > 0 && (
  <section style={{ marginTop: 24 }}>
    <h2 style={{ fontSize: 16, fontWeight: 700, marginBottom: 8 }}>Recurring Faults</h2>
    <p style={{ fontSize: 12, color: '#64748b', marginBottom: 10 }}>
      Panels with anomalies in 2 or more inspections — highest priority for maintenance.
    </p>
    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
      <thead>
        <tr style={{ background: '#f8fafc', borderBottom: '2px solid #e2e8f0' }}>
          {['Panel', 'Inspections', 'Fault Types', 'First Seen', 'Last Seen', 'Severity'].map((h) => (
            <th key={h} style={{ padding: '8px 12px', textAlign: 'left', color: '#64748b', fontWeight: 600 }}>{h}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {recurringData.map((row) => (
          <tr key={row.panel_id} style={{ borderBottom: '1px solid #f1f5f9' }}>
            <td style={{ padding: '8px 12px', fontWeight: 600 }}>{row.panel_id}</td>
            <td style={{ padding: '8px 12px' }}>{row.inspection_count}</td>
            <td style={{ padding: '8px 12px', color: '#475569' }}>{row.classes.join(', ')}</td>
            <td style={{ padding: '8px 12px', color: '#64748b' }}>{row.first_seen ?? '—'}</td>
            <td style={{ padding: '8px 12px', color: '#64748b' }}>{row.last_seen ?? '—'}</td>
            <td style={{ padding: '8px 12px' }}>
              <span style={{
                padding: '2px 8px',
                borderRadius: 4,
                fontSize: 11,
                fontWeight: 700,
                color: '#fff',
                background: { CRITICAL: '#dc2626', HIGH: '#ea580c', MEDIUM: '#ca8a04', LOW: '#2563eb' }[row.worst_severity],
              }}>
                {row.worst_severity}
              </span>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  </section>
)}
```

- [ ] **Step 9: Typecheck**

```bash
cd website/nextjs && npx tsc --noEmit 2>&1 | grep -E "(HistoryTab|RecurringPanel|api\.ts)"
```

Expected: empty.

- [ ] **Step 10: Commit frontend**

```bash
git add website/nextjs/lib/api.ts \
        website/nextjs/components/Platform/HistoryTab.tsx
git commit -m "feat(history): recurring faults table in History tab"
```

---

## Task 6: Park mode UI

**Files:**
- Modify: `website/nextjs/components/Platform/OperationsTab.tsx`

The `/batch` endpoint accepts `park_mode: "auto" | "numbered" | "unnumbered"` but the UI never sends it, always defaulting to `"auto"`. This task adds a select to `OperationsTab`.

- [ ] **Step 1: Add `parkMode` state and select to `OperationsTab.tsx`**

In `website/nextjs/components/Platform/OperationsTab.tsx`, find the existing form state declarations (near `parkId`, `altitude` state). Add:

```tsx
const [parkMode, setParkMode] = useState<'auto' | 'numbered' | 'unnumbered'>('auto')
```

In the JSX, find the form row containing the Park ID input and Altitude input. Add a third field in the same row:

```tsx
<label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: '#64748b' }}>
  Park Mode
  <select
    value={parkMode}
    onChange={(e) => setParkMode(e.target.value as 'auto' | 'numbered' | 'unnumbered')}
    title="Auto: detect from images. Numbered: OCR panel IDs from RGB. Unnumbered: synthetic R-C grid."
    style={{ padding: '6px 10px', border: '1px solid #cbd5e1', borderRadius: 6 }}
  >
    <option value="auto">Auto-detect</option>
    <option value="numbered">Numbered (OCR)</option>
    <option value="unnumbered">Unnumbered (Grid)</option>
  </select>
</label>
```

- [ ] **Step 2: Include `park_mode` in the batch FormData**

Find where the `FormData` is constructed before `api.batch(form)` is called. Add:

```tsx
form.append('park_mode', parkMode)
```

- [ ] **Step 3: Verify in the browser**

Open Operations tab. Confirm the Park Mode dropdown appears. Select "Numbered (OCR)". Start a batch. In the Network tab, confirm the `park_mode=numbered` field is present in the request payload.

- [ ] **Step 4: Commit**

```bash
git add website/nextjs/components/Platform/OperationsTab.tsx
git commit -m "feat(operations): park mode selector (auto/numbered/unnumbered)"
```

---

## Task 7: AuthGate unit tests

**Files:**
- Create: `website/nextjs/tests/unit/AuthGate.test.tsx`

- [ ] **Step 1: Write the test file**

```tsx
import '@testing-library/jest-dom/vitest'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { AuthGate } from '@/components/Platform/AuthGate'

const STORAGE_KEY = 'axalon_api_key'

afterEach(() => {
  sessionStorage.clear()
  vi.restoreAllMocks()
})

describe('AuthGate', () => {
  test('renders children and no dialog by default', () => {
    render(<AuthGate><div>content</div></AuthGate>)
    expect(screen.getByText('content')).toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  test('shows lock screen when axalon:unauthorized event fires', () => {
    render(<AuthGate><div>content</div></AuthGate>)
    act(() => { window.dispatchEvent(new Event('axalon:unauthorized')) })
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByPlaceholderText(/Bearer key/i)).toBeInTheDocument()
  })

  test('children remain visible behind the lock overlay', () => {
    render(<AuthGate><div>content</div></AuthGate>)
    act(() => { window.dispatchEvent(new Event('axalon:unauthorized')) })
    expect(screen.getByText('content')).toBeInTheDocument()
  })

  test('Unlock dismisses dialog and stores key in sessionStorage', () => {
    render(<AuthGate><div>content</div></AuthGate>)
    act(() => { window.dispatchEvent(new Event('axalon:unauthorized')) })
    fireEvent.change(screen.getByPlaceholderText(/Bearer key/i), {
      target: { value: 'secret123' },
    })
    fireEvent.click(screen.getByRole('button', { name: /Unlock/i }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    expect(sessionStorage.getItem(STORAGE_KEY)).toBe('secret123')
  })

  test('shows error and keeps dialog open when submitting empty key', () => {
    render(<AuthGate><div>content</div></AuthGate>)
    act(() => { window.dispatchEvent(new Event('axalon:unauthorized')) })
    fireEvent.click(screen.getByRole('button', { name: /Unlock/i }))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText(/Enter a key/i)).toBeInTheDocument()
  })

  test('Enter key submits the form', () => {
    render(<AuthGate><div>content</div></AuthGate>)
    act(() => { window.dispatchEvent(new Event('axalon:unauthorized')) })
    const input = screen.getByPlaceholderText(/Bearer key/i)
    fireEvent.change(input, { target: { value: 'mykey' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(sessionStorage.getItem(STORAGE_KEY)).toBe('mykey')
  })

  test('reads pre-stored key and does not show lock on mount', () => {
    sessionStorage.setItem(STORAGE_KEY, 'pre-stored')
    render(<AuthGate><div>content</div></AuthGate>)
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run to confirm all pass**

```bash
cd website/nextjs && npm test -- tests/unit/AuthGate.test.tsx
```

Expected: 7 passed.

If any test fails because `AuthGate` doesn't exist yet (Phase 4 not yet executed in this environment), that's acceptable — note it as a dependency on Phase 4 execution.

- [ ] **Step 3: Run full vitest suite to confirm no regressions**

```bash
cd website/nextjs && npm test
```

Expected: all existing tests pass + 7 new AuthGate tests.

- [ ] **Step 4: Commit**

```bash
git add website/nextjs/tests/unit/AuthGate.test.tsx
git commit -m "test(auth): vitest coverage for AuthGate lock/unlock flow"
```

---

## Task 8: Annotation editor e2e test

**Files:**
- Create: `website/nextjs/tests/e2e/annotation.spec.ts`

- [ ] **Step 1: Write the Playwright test**

```ts
import { expect, test } from '@playwright/test'
import path from 'node:path'

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..', '..')
const THERMAL_IMG = path.join(
  REPO_ROOT, 'tests', 'fixtures', 'sample_mission', 'thermal', 'img_001.jpg'
)

test.describe('Annotation editor', () => {
  test('draw a correction box, assign class, save, then delete', async ({ page }) => {
    await page.goto('/platform')

    // Navigate to Inspect tab
    await page.getByRole('button', { name: /^Inspect$/ }).click()

    // Upload thermal image
    await page.setInputFiles('input[type=file]', THERMAL_IMG)
    await page.getByRole('button', { name: /submit|inspect/i }).last().click()

    // Wait for inspect result and canvas to appear
    const canvas = page.locator('canvas').first()
    await expect(canvas).toBeVisible({ timeout: 60_000 })

    // Also wait for the "Download Report" button (confirms inspectResult is set)
    await expect(page.getByRole('link', { name: /Download Report/i })).toBeVisible({
      timeout: 10_000,
    })

    // Draw a correction box by dragging across the canvas
    const box = await canvas.boundingBox()
    if (!box) throw new Error('Canvas bounding box not found')
    const startX = box.x + box.width * 0.2
    const startY = box.y + box.height * 0.2
    const endX = box.x + box.width * 0.6
    const endY = box.y + box.height * 0.6

    await page.mouse.move(startX, startY)
    await page.mouse.down()
    await page.mouse.move(endX, endY, { steps: 10 })
    await page.mouse.up()

    // Class picker appears
    await expect(page.locator('text=Assign class')).toBeVisible({ timeout: 5_000 })

    // Select a class
    await page.selectOption('.annotation-class-picker select, div:has(text=Assign) select', 'hot-spot-low')

    // Save
    await page.getByRole('button', { name: /^Save$/ }).click()

    // Picker is gone
    await expect(page.locator('text=Assign class')).not.toBeVisible()

    // Click approximately where we drew the box (canvas centre of our drag)
    const clickX = (startX + endX) / 2
    const clickY = (startY + endY) / 2
    await page.mouse.click(clickX, clickY)

    // Delete button appears (selected box)
    await expect(page.getByRole('button', { name: /Delete/i })).toBeVisible({ timeout: 5_000 })

    // Delete the correction
    await page.getByRole('button', { name: /Delete/i }).click()

    // Delete button gone
    await expect(page.getByRole('button', { name: /Delete/i })).not.toBeVisible()
  })

  test('cancel discards the box without saving', async ({ page }) => {
    await page.goto('/platform')
    await page.getByRole('button', { name: /^Inspect$/ }).click()
    await page.setInputFiles('input[type=file]', THERMAL_IMG)
    await page.getByRole('button', { name: /submit|inspect/i }).last().click()

    const canvas = page.locator('canvas').first()
    await expect(canvas).toBeVisible({ timeout: 60_000 })

    const box = await canvas.boundingBox()
    if (!box) throw new Error('Canvas bounding box not found')
    await page.mouse.move(box.x + 30, box.y + 30)
    await page.mouse.down()
    await page.mouse.move(box.x + 150, box.y + 100, { steps: 5 })
    await page.mouse.up()

    await expect(page.locator('text=Assign class')).toBeVisible({ timeout: 5_000 })

    // Cancel instead of saving
    await page.getByRole('button', { name: /^Cancel$/ }).click()

    // Picker is gone and no box remains to select
    await expect(page.locator('text=Assign class')).not.toBeVisible()
    // No delete button visible (nothing selected)
    await expect(page.getByRole('button', { name: /Delete/i })).not.toBeVisible()
  })
})
```

- [ ] **Step 2: Ensure fixture image exists**

```bash
ls tests/fixtures/sample_mission/thermal/img_001.jpg
```

Expected: file present. If not, run `python3 scripts/make_sample_mission.py` first.

- [ ] **Step 3: Start services and run the test**

```bash
./run.sh all &   # or docker compose up -d
sleep 15
cd website/nextjs && npm run test:e2e -- tests/e2e/annotation.spec.ts
```

Expected: 2 passed.

If the canvas drag doesn't register because of a pointer event issue, use `page.dispatchEvent('canvas', 'mousedown', ...)` as a fallback and update the test accordingly. If the class picker `<select>` locator is wrong, use `mcp__playwright__browser_snapshot` to inspect the actual DOM and update the selector.

- [ ] **Step 4: Run full e2e suite to confirm no golden-path regressions**

```bash
cd website/nextjs && npm run test:e2e
```

Expected: all e2e tests pass (golden-path + 2 annotation tests).

- [ ] **Step 5: Commit**

```bash
git add website/nextjs/tests/e2e/annotation.spec.ts
git commit -m "test(e2e): playwright coverage for annotation editor draw/save/delete"
```

---

## Task 9: Final acceptance pass

**Files:** none — verification only.

- [ ] **Step 1: Run the full test suite**

```bash
./scripts/test_all.sh
```

Expected: backend pytest, vitest, and playwright all exit 0.

- [ ] **Step 2: Check the acceptance list**

```
Infrastructure
- [ ] alembic upgrade head on a fresh DB creates all tables including jobs and corrections
- [ ] alembic upgrade head on a pre-Phase-4 DB adds jobs and corrections without dropping any existing table
- [ ] API lifespan logs "Alembic migrations: up to date" on start
- [ ] GET /results/{job_id}/{filename} returns 200 for a known annotated image
- [ ] ParkPanelDetail thumbnail loads (no /image/ 404 in browser DevTools network tab)
- [ ] docker compose up -d succeeds; docker compose logs api shows no GPU errors on CPU host
- [ ] AXALON_RESULTS_TTL_HOURS=1 triggers cleanup on restart (set short TTL, create a job older than 1h via direct DB insert, restart API, verify output dir deleted)

Reports
- [ ] After an inspect + drawn correction, GET /report/{inspect_job_id}?format=json returns {"corrections": [...]} with the saved box
- [ ] "Download Report (JSON)" link is visible in Inspect tab after a result appears
- [ ] Downloaded JSON contains the correction drawn in the session

History tab
- [ ] Selecting SOLAR_PARK_DEMO in History tab renders the TrendChart with 4 coloured lines
- [ ] Chart is readable at 375px phone viewport (no overflow)
- [ ] Recurring Faults table appears for parks with ≥2 inspections sharing a panel
- [ ] Selecting a park with only 1 inspection shows "Need at least 2 inspections" in the chart area

Operations tab
- [ ] Park Mode dropdown has three options: Auto-detect, Numbered (OCR), Unnumbered (Grid)
- [ ] Selecting "Numbered (OCR)" and starting a batch sends park_mode=numbered in the request

Tests
- [ ] npm test: all vitest tests pass, including 7 AuthGate tests
- [ ] npm run test:e2e: golden-path + 2 annotation spec tests all pass
- [ ] pytest tests/backend/: all pass including test_trend.py, test_corrections_in_report.py
```

- [ ] **Step 3: For any unchecked item, fix the underlying issue and re-verify.**

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore(platform): Phase 5 acceptance pass" || echo "nothing to commit"
```

---

## Done

When Task 9 passes, Phase 5 is complete.

**Remaining for Phase 6 (explicitly deferred):**
- RGB+thermal fusion (`core/fusion.py`) — thermal→RGB projection + annotated RGB output in Inspect tab
- Orthomosaic upload UI — `api.uploadOrtho()` is in the client but no tab exposes it
- Park Map PNG export — server-side render via `map_renderer.py` + download button in ParkMapTab
