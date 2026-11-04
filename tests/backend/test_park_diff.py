"""Tests for the /park/{id}/diff endpoint (platform/api/routers/park.py).

Builds a synthetic park with two inspections in the temp DB, then exercises the
per-panel diff response and its 404 branches.
"""
from __future__ import annotations

import pytest

from axalon.db.models import Park, Inspection, Detection


def _seed_diff_park(db_session):
    """Two inspections of park DPARK with a new, a resolved, and an unchanged fault."""
    # Stage commits so each FK parent exists before its children insert.
    db_session.add(Park(id="DPARK", name="Diff Park"))
    db_session.commit()
    db_session.add(Inspection(id="inspa", park_id="DPARK"))
    db_session.add(Inspection(id="inspb", park_id="DPARK"))
    db_session.commit()

    # Inspection A: R1-C1 critical hot-spot, R1-C2 soiling (will be resolved in B)
    db_session.add(Detection(inspection_id="inspa", panel_id="R1-C1",
                             class_="hot-spot-high", severity="CRITICAL", confidence=0.9))
    db_session.add(Detection(inspection_id="inspa", panel_id="R1-C2",
                             class_="soiling", severity="LOW", confidence=0.8))
    # Inspection B: R1-C1 unchanged, R2-C5 new cell fault
    db_session.add(Detection(inspection_id="inspb", panel_id="R1-C1",
                             class_="hot-spot-high", severity="CRITICAL", confidence=0.9))
    db_session.add(Detection(inspection_id="inspb", panel_id="R2-C5",
                             class_="cell", severity="MEDIUM", confidence=0.7))
    db_session.commit()


def test_diff_returns_per_panel_breakdown(client, db_session):
    # Arrange
    _seed_diff_park(db_session)

    # Act
    resp = client.get("/park/DPARK/diff", params={"inspection_a": "inspa", "inspection_b": "inspb"})

    # Assert
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["park_id"] == "DPARK"
    assert set(body["summary"]) == {"new", "resolved", "changed"}
    panel_ids = {p["panel_id"] for p in body["panels"]}
    assert {"R1-C1", "R1-C2", "R2-C5"} <= panel_ids
    # Every panel carries a status and both-side severities
    for panel in body["panels"]:
        assert panel["status"] in ("new", "resolved", "changed", "unchanged")
        assert "severity_a" in panel and "severity_b" in panel


def test_diff_detects_new_and_resolved_counts(client, db_session):
    # Arrange
    _seed_diff_park(db_session)

    # Act
    body = client.get(
        "/park/DPARK/diff",
        params={"inspection_a": "inspa", "inspection_b": "inspb"},
    ).json()

    # Assert — R2-C5 is new, R1-C2 soiling is resolved
    assert body["summary"]["new"] >= 1
    assert body["summary"]["resolved"] >= 1


def test_diff_unknown_park_404(client):
    resp = client.get("/park/GHOST/diff", params={"inspection_a": "a", "inspection_b": "b"})
    assert resp.status_code == 404


def test_diff_unknown_inspection_404(client, db_session):
    # Arrange — park exists, inspection_a does not
    db_session.add(Park(id="DPARK", name="Diff Park"))
    db_session.commit()

    # Act
    resp = client.get("/park/DPARK/diff", params={"inspection_a": "missing", "inspection_b": "alsomissing"})

    # Assert
    assert resp.status_code == 404
