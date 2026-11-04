"""Tests for the Agent Console router (platform/api/agents_router.py).

These endpoints read/write the real docs/plans/plan-state.json and logs/
directories in production. The `agents_client` fixture redirects every
module-level path to a temp dir so tests never mutate the repo's plan state.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


SYNTHETIC_PLAN = {
    "auto_run": False,
    "current_session_id": None,
    "tasks": [
        {
            "id": "t1", "name": "Task One", "priority": "P0", "effort": "Small",
            "file": "t1.md", "status": "pending", "session_id": None,
            "started_at": None, "completed_at": None,
        },
        {
            "id": "t2", "name": "Task Two", "priority": "P1", "effort": "Medium",
            "file": "t2.md", "status": "done", "session_id": None,
            "started_at": None, "completed_at": "2026-01-01T00:00:00",
        },
    ],
}


@pytest.fixture
def agents_client(temp_db, tmp_path, monkeypatch) -> TestClient:
    """TestClient with agents_router paths redirected to a temp sandbox."""
    import axalon.api.agents_router as ar

    plans_dir = tmp_path / "plans"
    plans_dir.mkdir()
    plan_file = plans_dir / "plan-state.json"
    plan_file.write_text(json.dumps(SYNTHETIC_PLAN))

    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    pipelines_dir = tmp_path / "pipelines"
    pipelines_dir.mkdir()

    monkeypatch.setattr(ar, "PLANS_DIR", plans_dir)
    monkeypatch.setattr(ar, "PLAN_STATE", plan_file)
    monkeypatch.setattr(ar, "LOGS_DIR", logs_dir)
    monkeypatch.setattr(ar, "PIPELINES_DIR", pipelines_dir)
    # Neutralise the infinite background watcher and real subprocess spawning so
    # tests never launch a real agent or block the TestClient portal thread.
    monkeypatch.setattr(ar, "_ensure_watcher", lambda *a, **k: None)
    monkeypatch.setattr(ar, "_spawn_plan_task", lambda task, model="x": "sess-fake-001")

    from axalon.api.app import app
    return TestClient(app)


# ── Plan board ──────────────────────────────────────────────────────────────

def test_get_plan_returns_all_tasks(agents_client):
    # Act
    resp = agents_client.get("/agents/plan")

    # Assert
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["tasks"]) == 2
    assert {t["id"] for t in body["tasks"]} == {"t1", "t2"}


def test_toggle_auto_flips_then_restores(agents_client):
    # Arrange — starts False
    first = agents_client.post("/agents/plan/toggle-auto").json()
    second = agents_client.post("/agents/plan/toggle-auto").json()

    # Assert
    assert first["auto_run"] is True
    assert second["auto_run"] is False


def test_mark_done_sets_status_and_timestamp(agents_client):
    # Act
    resp = agents_client.post("/agents/plan/t1/done")

    # Assert
    assert resp.status_code == 200
    task = resp.json()
    assert task["status"] == "done"
    assert task["completed_at"] is not None


def test_reset_task_returns_to_pending(agents_client):
    # Act — t2 is done; reset it
    resp = agents_client.post("/agents/plan/t2/reset")

    # Assert
    assert resp.status_code == 200
    task = resp.json()
    assert task["status"] == "pending"
    assert task["completed_at"] is None
    assert task["session_id"] is None


def test_mark_done_unknown_task_returns_404(agents_client):
    assert agents_client.post("/agents/plan/nope/done").status_code == 404


def test_reset_unknown_task_returns_404(agents_client):
    assert agents_client.post("/agents/plan/nope/reset").status_code == 404


def test_plan_write_persists_across_requests(agents_client):
    # Arrange
    agents_client.post("/agents/plan/t1/done")

    # Act
    body = agents_client.get("/agents/plan").json()

    # Assert — the done status survived the write
    t1 = next(t for t in body["tasks"] if t["id"] == "t1")
    assert t1["status"] == "done"


# ── Sessions / types / models ───────────────────────────────────────────────

def test_list_sessions_empty_when_no_logs(agents_client):
    resp = agents_client.get("/agents/sessions")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_agent_types_returns_a_list(agents_client):
    resp = agents_client.get("/agents/types")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_list_models_reports_ollama_status(agents_client):
    # Ollama is not running in CI — endpoint must degrade gracefully.
    resp = agents_client.get("/agents/models")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ollama"] in ("online", "offline")
    assert isinstance(body["models"], list)


def test_stream_log_invalid_session_id_400(agents_client):
    assert agents_client.get("/agents/sessions/bad$id/log").status_code == 400


def test_stream_log_missing_session_404(agents_client):
    assert agents_client.get("/agents/sessions/missing123/log").status_code == 404


# ── Pipeline ────────────────────────────────────────────────────────────────

def test_phase_definitions_returns_six_phases(agents_client):
    resp = agents_client.get("/agents/pipeline/phases/definitions")
    assert resp.status_code == 200
    phases = resp.json()
    assert len(phases) == 6
    assert {p["id"] for p in phases} >= {"think", "plan", "implement", "review", "test", "refine"}


def test_list_pipelines_empty_initially(agents_client):
    resp = agents_client.get("/agents/pipelines")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_pipeline_invalid_id_400(agents_client):
    assert agents_client.get("/agents/pipeline/bad$id").status_code == 400


def test_get_pipeline_missing_404(agents_client):
    assert agents_client.get("/agents/pipeline/nope123").status_code == 404


def test_list_pipelines_reads_existing_files(agents_client, tmp_path):
    # Arrange — drop a synthetic pipeline file into the sandbox PIPELINES_DIR
    import axalon.api.agents_router as ar
    pl = {"id": "pl-1", "prompt": "demo", "status": "done", "phases": []}
    (ar.PIPELINES_DIR / "pl-1.json").write_text(json.dumps(pl))

    # Act
    resp = agents_client.get("/agents/pipelines")

    # Assert
    assert resp.status_code == 200
    ids = [p["id"] for p in resp.json()]
    assert "pl-1" in ids


# ── Sessions kill + run-next (subprocess mocked) ─────────────────────────────

def test_kill_session_invalid_id_400(agents_client):
    assert agents_client.delete("/agents/sessions/bad$id").status_code == 400


def test_kill_session_missing_404(agents_client):
    assert agents_client.delete("/agents/sessions/ghost123").status_code == 404


def test_run_next_spawns_next_pending_task(agents_client):
    # _spawn_plan_task is mocked to return a fake session id.
    resp = agents_client.post("/agents/plan/run-next", json={"model": "qwen2.5-coder:7b"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["task_id"] == "t1"          # t1 is the only pending task
    assert body["session_id"] == "sess-fake-001"
