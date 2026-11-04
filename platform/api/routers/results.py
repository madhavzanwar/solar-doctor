"""results router — extracted from app.py (Plan 01)."""
from __future__ import annotations

from fastapi import APIRouter
from axalon.api.deps import *  # noqa: F401,F403

router = APIRouter(tags=["results"])

@router.get("/results/{job_id}/{filename}")
def serve_result_image(job_id: str, filename: str, principal: Principal = Depends(current_principal)):
    """Serve an annotated image from a completed job's output directory."""
    job_id = _validate_job_id(job_id)
    ensure_job_visible(principal, job_id, detail="Image not found")
    filename = _safe_filename(filename, "")
    if not filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    image_path = (OUTPUT_DIR / job_id / filename).resolve()
    job_dir = (OUTPUT_DIR / job_id).resolve()
    if not str(image_path).startswith(str(job_dir)):
        raise HTTPException(status_code=403, detail="Access denied")
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    mime, _ = mimetypes.guess_type(str(image_path))
    return FileResponse(str(image_path), media_type=mime or "image/jpeg")


@router.get("/image/{job_id}/{filename}")
def get_job_image(job_id: str, filename: str, principal: Principal = Depends(current_principal)):
    """Serve an annotated thermal/RGB image produced by the pipeline.

    Strictly bounded:
      - job_id and filename go through regex validation
      - resolved path must stay inside OUTPUT_DIR/job_id
      - filename must end in one of the orchestrator's known suffixes
    """
    job_id = _validate_job_id(job_id)
    ensure_job_visible(principal, job_id, detail="Image not found")
    if not _FILENAME_RE.match(filename) or not filename.endswith(_IMAGE_SUFFIXES):
        raise HTTPException(status_code=400, detail="Invalid image filename")

    job_dir = (OUTPUT_DIR / job_id).resolve()
    image_path = (job_dir / filename).resolve()

    if not str(image_path).startswith(str(job_dir)):
        raise HTTPException(status_code=403, detail="Access denied")
    if not image_path.exists():
        raise HTTPException(status_code=404, detail="Image not found")

    return FileResponse(path=str(image_path), media_type="image/jpeg")
