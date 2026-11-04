"""NodeODM REST client: request sequencing, retries, progress parsing, errors.

Every test runs against the in-memory FakeNodeODM — no network.
"""
from __future__ import annotations

import json

import pytest

from axalon.core.odm_client import (
    NodeODMClient,
    NodeODMError,
    TaskStatus,
    build_task_options,
    client_from_env,
)


def _client(fake, **kw) -> NodeODMClient:
    return NodeODMClient(
        "http://odm.local:3000/", token=kw.pop("token", None),
        session=fake, sleep=lambda _s: None, **kw,
    )


def _images(tmp_path, n: int) -> list:
    paths = []
    for i in range(n):
        p = tmp_path / f"img_{i:03d}.jpg"
        p.write_bytes(b"\xff\xd8jpeg")
        paths.append(p)
    return paths


def test_client_from_env_returns_none_when_unset(monkeypatch):
    monkeypatch.delenv("AXALON_NODEODM_URL", raising=False)
    assert client_from_env() is None


def test_client_from_env_reads_url_and_token(monkeypatch):
    monkeypatch.setenv("AXALON_NODEODM_URL", "http://odm:3000/")
    monkeypatch.setenv("AXALON_NODEODM_TOKEN", "sekret")
    client = client_from_env()
    assert client is not None
    assert client.base_url == "http://odm:3000"
    assert client.token == "sekret"


def test_submit_sequences_init_upload_commit_in_chunks(odm_fakes, tmp_path):
    # Arrange
    fake = odm_fakes.FakeNodeODM()
    client = _client(fake, upload_chunk_size=5)
    images = _images(tmp_path, 12)
    options = build_task_options(orthophoto_resolution_cm=3.0)

    # Act
    task_uuid = client.submit_task("park-A", images, options)

    # Assert
    assert task_uuid == fake.task_uuid
    upload = f"POST /task/new/upload/{fake.task_uuid}"
    assert fake.paths() == [
        "POST /task/new/init", upload, upload, upload,
        f"POST /task/new/commit/{fake.task_uuid}",
    ]
    assert [len(c.file_names) for c in fake.calls[1:4]] == [5, 5, 2]
    init = fake.calls[0]
    assert init.data["name"] == "park-A"
    sent = {o["name"]: o["value"] for o in json.loads(init.data["options"])}
    assert sent["orthophoto-resolution"] == 3.0
    assert sent["fast-orthophoto"] is True
    assert sent["dsm"] is False


def test_token_is_sent_as_query_param(odm_fakes, tmp_path):
    fake = odm_fakes.FakeNodeODM()
    client = _client(fake, token="tok123")
    client.submit_task("p", _images(tmp_path, 2), [])
    assert all(c.params and c.params.get("token") == "tok123" for c in fake.calls)


def test_task_info_parses_status_and_progress(odm_fakes):
    fake = odm_fakes.FakeNodeODM(info_script=[{"code": 20, "progress": 42.5}])
    info = _client(fake).task_info(fake.task_uuid)
    assert info.status is TaskStatus.RUNNING
    assert info.progress == pytest.approx(42.5)
    assert not info.is_terminal


def test_task_info_failed_carries_error_message(odm_fakes):
    fake = odm_fakes.FakeNodeODM(
        info_script=[{"code": 30, "progress": 12, "error": "Not enough overlap"}],
    )
    info = _client(fake).task_info(fake.task_uuid)
    assert info.status is TaskStatus.FAILED
    assert info.is_terminal
    assert info.error == "Not enough overlap"


def test_progress_is_clamped_to_0_100(odm_fakes):
    fake = odm_fakes.FakeNodeODM(info_script=[{"code": 20, "progress": 180}])
    assert _client(fake).task_info("u").progress == 100.0


def test_transient_errors_are_retried(odm_fakes, tmp_path):
    # Arrange — init fails twice (connection refused, then 503) before succeeding
    fake = odm_fakes.FakeNodeODM(failures={
        "POST /task/new/init": [
            odm_fakes.connection_error(),
            odm_fakes.FakeResponse(status_code=503, payload={"error": "busy"}),
        ],
    })
    client = _client(fake, max_retries=3)

    # Act
    task_uuid = client.submit_task("p", _images(tmp_path, 1), [])

    # Assert
    assert task_uuid == fake.task_uuid
    assert fake.paths().count("POST /task/new/init") == 3


def test_retries_exhausted_raise_transient_error(odm_fakes):
    fake = odm_fakes.FakeNodeODM(failures={
        "GET /task/u/info": [odm_fakes.connection_error() for _ in range(5)],
    })
    with pytest.raises(NodeODMError) as exc:
        _client(fake, max_retries=2).task_info("u")
    assert exc.value.transient is True
    assert fake.paths().count("GET /task/u/info") == 3


def test_client_error_is_not_retried(odm_fakes):
    fake = odm_fakes.FakeNodeODM(failures={
        "POST /task/new/init": [
            odm_fakes.FakeResponse(status_code=403, payload={"error": "Invalid token"}),
        ],
    })
    with pytest.raises(NodeODMError) as exc:
        _client(fake).init_task("p", [])
    assert exc.value.transient is False
    assert "Invalid token" in str(exc.value)
    assert fake.paths().count("POST /task/new/init") == 1


def test_error_payload_with_200_status_raises(odm_fakes):
    # NodeODM reports some failures as HTTP 200 + {"error": "..."}
    fake = odm_fakes.FakeNodeODM(failures={
        "POST /task/new/commit/u": [odm_fakes.FakeResponse(payload={"error": "No images"})],
    })
    with pytest.raises(NodeODMError, match="No images"):
        _client(fake).commit_task("u")


def test_failed_upload_removes_the_half_created_task(odm_fakes, tmp_path):
    fake = odm_fakes.FakeNodeODM(failures={
        "POST /task/new/upload/11111111-2222-3333-4444-555555555555": [
            odm_fakes.FakeResponse(status_code=400, payload={"error": "Bad image"}),
        ],
    })
    with pytest.raises(NodeODMError):
        _client(fake).submit_task("p", _images(tmp_path, 3), [])
    assert fake.paths()[-1] == "POST /task/remove"


def test_download_orthophoto_streams_to_file(odm_fakes, tmp_path):
    fake = odm_fakes.FakeNodeODM(orthophoto=b"x" * 5000)
    dest = tmp_path / "out.tif"
    written = _client(fake).download_orthophoto("u", dest)
    assert written == 5000
    assert dest.read_bytes() == b"x" * 5000
    assert fake.paths() == ["GET /task/u/download/orthophoto.tif"]


def test_cancel_and_remove_post_uuid(odm_fakes):
    fake = odm_fakes.FakeNodeODM()
    client = _client(fake)
    client.cancel_task("u")
    client.remove_task("u")
    assert fake.paths() == ["POST /task/cancel", "POST /task/remove"]
    assert all(c.data == {"uuid": "u"} for c in fake.calls)


def test_build_task_options_rejects_out_of_range_resolution():
    with pytest.raises(ValueError):
        build_task_options(orthophoto_resolution_cm=0)
