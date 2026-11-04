# tests/backend/test_fault_comments.py
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(temp_db):
    from axalon.api.app import app
    return TestClient(app)


@pytest.fixture
def existing_fault(db_session):
    from axalon.db.models import Park, PanelFault, FAULT_OPEN
    park = Park(id="PARK_CMT", name="Comment Park")
    db_session.add(park)
    db_session.flush()
    fault = PanelFault(
        park_id="PARK_CMT",
        panel_id="R1-C1",
        class_="bypass-diode",
        class_id=4,
        severity="CRITICAL",
        status=FAULT_OPEN,
    )
    db_session.add(fault)
    db_session.commit()
    return fault.id


def test_create_comment(client, existing_fault):
    resp = client.post(f"/faults/{existing_fault}/comments", json={
        "author": "pilot",
        "body": "Bypass diode failure confirmed from thermal image",
    })
    assert resp.status_code == 201
    data = resp.json()
    assert data["fault_id"] == existing_fault
    assert data["author"] == "pilot"
    assert data["body"] == "Bypass diode failure confirmed from thermal image"
    assert "id" in data
    assert "created_at" in data


def test_create_comment_requires_body(client, existing_fault):
    resp = client.post(f"/faults/{existing_fault}/comments", json={"author": "pilot"})
    assert resp.status_code == 400


def test_create_comment_invalid_fault(client):
    resp = client.post("/faults/99999/comments", json={"body": "test"})
    assert resp.status_code == 404


def test_list_comments_chronological(client, existing_fault):
    for body in ["First note", "Second note", "Third note"]:
        client.post(f"/faults/{existing_fault}/comments", json={"body": body})
    resp = client.get(f"/faults/{existing_fault}/comments")
    assert resp.status_code == 200
    comments = resp.json()
    assert len(comments) == 3
    assert comments[0]["body"] == "First note"
    assert comments[2]["body"] == "Third note"


def test_list_comments_empty(client, existing_fault):
    resp = client.get(f"/faults/{existing_fault}/comments")
    assert resp.status_code == 200
    assert resp.json() == []


def test_fault_list_includes_comment_count(client, existing_fault):
    client.post(f"/faults/{existing_fault}/comments", json={"body": "note 1"})
    client.post(f"/faults/{existing_fault}/comments", json={"body": "note 2"})
    resp = client.get("/parks/PARK_CMT/faults")
    assert resp.status_code == 200
    fault = resp.json()["faults"][0]
    assert fault["comment_count"] == 2
