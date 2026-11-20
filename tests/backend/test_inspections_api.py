"""Tests for unified Inspections API (P0.2)."""
import io
import os
import pytest
from PIL import Image
from fastapi.testclient import TestClient

os.environ["SOLARDOCTOR_RGB_FALLBACK"] = "1"
from solardoctor.api.app import app


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def _make_dummy_image(format="JPEG", color=(50, 80, 150), size=(224, 224)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format=format)
    return buf.getvalue()


def test_create_inspection_dusty_sample(client):
    img_path = "frontend/public/images/dusty-panel-closeup.webp"
    with open(img_path, "rb") as f:
        img_bytes = f.read()

    response = client.post(
        "/api/v1/inspections",
        files={"file": ("dusty.webp", img_bytes, "image/webp")},
        data={"plant_id": 1, "generate_xai": True},
    )
    assert response.status_code == 201
    data = response.json()

    assert data["id"].startswith("INSP-")
    assert data["plant_id"] == 1
    assert data["status"] == "completed"

    pred = data["prediction"]
    assert pred["predicted_class"] == "dusty"
    assert pred["confidence"] >= 0.80
    assert pred["is_ood"] is False
    assert pred["needs_field_check"] is False
    assert len(pred["top3"]) == 3
    assert pred["top3"][0]["class"] == "dusty"

    fusion = data["fusion"]
    assert fusion["verdict"] in ("Soiling confirmed", "Deficit detected", "Needs field check", "Normal operation")
    assert fusion["action"] in ("CLEAN NOW", "WAIT", "REPLACE", "FIELD CHECK", "NONE")
    assert fusion["severity"] in ("CRITICAL", "HIGH", "MEDIUM", "LOW")

    assert "gradcam_base64" in data
    assert "lime_base64" in data
    assert data["image_url"] == f"/api/v1/inspections/{data['id']}/image"
    assert data["xai_gradcam_url"] == f"/api/v1/inspections/{data['id']}/gradcam"
    assert data["xai_lime_url"] == f"/api/v1/inspections/{data['id']}/lime"


def test_get_inspection_and_stream_assets(client):
    img_bytes = _make_dummy_image(color=(30, 40, 120))
    res = client.post(
        "/api/v1/inspections",
        files={"file": ("blue_panel.jpg", img_bytes, "image/jpeg")},
        data={"generate_xai": True},
    )
    assert res.status_code == 201
    insp_id = res.json()["id"]

    # GET by ID
    get_res = client.get(f"/api/v1/inspections/{insp_id}")
    assert get_res.status_code == 200
    assert get_res.json()["id"] == insp_id

    # Stream original image
    img_stream = client.get(f"/api/v1/inspections/{insp_id}/image")
    assert img_stream.status_code == 200
    assert img_stream.headers["content-type"] in ("image/jpeg", "image/png", "image/webp")
    assert len(img_stream.content) > 0

    # Stream Grad-CAM
    cam_stream = client.get(f"/api/v1/inspections/{insp_id}/gradcam")
    assert cam_stream.status_code == 200
    assert cam_stream.headers["content-type"] == "image/png"
    assert len(cam_stream.content) > 0

    # Stream LIME
    lime_stream = client.get(f"/api/v1/inspections/{insp_id}/lime")
    assert lime_stream.status_code == 200
    assert lime_stream.headers["content-type"] == "image/png"
    assert len(lime_stream.content) > 0


def test_list_inspections(client):
    res = client.get("/api/v1/inspections?limit=10")
    assert res.status_code == 200
    items = res.json()
    assert isinstance(items, list)
    assert len(items) >= 1
    assert "id" in items[0]
    assert "prediction" in items[0]


def test_ood_detection_non_solar_image(client):
    # Vibrant neon magenta/red square (high saturation non-panel image)
    buf = io.BytesIO()
    Image.new("RGB", (224, 224), (255, 0, 50)).save(buf, format="JPEG")

    res = client.post(
        "/api/v1/inspections",
        files={"file": ("red.jpg", buf.getvalue(), "image/jpeg")},
    )
    assert res.status_code == 201
    pred = res.json()["prediction"]
    assert pred["is_ood"] is True
    assert pred["needs_field_check"] is True
    assert pred["field_check_reason"] == "out_of_distribution"


def test_invalid_image_upload_rejected(client):
    # Corrupt data
    res_bad = client.post(
        "/api/v1/inspections",
        files={"file": ("bad.jpg", b"NOT AN IMAGE DATA", "image/jpeg")},
    )
    assert res_bad.status_code == 422

    # Empty upload
    res_empty = client.post(
        "/api/v1/inspections",
        files={"file": ("empty.jpg", b"", "image/jpeg")},
    )
    assert res_empty.status_code == 400
