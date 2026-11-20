"""RGB vision router: model info, defect prediction and explanations (contract: docs/solardoctor/interfaces/vision-predict.md)."""
from __future__ import annotations

import io
import logging
from typing import Literal

from fastapi import APIRouter, File, HTTPException, Query, Request, UploadFile
from fastapi.routing import APIRoute
from PIL import Image
from starlette.concurrency import run_in_threadpool

from solardoctor.vision import VisionModelUnavailable, get_classifier

logger = logging.getLogger("solardoctor.api")
MAX_UPLOAD_BYTES = 15 * 1024 * 1024
MULTIPART_ALLOWANCE = 64 * 1024  # boundaries + headers around the file part


class _EarlyLimitRoute(APIRoute):
    """413 on an oversized Content-Length, and on any body stream that exceeds the cap (chunked, no Content-Length)."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guarded(request: Request):
            declared = request.headers.get("content-length", "")
            if declared.isdigit() and int(declared) > MAX_UPLOAD_BYTES + MULTIPART_ALLOWANCE:
                raise HTTPException(status_code=413, detail="image exceeds 15 MB limit")
            orig, received = request._receive, 0

            async def counting():
                nonlocal received
                msg = await orig()
                if msg["type"] == "http.request":
                    received += len(msg.get("body", b""))
                    if received > MAX_UPLOAD_BYTES + MULTIPART_ALLOWANCE:  # stops the multipart parser spooling more
                        raise HTTPException(status_code=413, detail="image exceeds 15 MB limit")
                return msg
            request._receive = counting
            return await handler(request)
        return guarded


router = APIRouter(prefix="/vision", tags=["vision"], route_class=_EarlyLimitRoute)

MAX_PIXELS = 50_000_000
_FORMATS = {"JPEG", "MPO", "PNG", "WEBP"}  # MPO = JPEG with an MPF marker (phone/camera photos)


async def _classifier():
    try:
        return await run_in_threadpool(get_classifier)
    except VisionModelUnavailable as exc:
        logger.warning("RGB model unavailable: %s", exc)
        raise HTTPException(status_code=503, detail="rgb_model_unavailable") from exc


async def _read_image(file: UploadFile) -> bytes:
    """Read at most 15 MB in chunks and check, by sniffing the bytes, that it is a JPEG/PNG/WebP of sane size."""
    chunks, total = [], 0
    while chunk := await file.read(1 << 20):
        total += len(chunk)
        if total > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="image exceeds 15 MB limit")
        chunks.append(chunk)
    data = b"".join(chunks)
    if not data:
        raise HTTPException(status_code=400, detail="empty upload")
    try:
        with Image.open(io.BytesIO(data)) as im:
            fmt, (w, h) = im.format, im.size
    except Exception:
        raise HTTPException(status_code=422, detail="not a decodable image") from None
    if fmt not in _FORMATS or w * h > MAX_PIXELS:
        raise HTTPException(status_code=422, detail="unsupported image (JPEG/PNG/WebP up to 50 MP)")
    return data


@router.get("/model")
async def model_info():
    return (await _classifier()).info()


@router.post("/predict")
async def predict(file: UploadFile = File(..., description="JPEG/PNG/WebP, max 15 MB")):
    data = await _read_image(file)
    clf = await _classifier()
    try:
        return await run_in_threadpool(clf.predict, data)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/explain")
async def explain(
    file: UploadFile = File(..., description="JPEG/PNG/WebP, max 15 MB"),
    method: Literal["gradcam", "lime"] = Query("gradcam"),
    num_samples: int = Query(600, ge=50, le=2000),
    top_k: int = Query(5, ge=1, le=20),
):
    data = await _read_image(file)
    clf = await _classifier()
    try:
        return await run_in_threadpool(clf.explain, data, method, num_samples, top_k)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
