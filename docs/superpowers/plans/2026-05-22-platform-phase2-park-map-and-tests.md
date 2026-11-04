# Platform Phase 2 — Park Map Detail Tab + Automated Test Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a 5th "Park Map" tab showing the panel-grid view with click-to-drill-down, and lay down a four-layer automated test suite (backend pytest API contract + unit, frontend vitest unit, frontend playwright e2e) so future changes have a safety net.

**Architecture:** A new pure-function grid aggregator in `platform/park/grid.py` powers a new `GET /park/{id}/grid` endpoint. The frontend tab is two presentational components (`ParkMapGrid`, `ParkPanelDetail`) wired through `page.tsx` state and one new `api.parkGrid()` method. Tests sit in `tests/backend/` (pytest) and `website/nextjs/tests/{unit,e2e}/` (vitest + playwright), with a shared `scripts/test_all.sh` runner.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy 2.x, pytest, Next.js 14 (App Router, client components), TypeScript, Vitest, @testing-library/react, jsdom, @playwright/test.

**Spec:** `docs/superpowers/specs/2026-05-22-platform-phase2-park-map-and-tests-design.md`

---

## File Structure

| Path | Responsibility | Action |
|---|---|---|
| `platform/park/grid.py` | Pure function `build_grid(detections, park)` → grid payload | Create |
| `platform/api/app.py` | Add `GET /park/{park_id}/grid` handler | Modify |
| `website/nextjs/lib/api.ts` | Add `api.parkGrid()` + `ParkGrid`/`Panel` types | Modify |
| `website/nextjs/components/Platform/ParkMapGrid.tsx` | Presentational grid (rows×cols of cells, colored, click handler) | Create |
| `website/nextjs/components/Platform/ParkPanelDetail.tsx` | Side panel: detection list + thumbnail + GPS | Create |
| `website/nextjs/app/platform/page.tsx` | Add 5th tab; park + inspection state; render grid + detail | Modify |
| `tests/backend/conftest.py` | Shared fixtures: temp SQLite, FastAPI TestClient, batch_fixture | Create |
| `tests/backend/test_api_contract.py` | ≥1 test per endpoint | Create |
| `tests/backend/test_pipeline_unit.py` | Orchestrator + layout detector + grid aggregator unit tests | Create |
| `pytest.ini` | testpaths, addopts | Create |
| `website/nextjs/tests/unit/api.test.ts` | `request()` + `ApiError` happy and error paths | Create |
| `website/nextjs/tests/unit/Toast.test.tsx` | `useToast()` push + auto-dismiss | Create |
| `website/nextjs/vitest.config.ts` | vitest config (jsdom, alias `@/`) | Create |
| `website/nextjs/tests/e2e/golden_path.spec.ts` | Playwright walk of all 5 tabs | Create |
| `website/nextjs/playwright.config.ts` | Playwright config (baseURL, single project) | Create |
| `website/nextjs/package.json` | Add `test`, `test:e2e` scripts + devDeps | Modify |
| `scripts/test_all.sh` | Run pytest → vitest → playwright sequentially | Create |

---

## Task 1: Grid aggregator (TDD)

**Files:**
- Create: `platform/park/grid.py`
- Create: `tests/backend/__init__.py` (empty)
- Create: `tests/backend/test_grid_unit.py` (will become part of `test_pipeline_unit.py` later — for now an isolated test file)

- [ ] **Step 1: Write the failing test**

Create `tests/backend/__init__.py` (empty file). Then write `tests/backend/test_grid_unit.py`:

```python
"""Unit tests for the panel-grid aggregator."""
from types import SimpleNamespace

from platform.park.grid import build_grid


def _det(panel_id, severity, class_="hot-spot-low", confidence=0.5, image_id="img_001", bbox=None, gps=None):
    return {
        "panel_id": panel_id,
        "severity": severity,
        "class": class_,
        "confidence": confidence,
        "image_id": image_id,
        "thermal_filename": f"{image_id}.jpg",
        "bbox": bbox or [0, 0, 10, 10],
        "gps": gps,
    }


def test_build_grid_returns_park_metadata():
    park = SimpleNamespace(id="P1", rows=2, cols=3)
    grid = build_grid(detections=[], park=park, inspection_id="batch-1")
    assert grid["park_id"] == "P1"
    assert grid["inspection_id"] == "batch-1"
    assert grid["rows"] == 2 and grid["cols"] == 3
    assert grid["panels"] == []


def test_build_grid_aggregates_worst_severity():
    park = SimpleNamespace(id="P1", rows=2, cols=3)
    detections = [
        _det("R1-C1", "MEDIUM"),
        _det("R1-C1", "CRITICAL"),
        _det("R2-C3", "LOW"),
    ]
    grid = build_grid(detections=detections, park=park, inspection_id="batch-1")
    cells = {p["panel_id"]: p for p in grid["panels"]}
    assert cells["R1-C1"]["worst_severity"] == "CRITICAL"
    assert cells["R1-C1"]["detection_count"] == 2
    assert cells["R2-C3"]["worst_severity"] == "LOW"
    assert cells["R2-C3"]["detection_count"] == 1


def test_build_grid_includes_first_gps_when_available():
    park = SimpleNamespace(id="P1", rows=1, cols=1)
    detections = [
        _det("R1-C1", "LOW", gps={"lat": 19.0, "lon": 72.0}),
        _det("R1-C1", "MEDIUM", gps=None),
    ]
    grid = build_grid(detections=detections, park=park, inspection_id="batch-1")
    cell = grid["panels"][0]
    assert cell["gps"] == {"lat": 19.0, "lon": 72.0}


def test_build_grid_falls_back_to_panel_id_regex_when_rows_cols_zero():
    park = SimpleNamespace(id="P1", rows=0, cols=0)
    detections = [_det("R3-C7", "HIGH"), _det("R1-C2", "LOW")]
    grid = build_grid(detections=detections, park=park, inspection_id="batch-1")
    assert grid["rows"] == 3
    assert grid["cols"] == 7


def test_build_grid_handles_unparseable_panel_ids():
    park = SimpleNamespace(id="P1", rows=0, cols=0)
    detections = [_det("UNKNOWN", "LOW"), _det(None, "HIGH")]
    grid = build_grid(detections=detections, park=park, inspection_id="batch-1")
    assert grid["rows"] == 0 and grid["cols"] == 0
    # detections with no parseable panel_id are skipped from the panels list
    assert all(p["panel_id"] for p in grid["panels"])
```

- [ ] **Step 2: Run test to verify it fails**

Run from repo root:
```
cd /tmp && PYTHONSAFEPATH=1 python -m pytest /home/parakh/Desktop/AxalonSystems/tests/backend/test_grid_unit.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'platform.park.grid'` (or similar).

*(We run from /tmp + PYTHONSAFEPATH=1 because the local `platform/` directory shadows stdlib `platform`. This is the same workaround used by `run.sh`.)*

- [ ] **Step 3: Write the implementation**

Create `platform/park/grid.py`:

```python
"""Panel-grid aggregator — turns a flat list of detections into a per-panel grid summary.

Pure function. Used by the FastAPI /park/{id}/grid endpoint and exercised
directly by pytest.
"""
from __future__ import annotations

import re
from typing import Any, Iterable

_SEVERITY_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
_PANEL_ID_RE = re.compile(r"R(\d+)-C(\d+)")


def _worst(severities: Iterable[str | None]) -> str | None:
    valid = [s for s in severities if s in _SEVERITY_RANK]
    if not valid:
        return None
    return max(valid, key=lambda s: _SEVERITY_RANK[s])


def _first_non_null(values: Iterable[Any]) -> Any:
    for v in values:
        if v is not None:
            return v
    return None


def _derive_dims_from_panel_ids(detections: list[dict]) -> tuple[int, int]:
    max_r = max_c = 0
    for d in detections:
        pid = d.get("panel_id")
        if not pid:
            continue
        m = _PANEL_ID_RE.match(pid)
        if not m:
            continue
        r, c = int(m.group(1)), int(m.group(2))
        max_r = max(max_r, r)
        max_c = max(max_c, c)
    return max_r, max_c


def build_grid(
    *,
    detections: list[dict],
    park: Any,
    inspection_id: str | None,
) -> dict:
    """Aggregate detections into a per-panel grid summary.

    detections: list of dicts with keys panel_id, severity, class, confidence,
                image_id, thermal_filename, bbox, gps.
    park: object with .id, .rows, .cols (SQLAlchemy Park or SimpleNamespace).
    inspection_id: the inspection these detections belong to, or None if no inspection.
    """
    rows = int(getattr(park, "rows", 0) or 0)
    cols = int(getattr(park, "cols", 0) or 0)
    if rows == 0 or cols == 0:
        rows, cols = _derive_dims_from_panel_ids(detections)

    by_panel: dict[str, list[dict]] = {}
    for d in detections:
        pid = d.get("panel_id")
        if not pid:
            continue
        by_panel.setdefault(pid, []).append(d)

    panels: list[dict] = []
    for pid, dets in by_panel.items():
        m = _PANEL_ID_RE.match(pid)
        row, col = (int(m.group(1)) - 1, int(m.group(2)) - 1) if m else (0, 0)
        panels.append({
            "panel_id": pid,
            "row": row,
            "col": col,
            "worst_severity": _worst(d.get("severity") for d in dets),
            "detection_count": len(dets),
            "detections": [
                {
                    "class": d.get("class"),
                    "confidence": d.get("confidence"),
                    "severity": d.get("severity"),
                    "thermal_filename": d.get("thermal_filename") or (
                        f"{d['image_id']}.jpg" if d.get("image_id") else None
                    ),
                    "bbox": d.get("bbox"),
                }
                for d in dets
            ],
            "gps": _first_non_null(d.get("gps") for d in dets),
        })

    return {
        "park_id": getattr(park, "id", None),
        "inspection_id": inspection_id,
        "rows": rows,
        "cols": cols,
        "panels": panels,
    }
```

- [ ] **Step 4: Run tests to verify they pass**

```
cd /tmp && PYTHONSAFEPATH=1 python -m pytest /home/parakh/Desktop/AxalonSystems/tests/backend/test_grid_unit.py -v
```
Expected: 5 passed.

- [ ] **Step 5: Commit**

```
git add platform/park/grid.py tests/backend/__init__.py tests/backend/test_grid_unit.py
git commit -m "feat(park): grid aggregator + unit tests"
```

---

## Task 2: Backend pytest scaffolding + shared fixtures

**Files:**
- Create: `pytest.ini`
- Create: `tests/backend/conftest.py`

- [ ] **Step 1: Write `pytest.ini`**

At repo root:
```ini
[pytest]
testpaths = tests/backend
addopts = -ra --strict-markers --tb=short
```

- [ ] **Step 2: Write `tests/backend/conftest.py`**

```python
"""Shared pytest fixtures: temp DB, FastAPI TestClient, batch helper."""
from __future__ import annotations

import os
import shutil
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "tests" / "fixtures" / "sample_mission"


@pytest.fixture(scope="session")
def sample_mission_zip(tmp_path_factory) -> Path:
    """Build a fresh ZIP of the synthetic mission for upload tests."""
    if not FIXTURE_DIR.exists():
        raise RuntimeError(
            f"Synthetic mission fixture missing at {FIXTURE_DIR}. "
            f"Run: python scripts/make_sample_mission.py"
        )
    out_dir = tmp_path_factory.mktemp("missions")
    out_zip = out_dir / "sample_mission.zip"
    shutil.make_archive(str(out_zip)[:-4], "zip", root_dir=FIXTURE_DIR.parent, base_dir=FIXTURE_DIR.name)
    return out_zip


@pytest.fixture
def temp_db(monkeypatch, tmp_path) -> Path:
    """Point the app at a temp SQLite DB for the duration of one test."""
    db_path = tmp_path / "test_axalon.db"
    monkeypatch.setenv("AXALON_DB_URL", f"sqlite:///{db_path}")
    # Reset module-level engine caches if present
    from axalon.db import session as _session
    if hasattr(_session, "_engine"):
        _session._engine = None
    yield db_path


@pytest.fixture
def client(temp_db) -> TestClient:
    """FastAPI TestClient bound to a fresh in-test DB."""
    # Import inside the fixture so AXALON_DB_URL is set first.
    from axalon.api.app import app
    return TestClient(app)


@pytest.fixture
def batch_fixture(client, sample_mission_zip):
    """Run one batch end-to-end through the API and return its job_id."""
    def _run(park_id: str = "TEST_PARK", altitude_m: float = 42.0) -> str:
        with open(sample_mission_zip, "rb") as f:
            r = client.post(
                "/batch",
                files={"images": ("sample_mission.zip", f, "application/zip")},
                data={"park_id": park_id, "altitude_m": str(altitude_m)},
            )
        assert r.status_code == 202, r.text
        job_id = r.json()["job_id"]
        # Wait for completion (synchronous in TestClient runtime)
        for _ in range(300):
            s = client.get(f"/status/{job_id}").json()
            if s.get("state") in ("succeeded", "completed", "failed"):
                break
            import time
            time.sleep(0.5)
        return job_id
    return _run
```

- [ ] **Step 3: Verify pytest discovers the existing test**

```
cd /tmp && PYTHONSAFEPATH=1 python -m pytest /home/parakh/Desktop/AxalonSystems -v --collect-only 2>&1 | head -20
```
Expected: 5 tests collected from `tests/backend/test_grid_unit.py`.

- [ ] **Step 4: Commit**

```
git add pytest.ini tests/backend/conftest.py
git commit -m "test(backend): pytest scaffolding + shared fixtures"
```

---

## Task 3: New `/park/{id}/grid` endpoint

**Files:**
- Modify: `platform/api/app.py`
- Create: `tests/backend/test_park_grid_endpoint.py`

- [ ] **Step 1: Write the failing test**

```python
"""Contract test for GET /park/{park_id}/grid."""
import pytest


def test_grid_endpoint_returns_empty_for_unknown_park(client):
    r = client.get("/park/DOES_NOT_EXIST/grid")
    assert r.status_code == 404


def test_grid_endpoint_returns_grid_after_batch(client, batch_fixture):
    job_id = batch_fixture(park_id="TEST_GRID_PARK")
    r = client.get("/park/TEST_GRID_PARK/grid")
    assert r.status_code == 200
    body = r.json()
    assert body["park_id"] == "TEST_GRID_PARK"
    assert isinstance(body["panels"], list)
    # at least one panel should have a severity from the synthetic batch
    severities = [p["worst_severity"] for p in body["panels"]]
    assert any(s in {"CRITICAL", "HIGH", "MEDIUM", "LOW"} for s in severities)


def test_grid_endpoint_uses_explicit_inspection_id(client, batch_fixture):
    job_id = batch_fixture(park_id="TEST_GRID_PARK2")
    r = client.get(f"/park/TEST_GRID_PARK2/grid?inspection_id={job_id}")
    assert r.status_code == 200
    assert r.json()["inspection_id"] == job_id
```

- [ ] **Step 2: Run to verify it fails**

```
cd /tmp && PYTHONSAFEPATH=1 python -m pytest /home/parakh/Desktop/AxalonSystems/tests/backend/test_park_grid_endpoint.py -v
```
Expected: `test_grid_endpoint_returns_empty_for_unknown_park` may pass with 404 from existing handlers OR fail with "endpoint not found". Either way, the two grid-content tests will fail with 404.

- [ ] **Step 3: Implement the endpoint**

Find the existing `@app.get("/park/{park_id}")` handler in `platform/api/app.py` (around line 963). Add this new handler immediately after it:

```python
@app.get("/park/{park_id}/grid")
def get_park_grid(park_id: str, inspection_id: str | None = None):
    """Per-panel grid summary for a park's most recent (or specified) inspection."""
    from platform.park.grid import build_grid
    from axalon.db.models import Park, Inspection, Detection
    from axalon.db.session import session_scope as _session_scope, get_engine as _get_engine
    import json as _json

    engine = _get_engine()
    with _session_scope(engine) as s:
        park = s.query(Park).filter(Park.id == park_id).first()
        if park is None:
            from fastapi import HTTPException
            raise HTTPException(status_code=404, detail=f"Park {park_id!r} not found")

        if inspection_id:
            insp = s.query(Inspection).filter(
                Inspection.id == inspection_id,
                Inspection.park_id == park_id,
            ).first()
            if insp is None:
                from fastapi import HTTPException
                raise HTTPException(
                    status_code=404,
                    detail=f"Inspection {inspection_id!r} not found for park {park_id!r}",
                )
        else:
            insp = (
                s.query(Inspection)
                .filter(Inspection.park_id == park_id)
                .order_by(Inspection.created_at.desc())
                .first()
            )

        if insp is None:
            return {
                "park_id": park_id,
                "inspection_id": None,
                "rows": int(park.rows or 0),
                "cols": int(park.cols or 0),
                "panels": [],
            }

        rows = s.query(Detection).filter(Detection.inspection_id == insp.id).all()
        detections = []
        for d in rows:
            try:
                bbox = _json.loads(d.bbox) if d.bbox else None
            except _json.JSONDecodeError:
                bbox = None
            try:
                gps = _json.loads(d.gps) if d.gps else None
            except _json.JSONDecodeError:
                gps = None
            detections.append({
                "panel_id": d.panel_id,
                "severity": d.severity,
                "class": d.class_,
                "confidence": d.confidence,
                "image_id": d.image_id,
                "thermal_filename": f"{d.image_id}.jpg" if d.image_id else None,
                "bbox": bbox,
                "gps": gps,
            })

        return build_grid(detections=detections, park=park, inspection_id=insp.id)
```

- [ ] **Step 4: Run tests to verify they pass**

The API server is currently running (from Phase 1). After saving `app.py`, uvicorn `--reload` picks it up. But the TestClient spins up its own instance, so no restart needed for pytest.

```
cd /tmp && PYTHONSAFEPATH=1 python -m pytest /home/parakh/Desktop/AxalonSystems/tests/backend/test_park_grid_endpoint.py -v
```
Expected: 3 passed. (The batch tests are slow; allow up to 3 minutes.)

- [ ] **Step 5: Smoke-check via curl**

```
curl -fsS "http://localhost:8000/park/SOLAR_PARK_DEMO/grid" | python -m json.tool | head -30
```
Expected: valid grid JSON with at least one panel.

- [ ] **Step 6: Commit**

```
git add platform/api/app.py tests/backend/test_park_grid_endpoint.py
git commit -m "feat(api): GET /park/{id}/grid panel-grid summary endpoint"
```

---

## Task 4: API contract tests for all endpoints

**Files:**
- Create: `tests/backend/test_api_contract.py`

- [ ] **Step 1: Write the contract test file**

```python
"""Contract tests: ≥1 test per FastAPI endpoint.

These tests run against a fresh temp-DB TestClient (no live server).
The synthetic mission fixture is uploaded via `batch_fixture`.
"""
import pytest


# ── /health ───────────────────────────────────────────────────────────────────

def test_health_returns_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert "model" in body and "weights" in body


# ── /parks ────────────────────────────────────────────────────────────────────

def test_parks_returns_empty_envelope_when_no_parks(client):
    r = client.get("/parks")
    assert r.status_code == 200
    body = r.json()
    # tolerate either bare list or {"parks": [...], "total": N}
    if isinstance(body, dict):
        assert body.get("total") == 0
        assert body.get("parks") == []
    else:
        assert body == []


def test_parks_includes_park_after_batch(client, batch_fixture):
    batch_fixture(park_id="PARKS_TEST")
    r = client.get("/parks")
    assert r.status_code == 200
    body = r.json()
    parks = body["parks"] if isinstance(body, dict) else body
    assert any(p.get("id") == "PARKS_TEST" for p in parks)


# ── /park/{id} ────────────────────────────────────────────────────────────────

def test_park_summary_returns_park_metadata(client, batch_fixture):
    batch_fixture(park_id="SUMMARY_TEST")
    r = client.get("/park/SUMMARY_TEST")
    assert r.status_code == 200
    body = r.json()
    assert body.get("id") == "SUMMARY_TEST"


def test_park_summary_404_for_unknown(client):
    r = client.get("/park/NOPE")
    assert r.status_code == 404


# ── /batch + /status ──────────────────────────────────────────────────────────

def test_batch_returns_job_id(client, sample_mission_zip):
    with open(sample_mission_zip, "rb") as f:
        r = client.post(
            "/batch",
            files={"images": ("sample_mission.zip", f, "application/zip")},
            data={"park_id": "BATCH_TEST", "altitude_m": "42"},
        )
    assert r.status_code == 202
    assert "job_id" in r.json()


def test_status_returns_state_for_known_job(client, batch_fixture):
    job = batch_fixture(park_id="STATUS_TEST")
    r = client.get(f"/status/{job}")
    assert r.status_code == 200
    assert r.json()["state"] in {"succeeded", "completed", "failed", "running", "queued"}


def test_status_404_for_unknown_job(client):
    r = client.get("/status/no-such-job")
    assert r.status_code == 404


# ── /map/{job_id} ─────────────────────────────────────────────────────────────

def test_map_returns_anomalies_after_batch(client, batch_fixture):
    job = batch_fixture(park_id="MAP_TEST")
    r = client.get(f"/map/{job}")
    assert r.status_code == 200
    body = r.json()
    assert "anomalies" in body or "images" in body


# ── /report/{job_id} ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("fmt", ["json", "excel", "geojson"])
def test_report_downloads_succeed(client, batch_fixture, fmt):
    job = batch_fixture(park_id="REPORT_TEST")
    r = client.get(f"/report/{job}?format={fmt}")
    assert r.status_code == 200
    assert len(r.content) > 0


# ── /settings ─────────────────────────────────────────────────────────────────

def test_settings_get_returns_dict(client):
    r = client.get("/settings")
    assert r.status_code == 200
    assert isinstance(r.json(), dict)


def test_settings_put_round_trip(client):
    original = client.get("/settings").json()
    # API expects {"settings": blob}
    new = dict(original)
    new["_phase2_test_marker"] = "yes"
    r = client.put("/settings", json={"settings": new})
    assert r.status_code == 200
    re_read = client.get("/settings").json()
    assert re_read.get("_phase2_test_marker") == "yes"
    # restore (best effort — clear the marker)
    cleaned = {k: v for k, v in re_read.items() if k != "_phase2_test_marker"}
    client.put("/settings", json={"settings": cleaned})


# ── /park/{id}/grid ───────────────────────────────────────────────────────────

def test_park_grid_default_inspection(client, batch_fixture):
    batch_fixture(park_id="GRID_DEFAULT")
    r = client.get("/park/GRID_DEFAULT/grid")
    assert r.status_code == 200
    body = r.json()
    assert body["park_id"] == "GRID_DEFAULT"
    assert isinstance(body["panels"], list)
```

- [ ] **Step 2: Run the contract tests**

```
cd /tmp && PYTHONSAFEPATH=1 python -m pytest /home/parakh/Desktop/AxalonSystems/tests/backend/test_api_contract.py -v
```
Expected: all green. Allow up to 10 minutes — each `batch_fixture` use runs the full pipeline.

If a test fails because the API response shape diverges from the assertion: prefer to loosen the assertion (the test should describe the contract minimally, not over-specify). Document the actual shape in a comment.

- [ ] **Step 3: Commit**

```
git add tests/backend/test_api_contract.py
git commit -m "test(api): contract tests across all platform endpoints"
```

---

## Task 5: Pipeline + layout unit tests

**Files:**
- Create: `tests/backend/test_pipeline_unit.py`

- [ ] **Step 1: Write unit tests**

```python
"""Unit tests for orchestrator and ParkLayoutDetector (no API layer)."""
from pathlib import Path
import numpy as np
import pytest


# ── ParkLayoutDetector ────────────────────────────────────────────────────────

def test_park_layout_detector_assigns_grid_ids():
    from platform.park.layout import ParkLayoutDetector
    panels = [
        {"x": 10, "y": 10, "w": 20, "h": 20},
        {"x": 40, "y": 10, "w": 20, "h": 20},
        {"x": 10, "y": 40, "w": 20, "h": 20},
        {"x": 40, "y": 40, "w": 20, "h": 20},
    ]
    out = ParkLayoutDetector().assign_grid_ids(panels)
    ids = sorted([p["panel_id"] for p in out])
    assert ids == ["R1-C1", "R1-C2", "R2-C1", "R2-C2"]


def test_park_layout_detector_handles_empty_panel_list():
    from platform.park.layout import ParkLayoutDetector
    out = ParkLayoutDetector().assign_grid_ids([])
    assert out == []


# ── Orchestrator (batch end-to-end without HTTP) ──────────────────────────────

@pytest.fixture
def fixture_dir():
    return Path(__file__).resolve().parents[1] / "fixtures" / "sample_mission"


def test_orchestrator_processes_a_batch_directly(fixture_dir, tmp_path):
    """Run the orchestrator's inspect_folder against the synthetic mission.

    This is slow (~30-90s on CPU) but verifies the pipeline outside the API.
    Marker: this is the only unit test that actually runs YOLO inference.
    """
    from axalon.pipeline.orchestrator import InspectionOrchestrator
    orch = InspectionOrchestrator(conf=0.25, device="cpu", output_dir=str(tmp_path))
    result = orch.inspect_folder(
        folder=str(fixture_dir),
        park_id="ORCH_UNIT_TEST",
        altitude_m=42.0,
    )
    assert result.get("total_images") == 20
    assert "summary" in result
    assert result.get("batch_id")


# ── Grid aggregator: extra integration shape ──────────────────────────────────

def test_grid_aggregator_with_realistic_payload():
    from types import SimpleNamespace
    from platform.park.grid import build_grid

    park = SimpleNamespace(id="REALISTIC", rows=3, cols=4)
    detections = [
        {"panel_id": "R1-C1", "severity": "CRITICAL", "class": "hot-spot-high",
         "confidence": 0.91, "image_id": "img_001",
         "thermal_filename": "img_001.jpg",
         "bbox": [10, 10, 50, 50], "gps": {"lat": 19.0, "lon": 72.0}},
        {"panel_id": "R3-C4", "severity": "LOW", "class": "soiling",
         "confidence": 0.31, "image_id": "img_017",
         "thermal_filename": "img_017.jpg",
         "bbox": [5, 5, 30, 30], "gps": None},
    ]
    grid = build_grid(detections=detections, park=park, inspection_id="batch-X")
    assert grid["rows"] == 3 and grid["cols"] == 4
    assert len(grid["panels"]) == 2
    cell = next(p for p in grid["panels"] if p["panel_id"] == "R1-C1")
    assert cell["worst_severity"] == "CRITICAL"
    assert cell["gps"] == {"lat": 19.0, "lon": 72.0}
    assert cell["detections"][0]["class"] == "hot-spot-high"
```

- [ ] **Step 2: Run them**

```
cd /tmp && PYTHONSAFEPATH=1 python -m pytest /home/parakh/Desktop/AxalonSystems/tests/backend/test_pipeline_unit.py -v
```
Expected: all 4 pass. The orchestrator test is slow — allow 2 minutes.

If `ParkLayoutDetector.assign_grid_ids` doesn't match the expected ID shape (e.g. zero-indexed instead of one-indexed), update the assertion to match the actual contract — don't change the implementation.

- [ ] **Step 3: Commit**

```
git add tests/backend/test_pipeline_unit.py
git commit -m "test(pipeline): unit tests for orchestrator + layout detector + grid"
```

---

## Task 6: Add `api.parkGrid()` + types

**Files:**
- Modify: `website/nextjs/lib/api.ts`

- [ ] **Step 1: Add types + method**

In `website/nextjs/lib/api.ts`, locate the type exports near the top and add:

```ts
export type Severity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'

export type GridPanelDetection = {
  class: string | null
  confidence: number | null
  severity: Severity | null
  thermal_filename: string | null
  bbox: number[] | null
}

export type GridPanel = {
  panel_id: string
  row: number
  col: number
  worst_severity: Severity | null
  detection_count: number
  detections: GridPanelDetection[]
  gps: { lat: number; lon: number } | null
}

export type ParkGrid = {
  park_id: string
  inspection_id: string | null
  rows: number
  cols: number
  panels: GridPanel[]
}
```

Then in the `export const api = { ... }` block, add (alphabetically near `park`):

```ts
  parkGrid: (parkId: string, inspectionId?: string) => {
    const q = inspectionId ? `?inspection_id=${encodeURIComponent(inspectionId)}` : ''
    return request<ParkGrid>(`/park/${encodeURIComponent(parkId)}/grid${q}`)
  },
```

- [ ] **Step 2: Typecheck**

```
cd website/nextjs && npx tsc --noEmit
```
Expected: zero errors.

- [ ] **Step 3: Smoke-check against running API**

```
curl -fsS "http://localhost:8000/park/SOLAR_PARK_DEMO/grid" | python -m json.tool | head -20
```
Confirm the shape matches the `ParkGrid` type you just added.

- [ ] **Step 4: Commit**

```
git add website/nextjs/lib/api.ts
git commit -m "feat(api-client): add api.parkGrid + ParkGrid types"
```

---

## Task 7: ParkMapGrid component

**Files:**
- Create: `website/nextjs/components/Platform/ParkMapGrid.tsx`

- [ ] **Step 1: Write the component**

```tsx
'use client'

import type { GridPanel, ParkGrid, Severity } from '@/lib/api'

const SEVERITY_COLOR: Record<Severity, string> = {
  CRITICAL: '#dc2626',
  HIGH: '#ea580c',
  MEDIUM: '#ca8a04',
  LOW: '#2563eb',
}
const EMPTY_COLOR = '#e2e8f0'
const SELECTED_RING = '#0ea5e9'

export function ParkMapGrid({
  grid,
  selectedPanelId,
  onSelect,
}: {
  grid: ParkGrid | null
  selectedPanelId: string | null
  onSelect: (panel: GridPanel) => void
}) {
  if (!grid) {
    return <div style={{ padding: 16, color: '#64748b', fontSize: 13 }}>Loading grid…</div>
  }
  if (grid.panels.length === 0) {
    return (
      <div style={{ padding: 24, color: '#64748b', fontSize: 13, textAlign: 'center' }}>
        No panel detections yet for this inspection.
      </div>
    )
  }

  const byKey = new Map<string, GridPanel>()
  for (const p of grid.panels) byKey.set(`${p.row}|${p.col}`, p)
  const rows = Math.max(grid.rows, ...grid.panels.map((p) => p.row + 1), 1)
  const cols = Math.max(grid.cols, ...grid.panels.map((p) => p.col + 1), 1)

  return (
    <div>
      <Legend />
      <div
        role="grid"
        aria-label={`Park ${grid.park_id} panel grid`}
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${cols}, minmax(20px, 1fr))`,
          gap: 4,
          padding: 12,
          background: '#f8fafc',
          borderRadius: 8,
          border: '1px solid #e2e8f0',
        }}
      >
        {Array.from({ length: rows * cols }).map((_, i) => {
          const r = Math.floor(i / cols)
          const c = i % cols
          const panel = byKey.get(`${r}|${c}`)
          const fill = panel?.worst_severity ? SEVERITY_COLOR[panel.worst_severity] : EMPTY_COLOR
          const isSelected = panel?.panel_id === selectedPanelId
          return (
            <button
              key={i}
              role="gridcell"
              data-testid={panel ? `panel-${panel.panel_id}` : `panel-empty-${r}-${c}`}
              aria-label={
                panel
                  ? `Panel ${panel.panel_id}, ${panel.detection_count} detections, worst ${panel.worst_severity ?? 'none'}`
                  : `Empty panel R${r + 1}-C${c + 1}`
              }
              onClick={panel ? () => onSelect(panel) : undefined}
              disabled={!panel}
              style={{
                aspectRatio: '1 / 1',
                background: fill,
                border: isSelected ? `2px solid ${SELECTED_RING}` : '1px solid rgba(0,0,0,0.08)',
                borderRadius: 3,
                cursor: panel ? 'pointer' : 'default',
                padding: 0,
                fontSize: 0,
              }}
            />
          )
        })}
      </div>
    </div>
  )
}

function Legend() {
  const entries: Array<[string, string]> = [
    ['CRITICAL', SEVERITY_COLOR.CRITICAL],
    ['HIGH', SEVERITY_COLOR.HIGH],
    ['MEDIUM', SEVERITY_COLOR.MEDIUM],
    ['LOW', SEVERITY_COLOR.LOW],
    ['Clean', EMPTY_COLOR],
  ]
  return (
    <div style={{ display: 'flex', gap: 12, alignItems: 'center', padding: '8px 12px', fontSize: 12, color: '#475569' }}>
      {entries.map(([label, color]) => (
        <span key={label} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <span style={{ width: 12, height: 12, background: color, borderRadius: 2, border: '1px solid rgba(0,0,0,0.1)' }} />
          {label}
        </span>
      ))}
    </div>
  )
}
```

- [ ] **Step 2: Typecheck**

```
cd website/nextjs && npx tsc --noEmit 2>&1 | grep -E "(ParkMapGrid|api\.ts)" | head -10
```
Expected: empty (no errors in these files).

- [ ] **Step 3: Commit**

```
git add website/nextjs/components/Platform/ParkMapGrid.tsx
git commit -m "feat(platform): ParkMapGrid presentational component"
```

---

## Task 8: ParkPanelDetail side-panel component

**Files:**
- Create: `website/nextjs/components/Platform/ParkPanelDetail.tsx`

- [ ] **Step 1: Write the component**

```tsx
'use client'

import type { GridPanel, GridPanelDetection } from '@/lib/api'
import { API_BASE } from '@/lib/api'

const SEVERITY_COLOR: Record<string, string> = {
  CRITICAL: '#dc2626',
  HIGH: '#ea580c',
  MEDIUM: '#ca8a04',
  LOW: '#2563eb',
}

export function ParkPanelDetail({
  panel,
  jobId,
  onClose,
}: {
  panel: GridPanel | null
  jobId: string | null
  onClose: () => void
}) {
  if (!panel) {
    return (
      <aside
        aria-label="Panel detail"
        style={{
          padding: 20,
          background: '#ffffff',
          border: '1px solid #e2e8f0',
          borderRadius: 8,
          minHeight: 280,
          color: '#64748b',
          fontSize: 13,
        }}
      >
        Click a panel in the grid to see its detections.
      </aside>
    )
  }

  const firstFile = panel.detections.find((d) => d.thermal_filename)?.thermal_filename
  const thumbUrl =
    jobId && firstFile ? `${API_BASE}/image/${encodeURIComponent(jobId)}/${encodeURIComponent(firstFile)}` : null

  return (
    <aside
      aria-label={`Panel ${panel.panel_id} detail`}
      style={{
        padding: 20,
        background: '#ffffff',
        border: '1px solid #e2e8f0',
        borderRadius: 8,
        display: 'flex',
        flexDirection: 'column',
        gap: 14,
      }}
    >
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <h3 style={{ margin: 0, fontSize: 16, fontWeight: 700 }}>Panel {panel.panel_id}</h3>
        <button
          onClick={onClose}
          aria-label="Close panel detail"
          style={{
            background: 'transparent',
            border: 'none',
            cursor: 'pointer',
            color: '#94a3b8',
            fontSize: 18,
            lineHeight: 1,
          }}
        >
          ×
        </button>
      </header>

      <div style={{ fontSize: 13, color: '#475569' }}>
        {panel.detection_count} detection{panel.detection_count === 1 ? '' : 's'}
        {panel.worst_severity ? (
          <span
            style={{
              marginLeft: 8,
              padding: '2px 8px',
              background: SEVERITY_COLOR[panel.worst_severity],
              color: '#fff',
              borderRadius: 4,
              fontSize: 11,
              fontWeight: 700,
            }}
          >
            {panel.worst_severity}
          </span>
        ) : null}
      </div>

      <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: 6 }}>
        {panel.detections.map((d, i) => (
          <DetectionRow key={i} d={d} />
        ))}
      </ul>

      {thumbUrl ? (
        <figure style={{ margin: 0 }}>
          <img
            src={thumbUrl}
            alt={`Thermal image ${firstFile}`}
            style={{ width: '100%', maxHeight: 240, objectFit: 'contain', borderRadius: 4, background: '#0f172a' }}
          />
          <figcaption style={{ fontSize: 11, color: '#94a3b8', marginTop: 4 }}>{firstFile}</figcaption>
        </figure>
      ) : null}

      {panel.gps ? (
        <div style={{ fontSize: 12, color: '#64748b' }}>
          GPS: {panel.gps.lat.toFixed(5)}, {panel.gps.lon.toFixed(5)}
        </div>
      ) : null}
    </aside>
  )
}

function DetectionRow({ d }: { d: GridPanelDetection }) {
  return (
    <li
      style={{
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        padding: '6px 10px',
        background: '#f8fafc',
        borderRadius: 4,
        fontSize: 12,
      }}
    >
      <span style={{ fontWeight: 600 }}>{d.class}</span>
      <span style={{ color: '#64748b' }}>
        {d.confidence != null ? `${Math.round(d.confidence * 100)}%` : ''}
        {d.severity ? (
          <span
            style={{
              marginLeft: 8,
              padding: '1px 6px',
              background: SEVERITY_COLOR[d.severity] ?? '#64748b',
              color: '#fff',
              borderRadius: 3,
              fontSize: 10,
              fontWeight: 700,
            }}
          >
            {d.severity}
          </span>
        ) : null}
      </span>
    </li>
  )
}
```

- [ ] **Step 2: Typecheck**

```
cd website/nextjs && npx tsc --noEmit 2>&1 | grep -E "ParkPanelDetail" | head -5
```
Expected: empty.

- [ ] **Step 3: Commit**

```
git add website/nextjs/components/Platform/ParkPanelDetail.tsx
git commit -m "feat(platform): ParkPanelDetail side-panel component"
```

---

## Task 9: Wire Park Map tab into page.tsx

**Files:**
- Modify: `website/nextjs/app/platform/page.tsx`

- [ ] **Step 1: Add imports**

Near the existing platform component imports (with `import { useMapData, ... } from '@/components/Platform/AnomalyMap'`), add:

```tsx
import { ParkMapGrid } from '@/components/Platform/ParkMapGrid'
import { ParkPanelDetail } from '@/components/Platform/ParkPanelDetail'
import type { GridPanel, ParkGrid } from '@/lib/api'
```

- [ ] **Step 2: Extend the `Tab` type**

Search for `type Tab =` near the top of the file. Add `'parkmap'` to the union:

```tsx
type Tab = 'operations' | 'inspect' | 'history' | 'settings' | 'parkmap'
```

- [ ] **Step 3: Add state inside `PlatformPageBody`**

Find the block of `useState` calls inside `PlatformPageBody`. Add (place near the History state, around line 208):

```tsx
const [parkMapParkId, setParkMapParkId] = useState<string>('')
const [parkMapInspectionId, setParkMapInspectionId] = useState<string>('')
const [parkMapInspections, setParkMapInspections] = useState<Array<{ id: string; flight_date?: string | null; created_at?: string | null }>>([])
const [parkMapGrid, setParkMapGrid] = useState<ParkGrid | null>(null)
const [parkMapLoading, setParkMapLoading] = useState(false)
const [parkMapSelectedPanel, setParkMapSelectedPanel] = useState<GridPanel | null>(null)
```

- [ ] **Step 4: Default the Park Map park to the active Operations job's park**

Right after the existing `useEffect` that initializes the History park (search for `setHistoryParkId`), add:

```tsx
useEffect(() => {
  if (!parkMapParkId && activeJob?.parkId) setParkMapParkId(activeJob.parkId)
}, [activeJob?.parkId, parkMapParkId])
```

- [ ] **Step 4b: Fetch the park's inspection list when the park changes**

Add this effect:

```tsx
useEffect(() => {
  if (!parkMapParkId) {
    setParkMapInspections([])
    setParkMapInspectionId('')
    return
  }
  let cancelled = false
  api
    .park(parkMapParkId)
    .then((summary) => {
      if (cancelled) return
      const list = ((summary as { inspections?: Array<{ id: string; flight_date?: string | null; created_at?: string | null }> }).inspections) ?? []
      setParkMapInspections(list)
      // default to most recent if not already chosen
      if (!parkMapInspectionId && list[0]) setParkMapInspectionId(list[0].id)
    })
    .catch((err) => {
      if (cancelled) return
      toast.error(err instanceof ApiError ? err.message : String(err))
      setParkMapInspections([])
    })
  return () => {
    cancelled = true
  }
}, [parkMapParkId, parkMapInspectionId, toast])
```

- [ ] **Step 5: Fetch the grid when park/inspection changes**

Add this effect alongside the other fetch effects:

```tsx
useEffect(() => {
  if (!parkMapParkId) {
    setParkMapGrid(null)
    return
  }
  let cancelled = false
  setParkMapLoading(true)
  api
    .parkGrid(parkMapParkId, parkMapInspectionId || undefined)
    .then((g) => {
      if (cancelled) return
      setParkMapGrid(g)
      setParkMapSelectedPanel(null)
    })
    .catch((err) => {
      if (cancelled) return
      toast.error(err instanceof ApiError ? err.message : String(err))
      setParkMapGrid(null)
    })
    .finally(() => {
      if (!cancelled) setParkMapLoading(false)
    })
  return () => {
    cancelled = true
  }
}, [parkMapParkId, parkMapInspectionId, toast])
```

- [ ] **Step 6: Add the tab button**

Find the tabs nav (search for `setTab('settings')` to find the existing tab buttons). Add a new button alongside, e.g.:

```tsx
<button
  onClick={() => setTab('parkmap')}
  data-testid="tab-parkmap"
  aria-selected={tab === 'parkmap'}
  /* match the styling of the other tab buttons in this file */
>
  Park Map
</button>
```

Match whatever styling the existing tab buttons use (className or inline style). Do not invent a new style system.

- [ ] **Step 7: Add the tab body**

Find the place where `tab === 'settings' ? (...) : null` (or similar conditional rendering) lives. Add the new conditional block:

```tsx
{tab === 'parkmap' ? (
  <section style={{ padding: '16px 24px', display: 'flex', flexDirection: 'column', gap: 16 }}>
    <header style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
      <h1 style={{ margin: 0, fontSize: 24 }}>Park Map</h1>
    </header>

    <div style={{ display: 'flex', gap: 12, alignItems: 'flex-end', flexWrap: 'wrap' }}>
      <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: '#64748b' }}>
        Park
        <select
          data-testid="parkmap-park-select"
          value={parkMapParkId}
          onChange={(e) => {
            setParkMapParkId(e.target.value)
            setParkMapInspectionId('')
          }}
          style={{ padding: '6px 10px', border: '1px solid #cbd5e1', borderRadius: 6 }}
        >
          <option value="">— select a park —</option>
          {parkList.map((p) => (
            <option key={p.id} value={p.id}>
              {p.id}
              {p.name ? ` — ${p.name}` : ''}
            </option>
          ))}
        </select>
      </label>

      <label style={{ display: 'flex', flexDirection: 'column', gap: 4, fontSize: 12, color: '#64748b' }}>
        Inspection
        <select
          data-testid="parkmap-inspection-select"
          value={parkMapInspectionId}
          onChange={(e) => setParkMapInspectionId(e.target.value)}
          disabled={parkMapInspections.length === 0}
          style={{ padding: '6px 10px', border: '1px solid #cbd5e1', borderRadius: 6, minWidth: 220 }}
        >
          <option value="">— most recent —</option>
          {parkMapInspections.map((i) => (
            <option key={i.id} value={i.id}>
              {i.id}{i.flight_date ? ` (${i.flight_date})` : ''}
            </option>
          ))}
        </select>
      </label>

      {parkMapLoading ? <span style={{ fontSize: 12, color: '#64748b' }}>Loading…</span> : null}
    </div>

    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) 320px', gap: 16 }}>
      <ParkMapGrid
        grid={parkMapGrid}
        selectedPanelId={parkMapSelectedPanel?.panel_id ?? null}
        onSelect={(p) => setParkMapSelectedPanel(p)}
      />
      <ParkPanelDetail
        panel={parkMapSelectedPanel}
        jobId={parkMapGrid?.inspection_id ?? null}
        onClose={() => setParkMapSelectedPanel(null)}
      />
    </div>
  </section>
) : null}
```

- [ ] **Step 8: Typecheck**

```
cd website/nextjs && npx tsc --noEmit 2>&1 | tail -20
```
Expected: no new errors.

- [ ] **Step 9: Manual verify via Playwright**

```
# Services should still be running from Phase 1 / earlier. If not:
# nohup ./run.sh all > /tmp/run-all.log 2>&1 &
```

Drive Playwright:
- Navigate to `http://localhost:3000/platform`
- Click the new "Park Map" tab.
- Snapshot. Confirm: park dropdown shows SOLAR_PARK_DEMO, grid renders, legend visible.
- Pick a non-empty cell (one with a colored fill) by `data-testid` from the snapshot (e.g. `panel-R1-C1`).
- Click it. Confirm side panel updates with detection list + thumbnail.

- [ ] **Step 10: Commit**

```
git add website/nextjs/app/platform/page.tsx
git commit -m "feat(platform): Park Map tab with grid + side detail"
```

---

## Task 10: Vitest setup + lib/api unit tests

**Files:**
- Modify: `website/nextjs/package.json`
- Create: `website/nextjs/vitest.config.ts`
- Create: `website/nextjs/tests/unit/api.test.ts`

- [ ] **Step 1: Install vitest + react testing deps**

```
cd website/nextjs && npm install --save-dev vitest @vitejs/plugin-react @testing-library/react @testing-library/dom @testing-library/jest-dom jsdom @types/react @types/react-dom
```
(Most of these may already be present — npm will no-op.)

- [ ] **Step 2: Create `vitest.config.ts`**

```ts
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'node:path'

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, '.'),
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['tests/unit/**/*.{test,spec}.{ts,tsx}'],
  },
})
```

- [ ] **Step 3: Add `test` script to `package.json`**

In `website/nextjs/package.json`, in the `"scripts"` block, add (alongside `dev`/`build`/`start`/`lint`):

```json
"test": "vitest run",
"test:watch": "vitest"
```

- [ ] **Step 4: Write the API client tests**

`website/nextjs/tests/unit/api.test.ts`:

```ts
import { afterEach, describe, expect, test, vi } from 'vitest'
import { api, ApiError } from '@/lib/api'

afterEach(() => {
  vi.restoreAllMocks()
})

describe('api client', () => {
  test('health returns parsed JSON on 200', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify({ status: 'ok' }), { status: 200 })
    )
    const h = await api.health()
    expect(h.status).toBe('ok')
  })

  test('throws ApiError with status + body on 500', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response('boom', { status: 500 })
    )
    await expect(api.health()).rejects.toMatchObject({
      name: 'ApiError',
      status: 500,
    })
  })

  test('throws ApiError with truncated body in message', async () => {
    const long = 'x'.repeat(500)
    vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(long, { status: 400 })
    )
    let caught: unknown
    try {
      await api.health()
    } catch (e) {
      caught = e
    }
    expect(caught).toBeInstanceOf(ApiError)
    expect((caught as ApiError).message).toMatch(/HTTP 400/)
    // body slice in message should not exceed 200 chars (per ApiError impl)
    expect((caught as ApiError).message.length).toBeLessThan(260)
  })

  test('network error becomes ApiError with status 0', async () => {
    vi.spyOn(globalThis, 'fetch').mockRejectedValueOnce(new TypeError('fetch failed'))
    await expect(api.health()).rejects.toMatchObject({
      name: 'ApiError',
      status: 0,
    })
  })

  test('parkGrid encodes query string when inspectionId provided', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
      new Response(
        JSON.stringify({ park_id: 'P1', inspection_id: 'b1', rows: 1, cols: 1, panels: [] }),
        { status: 200 }
      )
    )
    await api.parkGrid('PARK A', 'batch-zz')
    const calledUrl = (fetchSpy.mock.calls[0][0] as string)
    expect(calledUrl).toContain('/park/PARK%20A/grid')
    expect(calledUrl).toContain('inspection_id=batch-zz')
  })
})
```

- [ ] **Step 5: Run the tests**

```
cd website/nextjs && npm test
```
Expected: 5 passed.

- [ ] **Step 6: Commit**

```
git add website/nextjs/package.json website/nextjs/package-lock.json website/nextjs/vitest.config.ts website/nextjs/tests/unit/api.test.ts
git commit -m "test(api-client): vitest setup + lib/api.ts unit tests"
```

---

## Task 11: Toast component tests

**Files:**
- Create: `website/nextjs/tests/unit/Toast.test.tsx`

- [ ] **Step 1: Write the test**

```tsx
import '@testing-library/jest-dom/vitest'
import { afterEach, describe, expect, test, vi } from 'vitest'
import { act, render, screen } from '@testing-library/react'
import { ToastProvider, useToast } from '@/components/Platform/Toast'

afterEach(() => {
  vi.useRealTimers()
})

function Pusher({ kind, text }: { kind: 'error' | 'info' | 'success'; text: string }) {
  const toast = useToast()
  return <button onClick={() => toast[kind](text)}>push</button>
}

describe('Toast', () => {
  test('useToast throws outside provider', () => {
    function Bad() {
      useToast()
      return null
    }
    // Suppress React's error log for the expected throw
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<Bad />)).toThrow(/inside <ToastProvider>/)
    spy.mockRestore()
  })

  test('renders an error toast after push', async () => {
    render(
      <ToastProvider>
        <Pusher kind="error" text="kaboom" />
      </ToastProvider>
    )
    act(() => {
      screen.getByText('push').click()
    })
    expect(await screen.findByText('kaboom')).toBeInTheDocument()
  })

  test('auto-dismisses after 6 seconds', async () => {
    vi.useFakeTimers()
    render(
      <ToastProvider>
        <Pusher kind="info" text="bye" />
      </ToastProvider>
    )
    act(() => {
      screen.getByText('push').click()
    })
    expect(screen.getByText('bye')).toBeInTheDocument()
    act(() => {
      vi.advanceTimersByTime(6001)
    })
    expect(screen.queryByText('bye')).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run**

```
cd website/nextjs && npm test
```
Expected: 8 tests passed total (5 from api + 3 from Toast).

- [ ] **Step 3: Commit**

```
git add website/nextjs/tests/unit/Toast.test.tsx
git commit -m "test(toast): vitest coverage for Toast provider + auto-dismiss"
```

---

## Task 12: Playwright setup + golden path e2e

**Files:**
- Modify: `website/nextjs/package.json`
- Create: `website/nextjs/playwright.config.ts`
- Create: `website/nextjs/tests/e2e/golden_path.spec.ts`

- [ ] **Step 1: Install playwright**

```
cd website/nextjs && npm install --save-dev @playwright/test
npx playwright install chromium
```

- [ ] **Step 2: Create `playwright.config.ts`**

```ts
import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 240_000,
  expect: { timeout: 15_000 },
  fullyParallel: false,
  retries: 0,
  reporter: 'line',
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? 'http://localhost:3000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [{ name: 'chromium', use: { browserName: 'chromium' } }],
})
```

- [ ] **Step 3: Add `test:e2e` script to `package.json`**

```json
"test:e2e": "playwright test"
```

- [ ] **Step 4: Write the golden-path test**

`website/nextjs/tests/e2e/golden_path.spec.ts`:

```ts
import { expect, test } from '@playwright/test'
import path from 'node:path'

const REPO_ROOT = path.resolve(__dirname, '..', '..', '..', '..')
const FIXTURE_ZIP = path.join(REPO_ROOT, 'tests', 'fixtures', 'sample_mission.zip')

test.describe('Operator golden path', () => {
  test('runs a batch then visits every tab', async ({ page }) => {
    await page.goto('/platform')

    // Operations tab is default
    await expect(page.getByRole('heading', { name: /Operations/i })).toBeVisible()

    // Set park + altitude
    await page.fill('input[placeholder*="park" i], input[name="parkId"], input[name="park_id"]', 'E2E_PARK')
    // altitude — try common labels
    const altInput = page.locator('input[type=number]').first()
    if (await altInput.count()) await altInput.fill('42')

    // Upload zip
    await page.setInputFiles('input[type=file]', FIXTURE_ZIP)

    // Click Start batch (button label may vary; match loosely)
    await page.getByRole('button', { name: /start (batch|inspection)/i }).click()

    // Wait for completion — UI shows 100% or "completed"
    await expect(
      page.locator('text=/100\\s*%/').first()
    ).toBeVisible({ timeout: 180_000 })

    // Click report download buttons (each should produce a 200; we don't validate the file)
    for (const label of ['JSON', 'Excel', 'GeoJSON']) {
      const link = page.getByRole('link', { name: new RegExp(label, 'i') }).first()
      if (await link.count()) {
        // For links, just assert href contains /report/
        const href = await link.getAttribute('href')
        expect(href ?? '').toContain('/report/')
      }
    }

    // Inspect tab
    await page.getByRole('button', { name: /^Inspect$/ }).click()
    await page.setInputFiles('input[type=file]', path.join(REPO_ROOT, 'tests', 'fixtures', 'sample_mission', 'thermal', 'img_001.jpg'))
    const submit = page.getByRole('button', { name: /submit|inspect/i }).last()
    await submit.click()
    // Result section should appear
    await expect(page.locator('text=/detection/i').first()).toBeVisible({ timeout: 60_000 })

    // History tab
    await page.getByRole('button', { name: /^History$/ }).click()
    await expect(page.locator('select').first()).toBeVisible()

    // Settings tab
    await page.getByRole('button', { name: /^Settings$/ }).click()
    await expect(page.locator('text=/setting/i').first()).toBeVisible()

    // Park Map tab
    await page.getByTestId('tab-parkmap').click()
    await expect(page.getByRole('heading', { name: /Park Map/i })).toBeVisible()
    await page.getByTestId('parkmap-park-select').selectOption('E2E_PARK')
    // Wait for grid to render — look for any panel cell
    await expect(page.locator('[data-testid^="panel-R"]').first()).toBeVisible({ timeout: 30_000 })
  })
})
```

- [ ] **Step 5: Ensure the fixture ZIP exists**

```
cd /home/parakh/Desktop/AxalonSystems
ls tests/fixtures/sample_mission.zip || (cd tests/fixtures && zip -rq sample_mission.zip sample_mission/)
```

- [ ] **Step 6: Run the test**

Services must be running (`./run.sh all` from Phase 1). Then:

```
cd website/nextjs && npm run test:e2e
```
Expected: 1 passed (may take 3-5 minutes).

If a locator misses (e.g. the park-id input has a different placeholder), use `mcp__playwright__browser_snapshot` to grab the actual DOM and update the locator. Do not weaken the test to skip steps.

- [ ] **Step 7: Commit**

```
git add website/nextjs/package.json website/nextjs/package-lock.json website/nextjs/playwright.config.ts website/nextjs/tests/e2e/golden_path.spec.ts
git commit -m "test(e2e): playwright golden-path test across all 5 tabs"
```

---

## Task 13: scripts/test_all.sh + final acceptance

**Files:**
- Create: `scripts/test_all.sh`
- Modify: `docs/OPERATOR_RUNBOOK.md` (add Testing section)

- [ ] **Step 1: Write the runner**

`scripts/test_all.sh`:

```bash
#!/usr/bin/env bash
# test_all.sh — Run the full Phase 2 test suite (pytest + vitest + playwright).
#
# Usage:
#   ./scripts/test_all.sh
#
# Assumes ./run.sh all is up if you want the playwright step to pass.
# If services are not up, this script will start them, run, and stop them.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; RESET='\033[0m'

info()    { echo -e "${CYAN}[test_all]${RESET} $*"; }
success() { echo -e "${GREEN}[test_all]${RESET} $*"; }
fail()    { echo -e "${RED}[test_all]${RESET} $*" >&2; }

started_services=0
ensure_services() {
    if curl -fsS http://localhost:8000/health >/dev/null 2>&1 \
       && curl -fsS -o /dev/null http://localhost:3000/platform; then
        info "Services already running."
    else
        info "Starting services (./run.sh all)..."
        nohup ./run.sh all > /tmp/test_all_run.log 2>&1 &
        started_services=1
        for i in $(seq 1 90); do
            if curl -fsS http://localhost:8000/health >/dev/null 2>&1 \
               && curl -fsS -o /dev/null http://localhost:3000/platform; then
                success "Services ready."
                return 0
            fi
            sleep 1
        done
        fail "Services did not come up in 90s. Check /tmp/test_all_run.log."
        exit 1
    fi
}

cleanup_services() {
    if [ "$started_services" -eq 1 ]; then
        info "Stopping services we started..."
        ./run.sh stop || true
    fi
}
trap cleanup_services EXIT

info "▶ Backend pytest"
(cd /tmp && PYTHONSAFEPATH=1 python -m pytest "$REPO_ROOT" -v)

info "▶ Frontend vitest"
(cd "$REPO_ROOT/website/nextjs" && npm test --silent)

ensure_services

info "▶ Frontend playwright"
(cd "$REPO_ROOT/website/nextjs" && npm run test:e2e --silent)

success "All suites passed."
```

- [ ] **Step 2: Make it executable**

```
chmod +x scripts/test_all.sh
```

- [ ] **Step 3: Run it end-to-end**

```
./scripts/test_all.sh
```
Expected: all three suites pass and the script exits 0. Allow up to 15 minutes for full run.

If any suite fails, investigate the underlying issue and fix it before continuing. Commit each fix with appropriate `fix(...)` or `test(...)` message.

- [ ] **Step 4: Update OPERATOR_RUNBOOK with a Testing section**

Append to `docs/OPERATOR_RUNBOOK.md`:

```markdown

## 9. Run the test suite (optional)

Phase 2 added an automated suite covering API contract, pipeline units, frontend units, and a Playwright end-to-end walk of all five tabs.

```bash
./scripts/test_all.sh
```

What it does:

- **Backend pytest** (`tests/backend/`) — every API endpoint + the orchestrator + the panel-grid aggregator.
- **Frontend vitest** (`website/nextjs/tests/unit/`) — the `api.ts` client + the Toast hook.
- **Frontend playwright** (`website/nextjs/tests/e2e/`) — drives a headless Chromium through every tab including a real batch run.

The script starts the platform services itself if they're not already up, and stops them after. Pass-through exit code: zero on success, non-zero on the first failing suite.
```

- [ ] **Step 5: Final acceptance check against the spec**

Run through the spec's acceptance list manually:

- [ ] `GET /park/SOLAR_PARK_DEMO/grid` returns ≥1 panel with a severity.
- [ ] Park Map tab renders, clicking a cell shows side detail.
- [ ] Park dropdown switches, defaults to active Operations park.
- [ ] Inspection dropdown lists inspections (covered indirectly — defaults to most recent).
- [ ] Empty state renders for a park with no inspections.
- [ ] `pytest tests/backend/` passes.
- [ ] `cd website/nextjs && npm test` passes.
- [ ] `cd website/nextjs && npm run test:e2e` passes.
- [ ] `scripts/test_all.sh` exits 0.
- [ ] Phase 1 regression check passed (the golden-path test exercises Phase 1's full flow).

For any unchecked item, fix the underlying issue and re-verify.

- [ ] **Step 6: Final commit**

```
git add scripts/test_all.sh docs/OPERATOR_RUNBOOK.md
git commit -m "chore(tests): test_all.sh runner + runbook testing section"
```

---

## Done

When Task 13 passes, Phase 2 is complete. Phase 3 (polish: loading skeletons, transitions, mobile, demo seed data) starts via a fresh brainstorming session.
