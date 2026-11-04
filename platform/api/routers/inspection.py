"""inspection router — extracted from app.py (Plan 01)."""
from __future__ import annotations

from fastapi import APIRouter
from axalon.api.deps import *  # noqa: F401,F403
from axalon.api.schemas.responses import JobStatusOut

router = APIRouter(tags=["inspection"])

@router.post("/inspect")
async def inspect_pair(
    thermal_image: UploadFile = File(..., description="Thermal IR image (JPEG/PNG/TIFF, max 50 MB)"),
    rgb_image: UploadFile | None = File(None, description="RGB image (optional)"),
    park_id: str = Form("unknown"),
    park_mode: str = Form("auto"),
    altitude_m: float = Form(20.0),
    # Optional site metadata — used in PDF/Excel reports
    site_name: str = Form(""),
    client: str = Form(""),
    location: str = Form(""),
    capacity_mw: str = Form(""),
    lat: str = Form(""),
    lon: str = Form(""),
    irradiance_wm2: str = Form(""),
    inspection_time: str = Form(""),
    drone_model: str = Form(""),
    inspection_type: str = Form("maintenance"),
    inspection_level: str = Form("simplified"),
    principal: Principal = Depends(current_principal),
):
    """Inspect a single thermal+RGB image pair."""
    park_id = _validate_park_id(park_id)
    # Scoped users may only add data to parks they can already see; new parks
    # are created unassigned, which is admin-only territory.
    ensure_park_visible(principal, park_id)

    # Validate altitude range
    if not (1.0 <= altitude_m <= 500.0):
        raise HTTPException(status_code=400, detail="altitude_m must be between 1 and 500")

    # Validate thermal file extension
    thermal_name = _safe_filename(thermal_image.filename, "thermal.jpg")
    if Path(thermal_name).suffix.lower() not in _ALLOWED_IMAGE_EXTS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported thermal image format. Allowed: {', '.join(_ALLOWED_IMAGE_EXTS)}",
        )

    # Read with size limit
    thermal_bytes = await thermal_image.read()
    if len(thermal_bytes) > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Thermal image exceeds 50 MB limit")

    rgb_bytes = None
    rgb_name = None
    if rgb_image:
        rgb_name = _safe_filename(rgb_image.filename, "rgb.jpg")
        if Path(rgb_name).suffix.lower() not in _ALLOWED_IMAGE_EXTS:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported RGB image format. Allowed: {', '.join(_ALLOWED_IMAGE_EXTS)}",
            )
        rgb_bytes = await rgb_image.read()
        if len(rgb_bytes) > _MAX_IMAGE_BYTES:
            raise HTTPException(status_code=413, detail="RGB image exceeds 50 MB limit")

    site_meta = {
        "site_name":        site_name or park_id,
        "client":           client,
        "location":         location,
        "capacity_mw":      capacity_mw,
        "lat":              lat,
        "lon":              lon,
        "irradiance_wm2":   irradiance_wm2,
        "inspection_time":  inspection_time,
        "drone_model":      drone_model,
        "inspection_type":  inspection_type,
        "inspection_level": inspection_level,
    }

    with tempfile.TemporaryDirectory() as tmpdir:
        thermal_path = Path(tmpdir) / thermal_name
        thermal_path.write_bytes(thermal_bytes)

        rgb_path = None
        if rgb_bytes is not None and rgb_name:
            rgb_path = Path(tmpdir) / rgb_name
            rgb_path.write_bytes(rgb_bytes)

        orch = get_orchestrator()
        result = orch.inspect_pair(
            thermal_path=thermal_path,
            rgb_path=rgb_path,
            park_id=park_id,
            altitude_m=altitude_m,
        )

    result["site_meta"] = site_meta
    _update_job(
        result["job_id"],
        park_id=park_id,
        state="succeeded",
        processed=1,
        total=1,
        message=None,
    )
    return JSONResponse(content={
        "job_id": result["job_id"],
        "status": "completed",
        "total_detections": result["total_detections"],
        "summary": result["summary"],
        "detections": result["detections"],
        "rgb_filename": Path(result.get("annotated_rgb") or "").name,
        "warnings": _check_iec_warnings(site_meta),
    })


@router.post("/batch", status_code=202)
async def inspect_batch(
    background_tasks: BackgroundTasks,
    images: UploadFile = File(..., description="ZIP archive of thermal+RGB image pairs (max 2 GB)"),
    park_id: str = Form("unknown"),
    park_mode: str = Form("auto"),
    altitude_m: float = Form(20.0),
    # Optional site metadata — used in PDF/Excel reports
    site_name: str = Form(""),
    client: str = Form(""),
    location: str = Form(""),
    capacity_mw: str = Form(""),
    lat: str = Form(""),
    lon: str = Form(""),
    irradiance_wm2: str = Form(""),
    inspection_time: str = Form(""),
    drone_model: str = Form(""),
    inspection_type: str = Form("maintenance"),
    inspection_level: str = Form("simplified"),
    principal: Principal = Depends(current_principal),
):
    """Submit a batch inspection job (runs in background)."""
    park_id = _validate_park_id(park_id)
    ensure_park_visible(principal, park_id)

    if not (1.0 <= altitude_m <= 500.0):
        raise HTTPException(status_code=400, detail="altitude_m must be between 1 and 500")

    # Validate it's actually a zip
    zip_name = _safe_filename(images.filename, "batch.zip")
    if Path(zip_name).suffix.lower() != ".zip":
        raise HTTPException(status_code=400, detail="Only ZIP archives are accepted for batch upload")

    zip_bytes = await images.read()
    if len(zip_bytes) > _MAX_ZIP_BYTES:
        raise HTTPException(status_code=413, detail="ZIP archive exceeds 2 GB limit")

    # Validate zip integrity + bomb metadata before accepting
    try:
        import io
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            infos = zf.infolist()
            if len(infos) > _MAX_ZIP_MEMBERS:
                raise HTTPException(
                    status_code=400,
                    detail=f"ZIP contains too many files ({len(infos)} > {_MAX_ZIP_MEMBERS})",
                )
            declared_uncompressed = sum(i.file_size for i in infos)
            if declared_uncompressed > _MAX_ZIP_UNCOMPRESSED_BYTES:
                raise HTTPException(
                    status_code=400,
                    detail="ZIP archive declared uncompressed size exceeds the allowed limit",
                )
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid ZIP archive")

    site_meta = {
        "site_name":        site_name or park_id,
        "client":           client,
        "location":         location,
        "capacity_mw":      capacity_mw,
        "lat":              lat,
        "lon":              lon,
        "irradiance_wm2":   irradiance_wm2,
        "inspection_time":  inspection_time,
        "drone_model":      drone_model,
        "inspection_type":  inspection_type,
        "inspection_level": inspection_level,
    }

    job_id = f"batch-{uuid.uuid4().hex[:8]}"
    tmp_zip = OUTPUT_DIR / f"{job_id}.zip"
    tmp_zip.write_bytes(zip_bytes)

    _create_job(job_id, park_id)

    background_tasks.add_task(_run_batch_job, job_id, tmp_zip, park_id, altitude_m, site_meta)

    return {"job_id": job_id, "state": "queued", "status": "queued",
            "message": "Batch job queued. Poll GET /status/{job_id} for progress.",
            "warnings": _check_iec_warnings(site_meta)}


@router.get("/status/{job_id}", response_model=JobStatusOut)
def get_status(job_id: str, principal: Principal = Depends(current_principal)):
    """Get the status and progress of an inspection job."""
    job_id = _validate_job_id(job_id)
    ensure_job_visible(principal, job_id)
    job = _get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return {
        "job_id": job_id,
        "state": job.get("state"),
        "status": job.get("status"),
        "progress": job.get("progress", 0.0),
        "processed": job.get("processed", 0),
        "total": job.get("total", 0),
        "message": job.get("message"),
        # Only expose error message if present — message is already sanitised
        **({"error": job["error"]} if "error" in job else {}),
    }


@router.get("/report/{job_id}")
def download_report(job_id: str, format: str = "json", principal: Principal = Depends(current_principal)):
    """Download the inspection report in the requested format."""
    job_id = _validate_job_id(job_id)
    ensure_job_visible(principal, job_id)

    job = _get_job(job_id)
    if job is None or job.get("status") != "completed":
        raise HTTPException(status_code=404, detail="Job not found or not yet complete")

    entry = _REPORT_FORMAT_MAP.get(format)
    if entry is None:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown format '{format}'. Use: {', '.join(_REPORT_FORMAT_MAP)}",
        )

    filename, media_type = entry
    # Construct path from whitelist — not from user input
    report_path = (OUTPUT_DIR / job_id / filename).resolve()
    corrections = _corrections_for_job(job_id)

    # Final safety: ensure path is still inside OUTPUT_DIR
    if not str(report_path).startswith(str(OUTPUT_DIR.resolve())):
        raise HTTPException(status_code=403, detail="Access denied")

    if format == "json":
        if report_path.exists():
            try:
                report_data = json.loads(report_path.read_text())
            except (json.JSONDecodeError, OSError):
                logger.exception("Failed to read JSON report for %s", job_id)
                report_data = {}
        else:
            report_data = {
                "inspection_id": job_id,
                "job_id": job_id,
                "park_id": job.get("park_id"),
                "summary": {},
                "detections": [],
            }
        report_data["corrections"] = corrections
        return JSONResponse(content=report_data)

    if not report_path.exists():
        raise HTTPException(status_code=404, detail=f"Report not yet generated for format: {format}")

    return FileResponse(path=str(report_path), filename=filename, media_type=media_type)
