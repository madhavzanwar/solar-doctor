"""Offline unit tests for scripts/fetch_weights.py (no network: a fake opener serves bytes)."""
from __future__ import annotations

import hashlib
import importlib.util
import http.server
import io
import threading
import urllib.error
import urllib.request
from pathlib import Path

_path = Path(__file__).resolve().parents[1] / "scripts" / "fetch_weights.py"
_spec = importlib.util.spec_from_file_location("fetch_weights", _path)
fw = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fw)

DATA = b"thermal-weights-" * 1000
SHA = hashlib.sha256(DATA).hexdigest()
QUIET = {"log": lambda *_: None, "sleep": lambda *_: None}


class Resp(io.BytesIO):
    def __init__(self, data, status=200):
        super().__init__(data)
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


def opener_serving(data, honour_range=True, seen=None):
    def op(req, timeout=None):
        if seen is not None:
            seen.append(dict(req.header_items()))
        rng = req.get_header("Range")
        if rng and honour_range:
            start = int(rng.split("=")[1].rstrip("-"))
            return Resp(data[start:], 206)
        return Resp(data, 200)
    return op


def test_downloads_and_verifies(tmp_path):
    dest = tmp_path / "c" / "best.pt"
    assert fw.fetch(["http://x/u"], dest, SHA, opener=opener_serving(DATA), **QUIET) == 0
    assert dest.read_bytes() == DATA
    assert not dest.with_name("best.pt.part").exists()


def test_good_file_is_not_touched(tmp_path):
    dest = tmp_path / "best.pt"
    dest.write_bytes(DATA)
    calls = []

    def op(req, timeout=None):
        calls.append(1)
        raise AssertionError("must not hit network")

    assert fw.fetch(["http://x/u"], dest, SHA, opener=op, **QUIET) == 0
    assert not calls


def test_bad_hash_never_creates_dest(tmp_path, capsys):
    dest = tmp_path / "best.pt"
    assert fw.fetch(["http://x/u"], dest, SHA, opener=opener_serving(b"corrupt"), **QUIET) == 1
    assert not dest.exists() and not dest.with_name("best.pt.part").exists()
    assert "sha256 mismatch" in capsys.readouterr().err


def test_existing_bad_file_replaced_only_by_verified_one(tmp_path):
    dest = tmp_path / "best.pt"
    dest.write_bytes(b"lfs pointer")
    assert fw.fetch(["http://x/u"], dest, SHA, opener=opener_serving(b"nope"), **QUIET) == 1
    assert dest.read_bytes() == b"lfs pointer"
    assert fw.fetch(["http://x/u"], dest, SHA, opener=opener_serving(DATA), **QUIET) == 0
    assert dest.read_bytes() == DATA


def test_resume_uses_range(tmp_path):
    dest = tmp_path / "best.pt"
    dest.with_name("best.pt.part").write_bytes(DATA[:5000])
    seen = []
    assert fw.fetch(["http://x/u"], dest, SHA, opener=opener_serving(DATA, seen=seen), **QUIET) == 0
    assert seen[0]["Range"] == "bytes=5000-"
    assert dest.read_bytes() == DATA


def test_server_ignoring_range_restarts(tmp_path):
    dest = tmp_path / "best.pt"
    dest.with_name("best.pt.part").write_bytes(DATA[:5000])
    assert fw.fetch(["http://x/u"], dest, SHA, opener=opener_serving(DATA, honour_range=False), **QUIET) == 0
    assert dest.read_bytes() == DATA


def test_falls_back_to_next_source_and_reports_errors(tmp_path, capsys):
    def op(req, timeout=None):
        if "first" in req.full_url:
            raise urllib.error.HTTPError(req.full_url, 500, "Server Error", {}, None)
        return Resp(DATA)

    assert fw.fetch(["http://x/first", "http://x/second"], tmp_path / "a.pt", SHA, opener=op, **QUIET) == 0
    assert fw.fetch(["http://x/first"], tmp_path / "b.pt", SHA, opener=op, **QUIET) == 1
    assert "500" in capsys.readouterr().err


def test_token_only_sent_to_hf(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "secret")
    assert fw._headers("https://huggingface.co/x", 0)["Authorization"] == "Bearer secret"
    assert "Authorization" not in fw._headers("https://example.com/x", 0)


def test_pinned_constants_and_cli_validation():
    assert fw.EXPECTED_SHA256.startswith("fabb41c88f9d") and len(fw.EXPECTED_SHA256) == 64
    assert fw.main(["--sha256", "abc"]) == 2
