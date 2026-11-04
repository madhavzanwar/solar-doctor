"""Corrections appear in the JSON report for an inspect job."""
import json

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def engine(tmp_path):
    from axalon.db.session import get_engine, init_db

    init_db(f"sqlite:///{tmp_path / 'report_corrections.db'}")
    return get_engine()


@pytest.fixture
def client(engine):
    from axalon.api.app import app

    with TestClient(app) as c:
        yield c


def test_json_report_includes_corrections(client):
    from axalon.db.models import Correction, Job
    from axalon.db.session import get_engine, session_scope

    job_id = "test-inspect-001"
    with session_scope(get_engine()) as s:
        s.add(Job(id=job_id, state="succeeded", park_id="unknown", total=1, processed=1))
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
