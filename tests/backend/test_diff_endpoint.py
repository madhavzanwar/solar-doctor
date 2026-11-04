"""Integration tests for GET /parks/{park}/inspections/{a}/diff/{b}.

Seeds inspections via the real in-memory SQLite session, then hits the endpoint
through the FastAPI TestClient.
"""
from __future__ import annotations

import pytest

from axalon.db.models import Detection as DbDetection, Inspection, Park


@pytest.fixture
def seed_inspections(db_session):
    """Return a helper that seeds a park + inspection with given detections."""
    def _seed(park_id: str, inspection_id: str, detections: list[tuple[str, str]]):
        if db_session.query(Park).filter_by(id=park_id).first() is None:
            db_session.add(Park(id=park_id, name=park_id))
            db_session.commit()
        db_session.add(Inspection(id=inspection_id, park_id=park_id))
        db_session.commit()
        for panel_id, cls in detections:
            db_session.add(DbDetection(
                inspection_id=inspection_id, panel_id=panel_id,
                class_=cls, severity="HIGH", confidence=0.8,
            ))
        db_session.commit()
    return _seed


def test_diff_identical_inspections_returns_empty_new_and_resolved(client, seed_inspections):
    # Arrange — two inspections with the same single fault
    park = "PARK_D1"
    seed_inspections(park, "insp-a", [("R1-C1", "hot-spot-high")])
    seed_inspections(park, "insp-b", [("R1-C1", "hot-spot-high")])

    # Act
    r = client.get(f"/parks/{park}/inspections/insp-a/diff/insp-b")

    # Assert
    assert r.status_code == 200
    body = r.json()
    assert body["counts"]["new"] == 0
    assert body["counts"]["resolved"] == 0
    assert body["counts"]["recurring"] == 1


def test_diff_new_fault_appears_in_new(client, seed_inspections):
    # Arrange — B has an extra fault that A lacks
    park = "PARK_D2"
    seed_inspections(park, "insp-a", [("R1-C1", "hot-spot-high")])
    seed_inspections(park, "insp-b", [("R1-C1", "hot-spot-high"), ("R2-C2", "soiling")])

    # Act
    body = client.get(f"/parks/{park}/inspections/insp-a/diff/insp-b").json()

    # Assert
    assert body["counts"]["new"] == 1
    assert {"panel_id": "R2-C2", "class": "soiling"} in body["new"]


def test_diff_resolved_fault_appears_in_resolved(client, seed_inspections):
    # Arrange — A had a fault that is gone in B
    park = "PARK_D3"
    seed_inspections(park, "insp-a", [("R1-C1", "hot-spot-high"), ("R2-C2", "soiling")])
    seed_inspections(park, "insp-b", [("R1-C1", "hot-spot-high")])

    # Act
    body = client.get(f"/parks/{park}/inspections/insp-a/diff/insp-b").json()

    # Assert
    assert body["counts"]["resolved"] == 1
    assert {"panel_id": "R2-C2", "class": "soiling"} in body["resolved"]


def test_diff_unknown_inspection_returns_404(client, seed_inspections):
    # Arrange
    park = "PARK_D4"
    seed_inspections(park, "insp-a", [("R1-C1", "hot-spot-high")])

    # Act
    r = client.get(f"/parks/{park}/inspections/insp-a/diff/does-not-exist")

    # Assert
    assert r.status_code == 404
