"""Hardening tests for scripts/fetch_weights.py: retries, ranges, redirects, token scope. No external network."""
from __future__ import annotations

import hashlib
import http.server
import importlib.util
import io
import threading
import urllib.error
import urllib.request
from pathlib import Path

_path = Path(__file__).resolve().parents[1] / "scripts" / "fetch_weights.py"
_spec = importlib.util.spec_from_file_location("fetch_weights_h", _path)
fw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fw)

DATA = b"thermal-weights-" * 1000
SHA = hashlib.sha256(DATA).hexdigest()
QUIET = {"log": lambda *_: None, "sleep": lambda *_: None}
URL = "http://x/u"


class Resp(io.BytesIO):
    def __init__(self, data, status=200, headers=None):
        super().__init__(data)
        self.status = status
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def serving(data):
    def op(req, timeout=None):
        rng = req.get_header("Range")
        if rng:
            start = int(rng.split("=")[1].rstrip("-"))
            return Resp(data[start:], 206, {"Content-Range": f"bytes {start}-{len(data) - 1}/{len(data)}"})
        return Resp(data, 200)
    return op


def test_206_with_wrong_offset_is_rejected_then_retried(tmp_path):
    dest = tmp_path / "best.pt"
    dest.with_name("best.pt.part").write_bytes(DATA[:5000])
    ranges = []

    def op(req, timeout=None):
        ranges.append(req.get_header("Range"))
        if len(ranges) == 1:
            return Resp(DATA[:100], 206, {"Content-Range": "bytes 0-99/16000"})
        return Resp(DATA, 200)

    assert fw.fetch([URL], dest, SHA, opener=op, **QUIET) == 0
    assert dest.read_bytes() == DATA
    assert ranges[0] == "bytes=5000-"


def test_good_206_resume_appends(tmp_path):
    dest = tmp_path / "best.pt"
    dest.with_name("best.pt.part").write_bytes(DATA[:5000])
    assert fw.fetch([URL], dest, SHA, opener=serving(DATA), **QUIET) == 0
    assert dest.read_bytes() == DATA


def test_416_with_full_size_part_is_verified_by_hash(tmp_path):
    dest = tmp_path / "best.pt"
    dest.with_name("best.pt.part").write_bytes(DATA)

    def op(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 416, "Range Not Satisfiable", {}, None)

    assert fw.fetch([URL], dest, SHA, opener=op, **QUIET) == 0
    assert dest.read_bytes() == DATA


def test_part_kept_after_network_error_then_resumed(tmp_path):
    dest = tmp_path / "best.pt"
    part = dest.with_name("best.pt.part")
    part.write_bytes(DATA[:3000])

    def op(req, timeout=None):
        raise urllib.error.URLError("boom")

    assert fw.fetch([URL], dest, SHA, opener=op, **QUIET) == 1
    assert part.read_bytes() == DATA[:3000] and not dest.exists()
    assert fw.fetch([URL], dest, SHA, opener=serving(DATA), **QUIET) == 0


def test_short_read_is_retried_on_same_url(tmp_path):
    dest = tmp_path / "best.pt"
    calls = []

    def op(req, timeout=None):
        calls.append(1)
        body = DATA[:5000] if len(calls) == 1 else DATA  # first: closes early
        return Resp(body, 200, {"Content-Length": str(len(DATA))})

    assert fw.fetch([URL], dest, SHA, opener=op, **QUIET) == 0
    assert len(calls) == 2 and dest.read_bytes() == DATA


def test_retries_are_bounded(tmp_path):
    calls = []

    def op(req, timeout=None):
        calls.append(1)
        return Resp(b"bad")

    assert fw.fetch([URL], tmp_path / "b.pt", SHA, opener=op, retries=2, **QUIET) == 1
    assert len(calls) == 3
    assert not (tmp_path / "b.pt").exists()


def test_unpublished_first_source_is_quiet(tmp_path, capsys):
    logs = []

    def op(req, timeout=None):
        if "mine" in req.full_url:
            raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)
        return Resp(DATA)

    rc = fw.fetch(["http://x/mine", "http://x/up"], tmp_path / "b.pt", SHA, opener=op, log=logs.append,
                  sleep=lambda *_: None)
    assert rc == 0
    assert any("not published yet" in m for m in logs)
    assert capsys.readouterr().err == ""


def test_force_redownloads_good_file(tmp_path):
    dest = tmp_path / "best.pt"
    dest.write_bytes(DATA)
    calls = []

    def op(req, timeout=None):
        calls.append(1)
        return Resp(DATA)

    assert fw.fetch([URL], dest, SHA, force=True, opener=op, **QUIET) == 0
    assert calls


def test_env_url_override_and_cli(tmp_path, monkeypatch):
    seen = []

    def fake_fetch(urls, dest, expected, force, **kw):
        seen.append(list(urls))
        return 0

    monkeypatch.setattr(fw, "fetch", fake_fetch)
    monkeypatch.setenv("SOLARDOCTOR_THERMAL_URL", "http://example/env.pt")
    assert fw.main(["--dest", str(tmp_path / "x.pt")]) == 0
    monkeypatch.delenv("SOLARDOCTOR_THERMAL_URL")
    assert fw.main(["--dest", str(tmp_path / "x.pt")]) == 0
    assert fw.main(["--dest", str(tmp_path / "x.pt"), "--url", "http://a/b"]) == 0
    assert seen == [["http://example/env.pt"], list(fw.DEFAULT_URLS), ["http://a/b"]]


def test_token_not_sent_to_public_space(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_TOKEN", "secret")
    auth = []

    def op(req, timeout=None):
        auth.append(req.get_header("Authorization"))
        return Resp(DATA)

    space = "https://huggingface.co/spaces/parakh20/axalon-api/resolve/main/ml/checkpoints/best.pt"
    own = "https://huggingface.co/madhavzanwar/solar-doctor-thermal-yolo11x/resolve/main/best.pt"
    assert fw.fetch([space], tmp_path / "a.pt", SHA, opener=op, **QUIET) == 0
    assert fw.fetch([own], tmp_path / "b.pt", SHA, opener=op, **QUIET) == 0
    assert auth == [None, "Bearer secret"]


def test_authorization_stripped_on_offhost_redirect():
    seen = {}

    class Target(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen["auth"] = self.headers.get("Authorization")
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"ok")

        def log_message(self, *a):
            pass

    target = http.server.HTTPServer(("127.0.0.1", 0), Target)
    tport = target.server_port

    class Redir(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(302)
            self.send_header("Location", f"http://localhost:{tport}/f")  # different host name
            self.end_headers()

        def log_message(self, *a):
            pass

    redir = http.server.HTTPServer(("127.0.0.1", 0), Redir)
    for srv in (target, redir):
        threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{redir.server_port}/x",
                                     headers={"Authorization": "Bearer secret"})
        with fw._default_open(req, timeout=10) as r:
            assert r.read() == b"ok"
    finally:
        target.shutdown()
        redir.shutdown()
        target.server_close()
        redir.server_close()
    assert seen["auth"] is None
