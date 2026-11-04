"""Tests for GET /analytics/overview — portfolio trend bundles in one call."""
from axalon.db.models import Detection, Inspection, Park


def _seed_park(session, park_id: str, severities: list[str]) -> None:
    session.add(Park(id=park_id, name=f"Park {park_id}"))
    session.flush()
    insp = Inspection(id=f"INSP-{park_id}-1", park_id=park_id, flight_date="2026-06-01")
    session.add(insp)
    session.flush()
    for sev in severities:
        session.add(
            Detection(inspection_id=insp.id, severity=sev, class_="hot-spot-low")
        )
    session.commit()


def test_overview_empty_db(client):
    resp = client.get("/analytics/overview")
    assert resp.status_code == 200
    assert resp.json() == []


def test_overview_bundles_all_parks(client, db_session):
    _seed_park(db_session, "PARK_A", ["CRITICAL", "CRITICAL", "LOW"])
    _seed_park(db_session, "PARK_B", ["MEDIUM"])

    resp = client.get("/analytics/overview")
    assert resp.status_code == 200
    bundles = resp.json()
    assert len(bundles) == 2

    by_id = {b["park"]["id"]: b for b in bundles}
    assert by_id["PARK_A"]["park"]["name"] == "Park PARK_A"

    trend_a = by_id["PARK_A"]["trend"]
    assert len(trend_a) == 1
    assert trend_a[0]["CRITICAL"] == 2
    assert trend_a[0]["LOW"] == 1
    assert trend_a[0]["date"] == "2026-06-01"

    trend_b = by_id["PARK_B"]["trend"]
    assert trend_b[0]["MEDIUM"] == 1
    assert trend_b[0]["CRITICAL"] == 0


def test_overview_park_without_inspections_has_empty_trend(client, db_session):
    db_session.add(Park(id="PARK_EMPTY", name="Empty"))
    db_session.commit()
    bundles = client.get("/analytics/overview").json()
    assert bundles[0]["trend"] == []
