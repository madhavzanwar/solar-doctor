"""ortho_generate router — build orthomosaics in-platform via NodeODM.

The operator either uploads a ZIP of drone images or points at an existing
inspection job whose images are already on disk. The heavy lifting happens in
axalon.api.support.odm_jobs as a background Job; this router validates input
and exposes status/cancel.
"""
from __future__ import annotations

from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool
from axalon.api.deps import *  # noqa: F401,F403
from axalon.api.support.odm_jobs import (
    MIN_GPS_IMAGES,
    NOT_CONFIGURED_MESSAGE,
    ODM_JOB_PREFIX,
    ODM_SENSORS,
    _write_task_meta,
    cancel_odm_job,
    collect_images,
    count_zip_images,
    get_odm_client,
    run_odm_job,
    serialize_odm_job,
    work_dir,
)
from axalon.core.odm_client import build_task_options

router = APIRouter(tags=["ortho"])

_UPLOAD_CHUNK_BYTES = 1024 * 1024
_LIST_LIMIT = 20


def _load_park_odm_job(park_id: str, job_id: str) -> DbJob:
    job_id = _validate_job_id(job_id)
    session = get_session()
    try:
        job = session.query(DbJob).filter(DbJob.id == job_id).first()
    finally:
        session.close()
    if job is None or not job.id.startswith(ODM_JOB_PREFIX) or job.park_id != park_id:
        raise HTTPException(status_code=404, detail="Generation job not found")
    return job


async def _stage_upload(upload: UploadFile, dest: Path) -> None:
    """Stream the ZIP to disk (never fully in memory) and check it before queuing."""
    if Path(_safe_filename(upload.filename, "images.zip")).suffix.lower() != ".zip":
        raise HTTPException(status_code=400, detail="Upload a .zip archive of drone images")
    dest.parent.mkdir(parents=True, exist_ok=True)
    total = 0
    with dest.open("wb") as out:
        while chunk := await upload.read(_UPLOAD_CHUNK_BYTES):
            total += len(chunk)
            if total > _MAX_ZIP_BYTES:
                raise HTTPException(status_code=413, detail="ZIP archive exceeds 2 GB limit")
            out.write(chunk)
    try:
        with zipfile.ZipFile(str(dest)) as zf:
            infos = zf.infolist()
            if len(infos) > _MAX_ZIP_MEMBERS:
                raise HTTPException(
                    status_code=400,
                    detail=f"ZIP contains too many files ({len(infos)} > {_MAX_ZIP_MEMBERS})",
                )
            if sum(i.file_size for i in infos) > _MAX_ZIP_UNCOMPRESSED_BYTES:
                raise HTTPException(
                    status_code=400,
                    detail="ZIP archive declared uncompressed size exceeds the allowed limit",
                )
            image_count = count_zip_images(zf)
    except zipfile.BadZipFile:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid ZIP archive")
    if image_count < MIN_GPS_IMAGES:
        raise HTTPException(
            status_code=400,
            detail=f"ZIP holds {image_count} images (.jpg/.png/.tif); at least {MIN_GPS_IMAGES} are needed",
        )


def _source_job_images(park_id: str, source_job_id: str, sensor: str) -> Path:
    source_job_id = _validate_job_id(source_job_id)
    session = get_session()
    try:
        source = session.query(DbJob).filter(DbJob.id == source_job_id).first()
    finally:
        session.close()
    root = (OUTPUT_DIR / source_job_id).resolve()
    if (
        source is None
        or (source.park_id and source.park_id != park_id)
        or not root.is_relative_to(OUTPUT_DIR.resolve())
        or not root.is_dir()
    ):
        raise HTTPException(status_code=404, detail="Source job not found or its images were cleaned up")
    found = len(collect_images(root, sensor))
    if found < MIN_GPS_IMAGES:
        raise HTTPException(
            status_code=400,
            detail=f"Source job has {found} usable images; at least {MIN_GPS_IMAGES} are needed",
        )
    return root


@router.get("/parks/{park_id}/orthos/generate")
def list_ortho_generation_jobs(park_id: str, principal: Principal = Depends(current_principal)):
    """Recent orthomosaic generation jobs for a park, newest first."""
    park_id = _validate_park_id(park_id)
    ensure_park_visible(principal, park_id)
    session = get_session()
    try:
        jobs = (
            session.query(DbJob)
            .filter(DbJob.id.like(f"{ODM_JOB_PREFIX}%"), DbJob.park_id == park_id)
            .order_by(DbJob.created_at.desc())
            .limit(_LIST_LIMIT)
            .all()
        )
        return {"park_id": park_id, "jobs": [serialize_odm_job(j) for j in jobs]}
    finally:
        session.close()


@router.post("/parks/{park_id}/orthos/generate", status_code=202)
async def generate_ortho(
    park_id: str,
    background_tasks: BackgroundTasks,
    images: UploadFile | None = File(None, description="ZIP of geotagged drone images"),
    source_job_id: str | None = Form(None, description="Reuse the images of an existing inspection job"),
    sensor: str = Form("auto", description="auto | rgb | thermal — one camera per ortho"),
    orthophoto_resolution_cm: float = Form(2.0),
    fast_orthophoto: bool = Form(True),
    dsm: bool = Form(False),
    principal: Principal = Depends(current_principal),
):
    """Queue a NodeODM task that stitches images into a GeoTIFF orthomosaic."""
    park_id = _validate_park_id(park_id)
    ensure_park_visible(principal, park_id)
    if get_odm_client() is None:
        raise HTTPException(status_code=503, detail=NOT_CONFIGURED_MESSAGE)
    if source_job_id:
        ensure_job_visible(principal, source_job_id)

    has_upload = images is not None and bool(images.filename)
    if has_upload == bool(source_job_id):
        raise HTTPException(
            status_code=400, detail="Provide either an images ZIP or source_job_id, not both",
        )
    if sensor not in ODM_SENSORS:
        raise HTTPException(status_code=400, detail=f"sensor must be one of: {', '.join(ODM_SENSORS)}")
    try:
        options = build_task_options(
            orthophoto_resolution_cm=orthophoto_resolution_cm,
            fast_orthophoto=fast_orthophoto, dsm=dsm,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    job_id = f"{ODM_JOB_PREFIX}{uuid.uuid4().hex[:12]}"
    scratch = work_dir(job_id)
    zip_path: Path | None = None
    try:
        if has_upload:
            zip_path = scratch / "upload.zip"
            await _stage_upload(images, zip_path)
            image_root = scratch / "images"
        else:
            # Walking a large inspection folder is blocking I/O — keep it off the event loop.
            image_root = await run_in_threadpool(_source_job_images, park_id, source_job_id, sensor)
    except HTTPException:
        shutil.rmtree(scratch, ignore_errors=True)
        raise
    except Exception:
        shutil.rmtree(scratch, ignore_errors=True)
        logger.exception("Failed to stage ODM upload")
        raise HTTPException(status_code=500, detail="Failed to store uploaded file")

    _create_job(job_id, park_id)
    _update_job(job_id, total=100, message="Queued")
    _write_task_meta(job_id, {
        "sensor": sensor, "source_job_id": source_job_id,
        "options": options,
    })
    background_tasks.add_task(
        run_odm_job, job_id, park_id, image_root,
        sensor=sensor, options=options, zip_path=zip_path,
    )
    return serialize_odm_job(_load_park_odm_job(park_id, job_id))


@router.get("/parks/{park_id}/orthos/generate/{job_id}")
def get_ortho_generation_status(park_id: str, job_id: str, principal: Principal = Depends(current_principal)):
    park_id = _validate_park_id(park_id)
    ensure_park_visible(principal, park_id)
    return serialize_odm_job(_load_park_odm_job(park_id, job_id))


@router.delete("/parks/{park_id}/orthos/generate/{job_id}")
def cancel_ortho_generation(park_id: str, job_id: str, principal: Principal = Depends(current_principal)):
    """Cancel a queued or running generation and its NodeODM task."""
    park_id = _validate_park_id(park_id)
    ensure_park_visible(principal, park_id)
    job = _load_park_odm_job(park_id, job_id)
    if not cancel_odm_job(job.id):
        raise HTTPException(status_code=409, detail=f"Job already {job.state}")
    return serialize_odm_job(_load_park_odm_job(park_id, job.id))
