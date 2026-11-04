# drone/agent/handoff.py
"""Post a completed capture to the platform's batch inspection endpoint.

Contract (verified Phase 6 Task 1 against platform/api/app.py:445 `inspect_batch`):
  POST {BASE}/batch                       -> 202
  Authorization: Bearer {token}           (HTTPBearer; enforced when AXALON_API_KEY set)
  multipart/form-data:
    images:     ZIP archive of thermal+RGB image pairs (required, <=2 GB)
    park_id:    str
    altitude_m: float (default 20.0)
  response: {"job_id": "batch-xxxx", "state": "queued", ...}

`transport` is injectable so the POST is unit-tested without a server.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import httpx


def zip_capture(folder: str) -> bytes:
    """Pack a capture folder's files (frames + GPS sidecars) into an in-memory ZIP."""
    buf = io.BytesIO()
    root = Path(folder)
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted(root.iterdir()):
            if p.is_file():
                zf.write(p, arcname=p.name)
    return buf.getvalue()


async def post_handoff(*, base_url: str, token: str, park_id: str, zip_bytes: bytes,
                       altitude_m: float = 20.0,
                       transport: httpx.BaseTransport | None = None,
                       timeout_s: float = 120.0) -> dict:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    files = {"images": ("capture.zip", zip_bytes, "application/zip")}
    data = {"park_id": park_id, "altitude_m": str(altitude_m)}
    async with httpx.AsyncClient(transport=transport, timeout=timeout_s) as client:
        resp = await client.post(
            f"{base_url.rstrip('/')}/batch",
            headers=headers, files=files, data=data)
        resp.raise_for_status()
        return resp.json()
