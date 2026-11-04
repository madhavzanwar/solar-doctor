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
    batch_fixture(park_id="TEST_GRID_PARK2")
    # The DB inspection_id is stored by the orchestrator (e.g. BATCH-TEST_GRID_PARK2-…)
    # which differs from the HTTP job_id. Look it up via the park summary.
    park_summary = client.get("/park/TEST_GRID_PARK2").json()
    inspection_id = park_summary["inspections"][0]["id"]
    r = client.get(f"/park/TEST_GRID_PARK2/grid?inspection_id={inspection_id}")
    assert r.status_code == 200
    assert r.json()["inspection_id"] == inspection_id
