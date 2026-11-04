# drone/tests/test_handoff.py
import io
import zipfile

import httpx
from drone.agent.handoff import zip_capture, post_handoff


def test_zip_capture_packs_files(tmp_path):
    (tmp_path / "img_1.jpg").write_bytes(b"rgb")
    (tmp_path / "img_1.json").write_text("{}")
    data = zip_capture(str(tmp_path))
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        names = zf.namelist()
    assert "img_1.jpg" in names and "img_1.json" in names


async def test_post_handoff_sends_bearer_multipart_to_batch():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        captured["url"] = str(request.url)
        captured["ctype"] = request.headers.get("content-type", "")
        return httpx.Response(202, json={"job_id": "batch-42", "state": "queued"})

    transport = httpx.MockTransport(handler)
    out = await post_handoff(
        base_url="https://api.example.com", token="t0k",
        park_id="park-7", zip_bytes=b"PK\x03\x04", altitude_m=20.0,
        transport=transport)
    assert out["job_id"] == "batch-42"
    assert captured["auth"] == "Bearer t0k"
    assert captured["url"].endswith("/batch")
    assert "multipart/form-data" in captured["ctype"]
