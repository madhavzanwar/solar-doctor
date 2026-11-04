"""In-memory stand-in for the NodeODM REST API (no network).

Implements the `request(method, url, **kwargs)` surface of `requests.Session`
that `axalon.core.odm_client.NodeODMClient` uses, and records every call so
tests can assert on request sequencing.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from urllib.parse import urlparse

import requests


class FakeResponse:
    def __init__(self, status_code: int = 200, payload=None, body: bytes = b""):
        self.status_code = status_code
        self._payload = payload
        self._body = body if payload is None else json.dumps(payload).encode()
        self.text = self._body.decode("utf-8", errors="replace")

    def json(self):
        if self._payload is None:
            return json.loads(self._body or b"null")
        return self._payload

    def iter_content(self, chunk_size: int = 1024):
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i:i + chunk_size]

    def close(self) -> None:
        pass


@dataclass
class Call:
    method: str
    path: str
    params: dict | None
    data: dict | None
    file_names: list[str]


@dataclass
class FakeNodeODM:
    """Scriptable NodeODM. `info_script` is consumed one entry per /info poll."""

    task_uuid: str = "11111111-2222-3333-4444-555555555555"
    info_script: list = field(default_factory=lambda: [
        {"code": 20, "progress": 10.0},
        {"code": 20, "progress": 60.0},
        {"code": 40, "progress": 100.0},
    ])
    orthophoto: bytes = b"GEOTIFF-BYTES"
    # method+path → list of failures to return before succeeding
    failures: dict = field(default_factory=dict)
    calls: list = field(default_factory=list)

    def request(self, method, url, params=None, data=None, files=None, timeout=None, stream=False, **_):
        path = urlparse(url).path
        names = []
        for item in files or []:
            _field, spec = item
            names.append(spec[0])
        self.calls.append(Call(method, path, params, data, names))

        key = f"{method} {path}"
        pending = self.failures.get(key)
        if pending:
            failure = pending.pop(0)
            if isinstance(failure, Exception):
                raise failure
            return failure

        if method == "GET" and path == "/info":
            return FakeResponse(payload={"version": "2.2.0", "taskQueueCount": 0})
        if method == "POST" and path == "/task/new/init":
            return FakeResponse(payload={"uuid": self.task_uuid})
        if method == "POST" and path.startswith("/task/new/upload/"):
            return FakeResponse(payload={"success": True})
        if method == "POST" and path.startswith("/task/new/commit/"):
            return FakeResponse(payload={"uuid": self.task_uuid})
        if method == "GET" and path.endswith("/info"):
            step = self.info_script.pop(0) if len(self.info_script) > 1 else self.info_script[0]
            status = {"code": step["code"]}
            if "error" in step:
                status["errorMessage"] = step["error"]
            return FakeResponse(payload={
                "uuid": self.task_uuid, "status": status,
                "progress": step.get("progress", 0), "imagesCount": 12,
            })
        if method == "GET" and path.endswith("/download/orthophoto.tif"):
            return FakeResponse(body=self.orthophoto)
        if method == "POST" and path in ("/task/cancel", "/task/remove"):
            return FakeResponse(payload={"success": True})
        return FakeResponse(status_code=404, payload={"error": f"no route {key}"})

    def paths(self) -> list[str]:
        return [f"{c.method} {c.path}" for c in self.calls]


def connection_error() -> Exception:
    return requests.ConnectionError("connection refused")
