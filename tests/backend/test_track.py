"""Tests for the /track workspace: password login, research/notes log, file library."""
import io

import pytest


@pytest.fixture
def track_password(monkeypatch):
    monkeypatch.setenv("AXALON_TRACK_PASSWORD", "test-track-pw")
    return "test-track-pw"


# ── login ─────────────────────────────────────────────────────────────────────

def test_track_login_ok(client, track_password):
    resp = client.post("/track/login", json={"password": track_password})
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}


def test_track_login_wrong_password(client, track_password):
    resp = client.post("/track/login", json={"password": "nope"})
    assert resp.status_code == 401


def test_track_login_missing_password_field(client, track_password):
    resp = client.post("/track/login", json={})
    assert resp.status_code == 401


def test_track_login_unconfigured_returns_503(client, monkeypatch):
    monkeypatch.delenv("AXALON_TRACK_PASSWORD", raising=False)
    resp = client.post("/track/login", json={"password": "anything"})
    assert resp.status_code == 503


# ── notes ─────────────────────────────────────────────────────────────────────

def _make_note(client, **overrides) -> dict:
    payload = {
        "title": "Open-Elevation API research",
        "kind": "research",
        "body": "Free elevation API, 1km SRTM grid — good enough for AGL follow.",
        "url": "https://open-elevation.example",
        "tags": "terrain, planner",
    }
    payload.update(overrides)
    resp = client.post("/track/notes", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_note_crud(client):
    note = _make_note(client)
    assert note["kind"] == "research"
    assert note["tags"] == "terrain, planner"

    listed = client.get("/track/notes").json()
    assert len(listed) == 1

    resp = client.patch(f"/track/notes/{note['id']}", json={"body": "updated", "kind": "doc"})
    assert resp.status_code == 200
    assert resp.json()["body"] == "updated"
    assert resp.json()["kind"] == "doc"

    assert client.delete(f"/track/notes/{note['id']}").status_code == 204
    assert client.get("/track/notes").json() == []


def test_note_requires_title(client):
    assert client.post("/track/notes", json={"title": " ", "body": "x"}).status_code == 400


def test_note_rejects_bad_kind(client):
    assert client.post("/track/notes", json={"title": "X", "kind": "tweet"}).status_code == 400


def test_note_filter_by_kind(client):
    _make_note(client)
    _make_note(client, title="Flight log 06-12", kind="log")
    logs = client.get("/track/notes?kind=log").json()
    assert len(logs) == 1
    assert logs[0]["kind"] == "log"


def test_note_404s(client):
    assert client.patch("/track/notes/999", json={"body": "x"}).status_code == 404
    assert client.delete("/track/notes/999").status_code == 404


# ── files ─────────────────────────────────────────────────────────────────────

def _upload(client, filename="bracket.stl", content=b"solid bracket", label="Camera mount v2"):
    return client.post(
        "/track/files",
        files={"file": (filename, io.BytesIO(content), "application/octet-stream")},
        data={"label": label},
    )


def test_file_upload_list_download_delete(client):
    resp = _upload(client)
    assert resp.status_code == 201, resp.text
    meta = resp.json()
    assert meta["original_name"] == "bracket.stl"
    assert meta["label"] == "Camera mount v2"
    assert meta["size_bytes"] == len(b"solid bracket")

    listed = client.get("/track/files").json()
    assert len(listed) == 1

    dl = client.get(f"/track/files/{meta['id']}")
    assert dl.status_code == 200
    assert dl.content == b"solid bracket"

    assert client.delete(f"/track/files/{meta['id']}").status_code == 204
    assert client.get("/track/files").json() == []


def test_file_upload_rejects_disallowed_extension(client):
    resp = _upload(client, filename="payload.exe", content=b"MZ")
    assert resp.status_code == 400


def test_file_upload_sanitizes_path_traversal(client):
    resp = _upload(client, filename="../../etc/passwd.pdf", content=b"%PDF-1.4")
    assert resp.status_code == 201
    assert "/" not in resp.json()["original_name"]
    assert ".." not in resp.json()["stored_name"]


def test_file_download_404(client):
    assert client.get("/track/files/999").status_code == 404
