"""Orthomosaic generation jobs backed by a NodeODM processing node.

A generation job is an ordinary `Job` row (id prefix `odm-`) so it shares the
persistence, status vocabulary and restart handling of inspection jobs.
`Job.processed` holds percent complete (total=100) and `Job.message` holds the
current stage while running, or the operator-facing error once failed.

The NodeODM task uuid and request parameters live in a small sidecar,
OUTPUT_DIR/odm/<job_id>/task.json, next to the job's scratch images — that
avoids a schema migration for data only this worker needs.

Stages: extract zip → collect + GPS-check images → submit (init/upload/commit)
→ poll → download orthophoto.tif → register via `_register_ortho` (the same
path a manual GeoTIFF upload takes) → remove the task from NodeODM.
"""
from __future__ import annotations

import json
import logging
import shutil
import threading
import time
import zipfile
from pathlib import Path

from fastapi import HTTPException

from axalon.core.geo import extract_gps_exif
from axalon.core.odm_client import NodeODMClient, NodeODMError, TaskStatus, client_from_env
from axalon.db.models import Job as DbJob
from axalon.db.session import get_session

from axalon.api.support.archives import _safe_extract_zip_with_timeout
from axalon.api.support.orthos import _ortho_path, _register_ortho
from axalon.api.support.paths import OUTPUT_DIR

logger = logging.getLogger("axalon.api")

ODM_JOB_PREFIX = "odm-"
ODM_WORK_DIR = OUTPUT_DIR / "odm"
ODM_SENSORS = ("auto", "rgb", "thermal")
MIN_GPS_IMAGES = 5
ODM_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff"}
NOT_CONFIGURED_MESSAGE = (
    "Orthomosaic generation is disabled: set AXALON_NODEODM_URL to a NodeODM "
    "server (see docs/DEPLOYMENT.md)."
)

_POLL_INTERVAL_S = 15.0
_MAX_CONSECUTIVE_POLL_FAILURES = 20      # ≈5 min of NodeODM being unreachable
_MAX_WAIT_S = 48 * 3600
_TERMINAL_STATES = {"succeeded", "failed", "cancelled"}
_GENERIC_FAILURE = "Orthomosaic generation failed. Check server logs for details."

# Indirection points so tests can run without waiting or a real NodeODM.
_sleep = time.sleep


def get_odm_client() -> NodeODMClient | None:
    return client_from_env()


def odm_capability() -> dict:
    """Capability flag surfaced on /health so the UI can hide the feature."""
    configured = get_odm_client() is not None
    return {"configured": configured, "message": None if configured else NOT_CONFIGURED_MESSAGE}


class _Cancelled(Exception):
    pass


class _JobFailed(Exception):
    """Failure with a message that is safe and useful to show the operator."""


# ── sidecar + job row helpers ────────────────────────────────────────────────
def work_dir(job_id: str) -> Path:
    return ODM_WORK_DIR / job_id


def _write_task_meta(job_id: str, updates: dict) -> None:
    path = work_dir(job_id) / "task.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    meta = {**_read_task_meta(job_id), **updates}
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(meta))
    tmp.replace(path)


def _read_task_meta(job_id: str) -> dict:
    path = work_dir(job_id) / "task.json"
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def ortho_name_for(job_id: str) -> str:
    return f"{job_id.replace('-', '_')}.tif"


def _update_if_active(job_id: str, **fields) -> bool:
    """Write fields unless the job already reached a terminal state.

    Guards against the worker overwriting an operator's cancel that landed
    between two polls. Returns False when the job is no longer active.
    """
    session = get_session()
    try:
        job = session.query(DbJob).filter(DbJob.id == job_id).first()
        if job is None or job.state in _TERMINAL_STATES:
            return False
        for key, value in fields.items():
            setattr(job, key, value)
        session.commit()
        return True
    except Exception:
        session.rollback()
        logger.exception("Failed to persist ODM job state for %s", job_id)
        return True
    finally:
        session.close()


def _job_state(job_id: str) -> str | None:
    session = get_session()
    try:
        job = session.query(DbJob).filter(DbJob.id == job_id).first()
        return job.state if job else None
    finally:
        session.close()


def _stage(job_id: str, message: str, percent: float) -> None:
    if not _update_if_active(
        job_id, state="running", message=message,
        processed=int(max(0.0, min(percent, 99.0))), total=100,
    ):
        raise _Cancelled()


def _raise_if_cancelled(job_id: str) -> None:
    if _job_state(job_id) == "cancelled":
        raise _Cancelled()


# ── image discovery + validation ─────────────────────────────────────────────
def _is_image(path: Path) -> bool:
    return (
        path.suffix.lower() in ODM_IMAGE_EXTS
        and not path.name.startswith(".")
        and "__MACOSX" not in path.parts
    )


def count_zip_images(zf: zipfile.ZipFile) -> int:
    return sum(
        1 for info in zf.infolist()
        if not info.is_dir() and _is_image(Path(info.filename))
    )


def collect_images(root: Path, sensor: str = "auto") -> list[Path]:
    """Pick the image set for one ortho: RGB or thermal, never both.

    A NodeODM task needs a single camera. Mission folders with rgb/ and
    thermal/ subdirectories are split by directory; flat folders (e.g. DJI
    `_T`/`_V` pairs side by side) are split by filename convention.
    """
    from axalon.pipeline.ingest import _is_thermal_name

    root = Path(root)
    all_images = sorted(p for p in root.rglob("*") if p.is_file() and _is_image(p))
    by_dir = {
        kind: [p for p in all_images if kind in {part.lower() for part in p.relative_to(root).parts[:-1]}]
        for kind in ("rgb", "thermal")
    }
    if sensor == "auto":
        if by_dir["rgb"]:
            sensor = "rgb"
        elif by_dir["thermal"]:
            sensor = "thermal"
        else:
            visual = [p for p in all_images if not _is_thermal_name(p.stem)]
            return visual or all_images
    if by_dir["rgb"] or by_dir["thermal"]:
        return by_dir[sensor]
    thermal = {p for p in all_images if _is_thermal_name(p.stem)}
    if sensor == "thermal":
        return sorted(thermal) or all_images
    return [p for p in all_images if p not in thermal] or all_images


def _validated_images(root: Path, sensor: str) -> list[Path]:
    images = collect_images(root, sensor)
    if len(images) < MIN_GPS_IMAGES:
        kind = "" if sensor == "auto" else f"{sensor} "
        raise _JobFailed(
            f"Found {len(images)} usable {kind}images; NodeODM needs at least {MIN_GPS_IMAGES}."
        )
    with_gps = sum(1 for p in images if extract_gps_exif(p) is not None)
    if with_gps < MIN_GPS_IMAGES:
        raise _JobFailed(
            f"Only {with_gps} of {len(images)} images carry GPS EXIF; at least "
            f"{MIN_GPS_IMAGES} geotagged images are needed to georeference the orthomosaic."
        )
    return images


# ── worker ───────────────────────────────────────────────────────────────────
def _poll_until_complete(client: NodeODMClient, job_id: str, task_uuid: str) -> None:
    failures = 0
    started = time.monotonic()
    while True:
        _raise_if_cancelled(job_id)
        try:
            info = client.task_info(task_uuid)
            failures = 0
        except NodeODMError as exc:
            if not exc.transient:
                raise
            failures += 1
            if failures > _MAX_CONSECUTIVE_POLL_FAILURES:
                raise
            info = None

        if info is not None:
            if info.status is TaskStatus.COMPLETED:
                return
            if info.status is TaskStatus.FAILED:
                raise _JobFailed(f"NodeODM task failed: {info.error or 'no error message reported'}")
            if info.status is TaskStatus.CANCELED:
                raise _JobFailed("NodeODM task was cancelled on the processing node.")
            label = (
                "Queued on NodeODM" if info.status is TaskStatus.QUEUED
                else f"Processing on NodeODM ({info.progress:.0f}%)"
            )
            _stage(job_id, label, 5 + info.progress * 0.9)

        if time.monotonic() - started > _MAX_WAIT_S:
            raise _JobFailed("NodeODM task did not finish within 48 hours.")
        _sleep(_POLL_INTERVAL_S)


def _fail(job_id: str, message: str) -> None:
    _update_if_active(job_id, state="failed", message=message)


def run_odm_job(
    job_id: str,
    park_id: str,
    image_root: Path | None,
    *,
    sensor: str,
    options: list[dict],
    zip_path: Path | None = None,
    resume_task_uuid: str | None = None,
) -> None:
    """Background entry point. Never raises; outcome is recorded on the Job row."""
    client = get_odm_client()
    task_uuid = resume_task_uuid
    try:
        if client is None:
            raise _JobFailed(NOT_CONFIGURED_MESSAGE)

        if task_uuid is None:
            if zip_path is not None:
                _stage(job_id, "Extracting images", 0)
                image_root.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(str(zip_path)) as zf:
                    _safe_extract_zip_with_timeout(zf, image_root)
                Path(zip_path).unlink(missing_ok=True)

            _stage(job_id, "Checking images for GPS", 1)
            images = _validated_images(image_root, sensor)

            _stage(job_id, f"Uploading {len(images)} images to NodeODM", 2)
            task_uuid = client.submit_task(f"{park_id} {job_id}", images, options)
            _write_task_meta(job_id, {"task_uuid": task_uuid})

        _stage(job_id, "Queued on NodeODM", 5)
        _poll_until_complete(client, job_id, task_uuid)

        _stage(job_id, "Downloading orthomosaic", 96)
        staged = work_dir(job_id) / "orthophoto.tif.part"
        staged.parent.mkdir(parents=True, exist_ok=True)
        client.download_orthophoto(task_uuid, staged)
        _raise_if_cancelled(job_id)

        _stage(job_id, "Registering orthomosaic", 99)
        name = ortho_name_for(job_id)
        try:
            _register_ortho(park_id, name, staged)
        except HTTPException as exc:
            raise _JobFailed(
                f"NodeODM returned an orthophoto that is not a valid GeoTIFF ({exc.detail})."
            ) from exc

        client.remove_task_quietly(task_uuid)
        _update_if_active(
            job_id, state="succeeded", processed=100, total=100, message=None,
            result_path=str(_ortho_path(park_id, name)),
        )
    except _Cancelled:
        logger.info("ODM job %s cancelled", job_id)
        if task_uuid and client is not None and not _read_task_meta(job_id).get("remote_cancelled"):
            _cancel_remote(client, task_uuid)
    except _JobFailed as exc:
        _fail(job_id, str(exc))
        if task_uuid and client is not None:
            client.remove_task_quietly(task_uuid)
    except NodeODMError as exc:
        logger.warning("ODM job %s failed talking to NodeODM: %s", job_id, exc)
        _fail(job_id, str(exc))
        if task_uuid and client is not None:
            client.remove_task_quietly(task_uuid)
    except Exception:
        logger.exception("ODM job %s failed", job_id)
        _fail(job_id, _GENERIC_FAILURE)
    finally:
        if _job_state(job_id) in _TERMINAL_STATES:
            shutil.rmtree(work_dir(job_id), ignore_errors=True)


def _cancel_remote(client: NodeODMClient, task_uuid: str) -> None:
    try:
        client.cancel_task(task_uuid)
    except Exception:
        logger.warning("Could not cancel NodeODM task %s", task_uuid, exc_info=True)
    client.remove_task_quietly(task_uuid)


def cancel_odm_job(job_id: str) -> bool:
    """Mark a job cancelled and best-effort cancel its NodeODM task.

    Returns False if the job is unknown or already finished. The worker notices
    the state change at its next checkpoint and stops.
    """
    if not _update_if_active(job_id, state="cancelled", message="Cancelled by operator"):
        return False
    task_uuid = _read_task_meta(job_id).get("task_uuid")
    client = get_odm_client()
    if task_uuid and client is not None:
        _cancel_remote(client, task_uuid)
        _write_task_meta(job_id, {"remote_cancelled": True})
    return True


def serialize_odm_job(job: DbJob) -> dict:
    state = job.state
    message = job.message
    return {
        "job_id": job.id,
        "park_id": job.park_id,
        "state": state,
        "progress": 1.0 if state == "succeeded" else round(int(job.processed or 0) / 100, 3),
        "stage": message if state in ("queued", "running") else None,
        "error": message if state == "failed" else None,
        "message": message,
        "ortho_name": Path(job.result_path).name if state == "succeeded" and job.result_path else None,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }


def resume_odm_jobs() -> int:
    """Resume polling of generation jobs interrupted by an API restart.

    Jobs whose NodeODM task was already committed keep processing on the node,
    so polling simply picks up again. Jobs interrupted before submission lost
    their scratch state and are failed with a retry hint. Never raises.
    """
    if get_odm_client() is None:
        return 0
    try:
        session = get_session()
    except Exception:
        logger.exception("Startup: database unreachable — ODM jobs not resumed")
        return 0
    try:
        jobs = session.query(DbJob).filter(
            DbJob.id.like(f"{ODM_JOB_PREFIX}%"),
            DbJob.state.in_(["queued", "running"]),
        ).all()
        pending = [(j.id, j.park_id) for j in jobs]
    except Exception:
        logger.exception("Startup: could not list ODM jobs")
        return 0
    finally:
        session.close()

    resumed = 0
    for job_id, park_id in pending:
        meta = _read_task_meta(job_id)
        task_uuid = meta.get("task_uuid")
        if not task_uuid:
            _fail(job_id, "Interrupted by an API restart before reaching NodeODM — please start it again.")
            shutil.rmtree(work_dir(job_id), ignore_errors=True)
            continue
        threading.Thread(
            target=run_odm_job,
            args=(job_id, park_id, None),
            kwargs={"sensor": meta.get("sensor", "auto"), "options": [], "resume_task_uuid": task_uuid},
            name=f"odm-resume-{job_id}",
            daemon=True,
        ).start()
        resumed += 1
    if resumed:
        logger.info("Resumed %s ODM generation job(s)", resumed)
    return resumed


__all__ = [
    "MIN_GPS_IMAGES",
    "NOT_CONFIGURED_MESSAGE",
    "ODM_JOB_PREFIX",
    "ODM_SENSORS",
    "cancel_odm_job",
    "collect_images",
    "count_zip_images",
    "get_odm_client",
    "odm_capability",
    "ortho_name_for",
    "resume_odm_jobs",
    "run_odm_job",
    "serialize_odm_job",
    "work_dir",
]
