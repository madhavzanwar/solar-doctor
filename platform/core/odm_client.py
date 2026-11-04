"""Thin typed client for the NodeODM REST API (OpenDroneMap processing node).

Reference: https://github.com/OpenDroneMap/NodeODM/blob/master/docs/index.adoc

A task goes init → upload (images in chunks) → commit → poll /info → download
orthophoto.tif → remove. Transient failures (connection errors, timeouts, 5xx,
429) are retried with exponential backoff; everything else raises immediately
so a bad token or a rejected image set surfaces as a clear error.

Configured with AXALON_NODEODM_URL (+ optional AXALON_NODEODM_TOKEN). When the
URL is unset `client_from_env()` returns None and the feature is disabled.
"""
from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable

import requests

logger = logging.getLogger("axalon.odm")

DEFAULT_TIMEOUT = (5.0, 60.0)          # (connect, read) seconds
UPLOAD_TIMEOUT = (5.0, 900.0)          # large image batches take a while
DOWNLOAD_TIMEOUT = (5.0, 900.0)
DEFAULT_UPLOAD_CHUNK = 20              # images per upload request
DEFAULT_MAX_RETRIES = 4
_DOWNLOAD_CHUNK_BYTES = 1024 * 1024
_TRANSIENT_HTTP = {408, 425, 429, 500, 502, 503, 504}

MIN_RESOLUTION_CM = 0.5
MAX_RESOLUTION_CM = 50.0


class NodeODMError(RuntimeError):
    """A NodeODM call failed. `transient` is True when retrying later may help."""

    def __init__(self, message: str, *, transient: bool = False, status_code: int | None = None):
        super().__init__(message)
        self.transient = transient
        self.status_code = status_code


class TaskStatus(Enum):
    QUEUED = 10
    RUNNING = 20
    FAILED = 30
    COMPLETED = 40
    CANCELED = 50


_TERMINAL = {TaskStatus.FAILED, TaskStatus.COMPLETED, TaskStatus.CANCELED}


@dataclass(frozen=True)
class TaskInfo:
    uuid: str
    status: TaskStatus
    progress: float            # 0–100
    error: str | None = None
    images_count: int | None = None

    @property
    def is_terminal(self) -> bool:
        return self.status in _TERMINAL


def build_task_options(
    *,
    orthophoto_resolution_cm: float = 2.0,
    fast_orthophoto: bool = True,
    dsm: bool = False,
) -> list[dict]:
    """NodeODM options tuned for flat, repetitive solar-farm imagery.

    fast-orthophoto skips the dense point cloud — solar parks are essentially
    planar, so it cuts processing time by several times with little loss in
    ortho quality. The 3D model and DSM are skipped unless asked for.
    """
    if not (MIN_RESOLUTION_CM <= float(orthophoto_resolution_cm) <= MAX_RESOLUTION_CM):
        raise ValueError(
            f"orthophoto_resolution_cm must be between {MIN_RESOLUTION_CM} and {MAX_RESOLUTION_CM}"
        )
    return [
        {"name": "orthophoto-resolution", "value": float(orthophoto_resolution_cm)},
        {"name": "fast-orthophoto", "value": bool(fast_orthophoto)},
        {"name": "dsm", "value": bool(dsm)},
        {"name": "skip-3dmodel", "value": True},
        {"name": "auto-boundary", "value": True},
    ]


def _parse_task_info(task_uuid: str, payload: dict) -> TaskInfo:
    status_obj = payload.get("status") or {}
    code = status_obj.get("code") if isinstance(status_obj, dict) else status_obj
    try:
        status = TaskStatus(int(code))
    except (TypeError, ValueError) as exc:
        raise NodeODMError(f"Unrecognised NodeODM task status: {code!r}") from exc
    try:
        progress = float(payload.get("progress") or 0.0)
    except (TypeError, ValueError):
        progress = 0.0
    error = status_obj.get("errorMessage") if isinstance(status_obj, dict) else None
    return TaskInfo(
        uuid=str(payload.get("uuid") or task_uuid),
        status=status,
        progress=min(max(progress, 0.0), 100.0),
        error=error or None,
        images_count=payload.get("imagesCount"),
    )


class NodeODMClient:
    def __init__(
        self,
        base_url: str,
        token: str | None = None,
        *,
        session=None,
        timeout: tuple[float, float] = DEFAULT_TIMEOUT,
        upload_chunk_size: int = DEFAULT_UPLOAD_CHUNK,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_s: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ):
        if not base_url:
            raise ValueError("NodeODM base_url is required")
        if upload_chunk_size < 1:
            raise ValueError("upload_chunk_size must be >= 1")
        self.base_url = base_url.rstrip("/")
        self.token = token or None
        self._session = session if session is not None else requests.Session()
        self._timeout = timeout
        self._chunk = upload_chunk_size
        self._max_retries = max(0, max_retries)
        self._backoff_s = backoff_s
        self._sleep = sleep

    # ── transport ────────────────────────────────────────────────────────────
    def _request(self, method: str, path: str, *, files_factory=None, **kwargs):
        """Send one request with retry on transient failures.

        `files_factory` rebuilds the multipart file list per attempt, because a
        file handle consumed by a failed attempt cannot be re-sent.
        """
        url = f"{self.base_url}{path}"
        params = dict(kwargs.pop("params", None) or {})
        if self.token:
            params["token"] = self.token
        kwargs.setdefault("timeout", self._timeout)

        last_error: NodeODMError | None = None
        for attempt in range(self._max_retries + 1):
            if attempt:
                self._sleep(self._backoff_s * (2 ** (attempt - 1)))
            opened: list = []
            try:
                if files_factory is not None:
                    files, opened = files_factory()
                    kwargs["files"] = files
                response = self._session.request(method, url, params=params or None, **kwargs)
            except (requests.ConnectionError, requests.Timeout) as exc:
                last_error = NodeODMError(
                    f"NodeODM unreachable ({method} {path}): {exc.__class__.__name__}",
                    transient=True,
                )
                logger.warning("%s (attempt %s)", last_error, attempt + 1)
                continue
            finally:
                for handle in opened:
                    handle.close()

            if response.status_code in _TRANSIENT_HTTP:
                last_error = NodeODMError(
                    f"NodeODM returned HTTP {response.status_code} for {method} {path}",
                    transient=True, status_code=response.status_code,
                )
                logger.warning("%s (attempt %s)", last_error, attempt + 1)
                response.close()
                continue
            if response.status_code >= 400:
                detail = _error_detail(response)
                response.close()
                raise NodeODMError(
                    f"NodeODM rejected {method} {path} (HTTP {response.status_code}): {detail}",
                    status_code=response.status_code,
                )
            return response
        assert last_error is not None
        raise last_error

    def _json(self, method: str, path: str, **kwargs) -> dict:
        response = self._request(method, path, **kwargs)
        try:
            payload = response.json()
        except ValueError as exc:
            raise NodeODMError(f"NodeODM sent a non-JSON response for {method} {path}") from exc
        if isinstance(payload, dict) and payload.get("error"):
            raise NodeODMError(f"NodeODM error on {method} {path}: {payload['error']}")
        return payload if isinstance(payload, dict) else {"value": payload}

    # ── API ──────────────────────────────────────────────────────────────────
    def info(self) -> dict:
        return self._json("GET", "/info")

    def init_task(self, name: str, options: list[dict]) -> str:
        payload = self._json(
            "POST", "/task/new/init",
            data={"name": name, "options": json.dumps(options)},
        )
        task_uuid = payload.get("uuid")
        if not task_uuid:
            raise NodeODMError("NodeODM did not return a task uuid")
        return str(task_uuid)

    def upload_images(self, task_uuid: str, images: Iterable[Path]) -> None:
        paths = [Path(p) for p in images]
        for start in range(0, len(paths), self._chunk):
            batch = paths[start:start + self._chunk]

            def files_factory(batch=batch):
                handles = [p.open("rb") for p in batch]
                files = [
                    ("images", (p.name, h, "application/octet-stream"))
                    for p, h in zip(batch, handles)
                ]
                return files, handles

            self._json(
                "POST", f"/task/new/upload/{task_uuid}",
                files_factory=files_factory, timeout=UPLOAD_TIMEOUT,
            )

    def commit_task(self, task_uuid: str) -> None:
        self._json("POST", f"/task/new/commit/{task_uuid}")

    def submit_task(self, name: str, images: Iterable[Path], options: list[dict]) -> str:
        """init → chunked upload → commit. Removes the task if upload/commit fails."""
        task_uuid = self.init_task(name, options)
        try:
            self.upload_images(task_uuid, images)
            self.commit_task(task_uuid)
        except Exception:
            self.remove_task_quietly(task_uuid)
            raise
        return task_uuid

    def task_info(self, task_uuid: str) -> TaskInfo:
        return _parse_task_info(task_uuid, self._json("GET", f"/task/{task_uuid}/info"))

    def download_orthophoto(self, task_uuid: str, dest: Path) -> int:
        """Stream orthophoto.tif to `dest`. Returns bytes written."""
        response = self._request(
            "GET", f"/task/{task_uuid}/download/orthophoto.tif",
            stream=True, timeout=DOWNLOAD_TIMEOUT,
        )
        written = 0
        try:
            with Path(dest).open("wb") as out:
                for chunk in response.iter_content(chunk_size=_DOWNLOAD_CHUNK_BYTES):
                    if chunk:
                        out.write(chunk)
                        written += len(chunk)
        finally:
            response.close()
        if written == 0:
            raise NodeODMError("NodeODM returned an empty orthophoto")
        return written

    def cancel_task(self, task_uuid: str) -> None:
        self._json("POST", "/task/cancel", data={"uuid": task_uuid})

    def remove_task(self, task_uuid: str) -> None:
        self._json("POST", "/task/remove", data={"uuid": task_uuid})

    def remove_task_quietly(self, task_uuid: str) -> None:
        try:
            self.remove_task(task_uuid)
        except Exception:
            logger.warning("Could not remove NodeODM task %s", task_uuid, exc_info=True)


def _error_detail(response) -> str:
    try:
        payload = response.json()
        if isinstance(payload, dict) and payload.get("error"):
            return str(payload["error"])[:300]
    except ValueError:
        pass
    return (getattr(response, "text", "") or "")[:300]


def client_from_env() -> NodeODMClient | None:
    """Build a client from AXALON_NODEODM_URL / AXALON_NODEODM_TOKEN, or None."""
    url = os.environ.get("AXALON_NODEODM_URL", "").strip()
    if not url:
        return None
    token = os.environ.get("AXALON_NODEODM_TOKEN", "").strip() or None
    return NodeODMClient(url, token)


__all__ = [
    "NodeODMClient",
    "NodeODMError",
    "TaskInfo",
    "TaskStatus",
    "build_task_options",
    "client_from_env",
]
