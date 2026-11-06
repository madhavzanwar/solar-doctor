from __future__ import annotations

import base64

import pytest

from solardoctor.api.routers import vision as vision_router


def _up(data, name="p.png", ctype="image/png"):
    return {"file": (name, data, ctype)}


@pytest.fixture
def ready(client, bundle_env):
    bundle_env()
    return client


def test_model_info(ready):
    r = ready.get("/api/v1/vision/model")
    assert r.status_code == 200 and r.json()["model_version"] == "rgb-test-0001"


def test_predict_ok_and_legacy_alias(ready, png):
    r = ready.post("/api/v1/vision/predict", files=_up(png))
    assert r.status_code == 200 and r.json()["predicted_class"]
    assert ready.post("/vision/predict", files=_up(png)).status_code == 200


def test_predict_ignores_client_mime(ready, png):
    assert ready.post("/api/v1/vision/predict", files=_up(png, "x.txt", "text/plain")).status_code == 200


def test_not_an_image_is_422(ready):
    r = ready.post("/api/v1/vision/predict", files=_up(b"hello world", "x.png"))
    assert r.status_code == 422


def test_empty_upload_is_400(ready):
    assert ready.post("/api/v1/vision/predict", files=_up(b"")).status_code == 400


def test_missing_file_is_422(ready):
    assert ready.post("/api/v1/vision/predict").status_code == 422


def test_oversize_is_413(ready, monkeypatch):
    monkeypatch.setattr(vision_router, "MAX_UPLOAD_BYTES", 1000)
    assert ready.post("/api/v1/vision/predict", files=_up(b"\x00" * 3000)).status_code == 413


def test_unsupported_format_is_422(ready):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buf, format="BMP")
    assert ready.post("/api/v1/vision/predict", files=_up(buf.getvalue(), "x.bmp")).status_code == 422


def test_explain_gradcam_and_lime(ready, png):
    r = ready.post("/api/v1/vision/explain?method=gradcam", files=_up(png))
    assert r.status_code == 200 and base64.b64decode(r.json()["png_base64"])[:4] == b"\x89PNG"
    q = "/api/v1/vision/explain?method=lime&num_samples=50&top_k=2"
    assert ready.post(q, files=_up(png)).json()["cached"] is False
    assert ready.post(q, files=_up(png)).json()["cached"] is True


@pytest.mark.parametrize("qs", ["method=shap", "num_samples=49", "num_samples=5001", "top_k=0", "top_k=21"])
def test_explain_validates_query(ready, png, qs):
    assert ready.post(f"/api/v1/vision/explain?{qs}", files=_up(png)).status_code == 422


def test_unavailable_is_503(client, monkeypatch, png):
    from solardoctor.vision.classifier import reset_classifier
    for k in ("SOLARDOCTOR_RGB_MODEL_DIR", "SOLARDOCTOR_RGB_MODEL_REVISION"):
        monkeypatch.delenv(k, raising=False)
    reset_classifier()
    for call in (lambda: client.get("/api/v1/vision/model"),
                 lambda: client.post("/api/v1/vision/predict", files=_up(png)),
                 lambda: client.post("/api/v1/vision/explain", files=_up(png))):
        r = call()
        assert r.status_code == 503 and r.json() == {"detail": "rgb_model_unavailable"}


def test_auth_policy_viewer_reads_operator_posts(client, bundle_env, users_mode, make_user, login, png):
    bundle_env()
    make_user("v@axalon.test", "viewer")
    make_user("o@axalon.test", "operator")
    viewer, operator = login("v@axalon.test"), login("o@axalon.test")
    assert client.get("/api/v1/vision/model").status_code == 401
    assert client.get("/api/v1/vision/model", headers=viewer).status_code == 200
    assert client.post("/api/v1/vision/predict", files=_up(png), headers=viewer).status_code == 403
    assert client.post("/api/v1/vision/predict", files=_up(png), headers=operator).status_code == 200


def test_mpo_jpeg_is_accepted(ready):
    import io
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (64, 48), (200, 10, 10)).save(buf, "MPO", save_all=True,
                                                    append_images=[Image.new("RGB", (64, 48), (10, 10, 200))])
    data = buf.getvalue()
    with Image.open(io.BytesIO(data)) as im:
        assert im.format == "MPO"
    assert ready.post("/api/v1/vision/predict", files=_up(data, "p.jpg", "image/jpeg")).status_code == 200
