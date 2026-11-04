import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text


@pytest.fixture
def engine(tmp_path):
    from axalon.db.session import get_engine, init_db

    init_db(f"sqlite:///{tmp_path / 'corrections.db'}")
    return get_engine()


@pytest.fixture
def client(engine):
    from axalon.api.app import app

    with TestClient(app) as c:
        yield c


def test_corrections_table_exists(engine):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='corrections'")
        ).fetchone()
    assert row is not None, "corrections table must exist after init_db"


def test_list_corrections_empty(client):
    r = client.get("/corrections/job-abc")
    assert r.status_code == 200
    assert r.json() == []


def test_create_correction(client):
    payload = {
        "class_": "cell",
        "class_id": 0,
        "severity": "MEDIUM",
        "bbox_norm": [0.1, 0.2, 0.4, 0.5],
    }
    r = client.post("/corrections/job-abc", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["id"] > 0
    assert body["class"] == "cell"
    assert body["job_id"] == "job-abc"
    assert body["bbox_norm"] == [0.1, 0.2, 0.4, 0.5]


def test_delete_correction(client):
    payload = {
        "class_": "module",
        "class_id": 2,
        "severity": "MEDIUM",
        "bbox_norm": [0.0, 0.0, 0.5, 0.5],
    }
    created_id = client.post("/corrections/job-del", json=payload).json()["id"]
    r = client.delete(f"/corrections/job-del/{created_id}")
    assert r.status_code == 204
    assert client.get("/corrections/job-del").json() == []


def test_invalid_job_id_rejected(client):
    r = client.get("/corrections/%2E%2E/etc/passwd")
    assert r.status_code == 400
