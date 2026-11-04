"""Tests for the results and settings routers (error/validation paths).

These exercise path-validation and not-found branches without producing real
output files, and verify GET /settings plus PUT-with-bad-body (which is rejected
before any write touches the real settings.yaml).
"""
from __future__ import annotations


# ── results router ───────────────────────────────────────────────────────────

def test_serve_result_image_missing_returns_404(client):
    # No output dir for this job -> image not found
    resp = client.get("/results/job123/frame.jpg")
    assert resp.status_code == 404


def test_get_job_image_invalid_suffix_400(client):
    # Filename must end in a known annotated-image suffix
    resp = client.get("/image/job123/notanimage.txt")
    assert resp.status_code == 400


def test_get_job_image_valid_suffix_missing_404(client):
    # Allowed suffix but the file does not exist
    resp = client.get("/image/job123/frame_annotated.jpg")
    assert resp.status_code == 404


def test_serve_result_image_invalid_job_id_400(client):
    resp = client.get("/results/bad$job/frame.jpg")
    assert resp.status_code == 400


# ── settings router ──────────────────────────────────────────────────────────

def test_get_settings_returns_data(client):
    resp = client.get("/settings")
    # settings.yaml ships with the repo -> 200 with a settings dict
    assert resp.status_code == 200
    assert "settings" in resp.json()


def test_put_settings_rejects_non_dict_body(client):
    # Rejected before any file write
    resp = client.put("/settings", json={"settings": "not-a-dict"})
    assert resp.status_code == 400


def test_put_settings_rejects_missing_settings_key(client):
    resp = client.put("/settings", json={"unexpected": 1})
    assert resp.status_code == 400
