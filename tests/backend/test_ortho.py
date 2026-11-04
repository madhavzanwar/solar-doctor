"""Tests for the ortho router (platform/api/routers/ortho.py).

Covers validation, error, and empty-state paths without needing a real
multi-gigabyte GeoTIFF — invalid/garbage uploads exercise the streaming write
and metadata-validation branches.
"""
from __future__ import annotations


def test_upload_ortho_rejects_non_tiff_name(client):
    # Act — a .png filename fails ortho-name validation before any write
    resp = client.post(
        "/park/TESTPARK/ortho",
        files={"file": ("photo.png", b"x", "image/png")},
    )
    # Assert
    assert resp.status_code == 400


def test_upload_ortho_rejects_garbage_tiff(client):
    # Act — valid name, but the bytes are not a georeferenced raster
    resp = client.post(
        "/park/TESTPARK/ortho",
        files={"file": ("o.tif", b"not a real geotiff", "image/tiff")},
    )
    # Assert — file is streamed to disk then metadata validation fails
    assert resp.status_code == 400


def test_list_orthos_empty_for_unknown_park(client):
    resp = client.get("/park/EMPTYPARK/orthos")
    assert resp.status_code == 200
    assert resp.json() == {"park_id": "EMPTYPARK", "orthos": []}


def test_get_ortho_metadata_missing_404(client):
    resp = client.get("/park/TESTPARK/ortho/missing.tif")
    assert resp.status_code == 404


def test_delete_ortho_missing_404(client):
    resp = client.delete("/park/TESTPARK/ortho/missing.tif")
    assert resp.status_code == 404


def test_get_ortho_tile_missing_ortho_404(client):
    # A tile request for a non-existent ortho is rejected before tiling.
    resp = client.get("/park/TESTPARK/ortho/missing.tif/tiles/0/0/0.png")
    assert resp.status_code == 404


def test_invalid_park_id_rejected(client):
    # park_id with illegal characters is rejected by _validate_park_id
    resp = client.get("/park/bad$park/orthos")
    assert resp.status_code == 400
