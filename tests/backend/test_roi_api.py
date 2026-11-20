"""Tests for ROI API endpoints (P0.6)."""
import pytest
from fastapi.testclient import TestClient

from solardoctor.api.app import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_get_and_update_roi(client):
    # GET plant ROI
    r = client.get("/api/v1/roi/1")
    assert r.status_code == 200
    data = r.json()
    assert data["plant_id"] == 1
    assert data["state"] == "ready"
    assert data["decision"] in ("CLEAN NOW", "WAIT", "FIELD CHECK", "REPLACE")
    assert data["recoverable_kwh_day"] >= 0
    assert data["inr_per_day"] >= 0
    assert data["inr_per_month"] >= 0
    assert "settings" in data

    # PUT plant settings
    put_res = client.put(
        "/api/v1/roi/1/settings",
        json={
            "tariff_inr_kwh": 7.15,
            "cleaning_cost_per_module_inr": 42.0,
            "tariff_preset": "utility",
        },
    )
    assert put_res.status_code == 200
    put_data = put_res.json()
    assert put_data["tariff_inr_kwh"] == 7.15
    assert put_data["cleaning_cost_per_module_inr"] == 42.0
    assert put_data["tariff_preset"] == "utility"

    # Re-fetch to ensure persistence
    r2 = client.get("/api/v1/roi/1")
    assert r2.status_code == 200
    assert r2.json()["settings"]["tariff_inr_kwh"] == 7.15


def test_roi_nonexistent_plant(client):
    r = client.get("/api/v1/roi/999999")
    assert r.status_code == 404
