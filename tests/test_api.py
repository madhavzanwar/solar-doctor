"""Tests for FastAPI endpoints."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch, tmp_path):
    """FastAPI TestClient bound to a fresh temp SQLite DB.

    Jobs and parks are persisted in the DB (no in-memory job dict any more),
    so each test gets its own database file via AXALON_DB_URL.
    """
    monkeypatch.setenv("AXALON_DB_URL", f"sqlite:///{tmp_path / 'test_api.db'}")
    monkeypatch.delenv("AXALON_AUTH_MODE", raising=False)
    from axalon.db import session as _session
    monkeypatch.setattr(_session, "_engine", None, raising=False)
    monkeypatch.setattr(_session, "_SessionLocal", None, raising=False)

    from axalon.api.app import app
    with TestClient(app) as test_client:
        yield test_client


def _completed_job(job_id: str) -> None:
    from axalon.api.support.jobs import _create_job, _update_job
    _create_job(job_id, park_id="TEST_PARK")
    _update_job(job_id, state="succeeded")


def test_health_ok(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "model" in body
    assert "weights" in body
    assert body["db"] == "ok"


def test_status_unknown_job(client):
    resp = client.get("/status/no-such-job")
    assert resp.status_code == 404


def test_report_unknown_job(client):
    resp = client.get("/report/no-such-job")
    assert resp.status_code == 404


def test_report_pdf_download(client, tmp_path, monkeypatch):
    import axalon.api.routers.inspection as inspection_router
    monkeypatch.setattr(inspection_router, "OUTPUT_DIR", tmp_path)
    job_id = "batch-testpdf"
    report_dir = tmp_path / job_id
    report_dir.mkdir(parents=True)
    pdf_path = report_dir / "inspection_report.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 test")
    _completed_job(job_id)

    resp = client.get(f"/report/{job_id}?format=pdf")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("application/pdf")
    assert resp.content == b"%PDF-1.4 test"


def test_report_rejects_unknown_format(client):
    job_id = "batch-knownjob"
    _completed_job(job_id)
    resp = client.get(f"/report/{job_id}?format=csv")
    assert resp.status_code == 400


def test_parks_returns_empty_list(client):
    """GET /parks returns empty list on fresh in-memory DB."""
    resp = client.get("/parks")
    assert resp.status_code == 200
    body = resp.json()
    assert body["parks"] == []
    assert body["total"] == 0


def test_park_not_found(client):
    resp = client.get("/park/NONEXISTENT_PARK_XYZ")
    assert resp.status_code == 404
