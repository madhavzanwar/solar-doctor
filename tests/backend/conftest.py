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
    if hasattr(_session, "_SessionLocal"):
        _session._SessionLocal = None
    yield db_path


@pytest.fixture(autouse=True)
def _default_auth_mode(monkeypatch):
    """Tests default to the historical keyless behaviour unless they opt in, so
    a developer shell with AXALON_AUTH_MODE exported cannot change results."""
    monkeypatch.delenv("AXALON_AUTH_MODE", raising=False)


@pytest.fixture
def client(temp_db) -> TestClient:
    """FastAPI TestClient bound to a fresh in-test DB."""
    # Import inside the fixture so AXALON_DB_URL is set first.
    from axalon.api.app import app
    return TestClient(app)


@pytest.fixture
def db_session(temp_db):
    """SQLAlchemy session bound to the temp test DB."""
    from axalon.db.session import get_session
    session = get_session()
    yield session
    session.close()


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


# ── NodeODM fake (no network) ────────────────────────────────────────────────
def _load_fake_nodeodm():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "fake_nodeodm", Path(__file__).with_name("fake_nodeodm.py"),
    )
    module = importlib.util.module_from_spec(spec)
    import sys
    sys.modules["fake_nodeodm"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def odm_fakes():
    """The fake_nodeodm module: FakeNodeODM, FakeResponse, connection_error."""
    return _load_fake_nodeodm()


# ── Users-mode auth fixtures ─────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _fast_isolated_auth(monkeypatch):
    """Keep auth tests fast and independent.

    Production hashes user passwords with 600k PBKDF2 rounds; tests only need
    the format, not the cost. The login limiter is process-global, so each test
    starts from a clean slate.
    """
    from axalon.core import auth as _auth
    monkeypatch.setattr(_auth, "USER_PBKDF2_ITERATIONS", 1_000)
    _auth.login_limiter.reset()
    yield
    _auth.login_limiter.reset()


@pytest.fixture
def users_mode(monkeypatch):
    """Switch the API into AXALON_AUTH_MODE=users for one test."""
    monkeypatch.setenv("AXALON_AUTH_MODE", "users")
    monkeypatch.delenv("AXALON_API_KEY", raising=False)
    return "users"


PASSWORD = "correct-horse-battery"


@pytest.fixture
def make_user(db_session):
    """Factory: create a user directly in the DB and return its id."""
    from axalon.core.auth import create_user

    def _make(email: str, role: str, password: str = PASSWORD, project_ids=()) -> int:
        user = create_user(
            db_session, email=email, password=password, role=role, project_ids=project_ids,
        )
        return user.id
    return _make


@pytest.fixture
def login(client):
    """Log in through the API and return ready-to-use auth headers."""
    def _login(email: str, password: str = PASSWORD) -> dict:
        r = client.post("/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['token']}"}
    return _login


@pytest.fixture
def two_projects(db_session):
    """Two projects with one park each plus an unassigned park. Every park gets
    an inspection, job, fault, comment, correction and mission so each scoped
    endpoint has something that could leak."""
    from axalon.db.models import (
        Correction, FaultComment, Inspection, Job, Mission, PanelFault, Park, Project,
    )

    p1, p2 = Project(name="North"), Project(name="South")
    db_session.add_all([p1, p2])
    db_session.commit()
    ids: dict = {"p1": p1.id, "p2": p2.id}
    for park_id, project_id, tag in (
        ("PARK_A", p1.id, "a"), ("PARK_B", p2.id, "b"), ("PARK_X", None, "x"),
    ):
        db_session.add(Park(id=park_id, name=park_id, project_id=project_id))
        db_session.commit()
        job_id = f"batch-{tag}000001"
        db_session.add(Inspection(id=job_id, park_id=park_id, flight_date="2026-01-01"))
        db_session.add(Job(id=job_id, park_id=park_id, state="succeeded", total=1, processed=1))
        fault = PanelFault(park_id=park_id, panel_id="R1-C1", class_="cell", severity="MEDIUM")
        mission = Mission(name=f"mission-{tag}", park_id=park_id)
        db_session.add_all([fault, mission])
        db_session.commit()
        db_session.add(FaultComment(fault_id=fault.id, body="seen"))
        db_session.add(Correction(job_id=job_id, class_="cell", bbox_norm="[0,0,1,1]"))
        db_session.commit()
        ids[f"job_{tag}"] = job_id
        ids[f"fault_{tag}"] = fault.id
        ids[f"mission_{tag}"] = mission.id
    return ids
