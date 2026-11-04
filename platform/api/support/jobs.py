"""Inspection job lifecycle: state persistence, the batch worker, and cleanup.

`_run_batch_job` is the entry point BackgroundTasks schedules for an uploaded
archive; everything else here reads or writes the Job row backing it.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from axalon.core.alerts import notify_inspection_complete
from axalon.db.models import Correction, Job as DbJob
from axalon.db.session import get_session
from axalon.reporting.geojson_writer import write_geojson
from axalon.reporting.report import (
    generate_excel_report,
    generate_json_report,
    generate_pdf_report,
)

from axalon.api.serializers import _serialize_correction
from axalon.api.support.archives import _safe_extract_zip_with_timeout
from axalon.api.support.orchestrator import get_orchestrator
from axalon.api.support.paths import OUTPUT_DIR

logger = logging.getLogger("axalon.api")

_REPORT_FORMAT_MAP = {
    "pdf":     ("inspection_report.pdf",        "application/pdf"),
    "json":    ("inspection_report.json",       "application/json"),
    "excel":   ("inspection_report.xlsx",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "geojson": ("park_anomaly_map.geojson",      "application/geo+json"),
}

# Job.state (storage) ←→ status (wire) are different vocabularies.
_STATUS_TO_STATE = {
    "queued": "queued",
    "processing": "running",
    "running": "running",
    "completed": "succeeded",
    "succeeded": "succeeded",
    "failed": "failed",
    "cancelled": "cancelled",
}
_STATE_TO_STATUS = {
    "queued": "queued",
    "running": "processing",
    "succeeded": "completed",
    "failed": "failed",
    "cancelled": "cancelled",
}


def _state_from_status(status: str | None) -> str:
    return _STATUS_TO_STATE.get(status or "", status or "queued")


def _update_job(job_id: str, **fields) -> None:
    session = get_session()
    try:
        job = session.query(DbJob).filter(DbJob.id == job_id).first()
        if job is None:
            job = DbJob(id=job_id)
            session.add(job)
        if "status" in fields and "state" not in fields:
            fields["state"] = _state_from_status(str(fields.pop("status")))
        if "progress" in fields:
            fields.pop("progress")
        if "error" in fields and "message" not in fields:
            fields["message"] = fields.pop("error")
        for key, value in fields.items():
            if hasattr(job, key):
                setattr(job, key, value)
        session.commit()
    except Exception:
        logger.exception("Failed to persist job state for %s", job_id)
    finally:
        session.close()


def _create_job(job_id: str, park_id: str | None = None) -> None:
    _update_job(job_id, park_id=park_id, state="queued", processed=0, total=0, message=None)


def _get_job(job_id: str) -> dict | None:
    session = get_session()
    try:
        job = session.query(DbJob).filter(DbJob.id == job_id).first()
        if job is None:
            return None
        total = int(job.total or 0)
        processed = int(job.processed or 0)
        progress = round(processed / total, 2) if total else (1.0 if job.state == "succeeded" else 0.0)
        return {
            "job_id": job.id,
            "state": job.state,
            "status": _STATE_TO_STATUS.get(job.state, job.state),
            "progress": progress,
            "processed": processed,
            "total": total,
            "message": job.message,
            "error": job.message,
            "park_id": job.park_id,
            "result_path": job.result_path,
        }
    finally:
        session.close()


def _corrections_for_job(job_id: str) -> list[dict]:
    session = get_session()
    try:
        rows = session.query(Correction).filter(Correction.job_id == job_id).all()
        return [_serialize_correction(row) for row in rows]
    except Exception:
        logger.exception("Failed to load corrections for report %s", job_id)
        return []
    finally:
        session.close()


def _read_inspection_report(job_id: str) -> dict | None:
    """Load the saved inspection_report.json for a completed job."""
    report_path = (OUTPUT_DIR / job_id / "inspection_report.json").resolve()
    if not str(report_path).startswith(str(OUTPUT_DIR.resolve())):
        return None
    if not report_path.exists():
        return None
    try:
        return json.loads(report_path.read_text())
    except (json.JSONDecodeError, OSError):
        logger.exception("Failed to read inspection report for job %s", job_id)
        return None


def _cleanup_old_results() -> None:
    ttl_hours = int(os.environ.get("AXALON_RESULTS_TTL_HOURS", "0"))
    if ttl_hours <= 0:
        return
    cutoff = datetime.utcnow() - timedelta(hours=ttl_hours)
    session = get_session()
    try:
        old_jobs = session.query(DbJob).filter(
            DbJob.created_at < cutoff,
            DbJob.state.in_(["succeeded", "failed"]),
        ).all()
        for job in old_jobs:
            job_dir = OUTPUT_DIR / job.id
            if job_dir.exists():
                shutil.rmtree(job_dir, ignore_errors=True)
        if old_jobs:
            logger.info("Cleaned up output for %s old job(s)", len(old_jobs))
    finally:
        session.close()


def _run_batch_job(
    job_id: str,
    zip_path: Path,
    park_id: str,
    altitude_m: float,
    site_meta: dict | None = None,
) -> None:
    extract_dir = OUTPUT_DIR / job_id
    extract_dir.mkdir(exist_ok=True)

    try:
        with zipfile.ZipFile(str(zip_path), "r") as zf:
            _safe_extract_zip_with_timeout(zf, extract_dir)
        zip_path.unlink(missing_ok=True)

        def progress_cb(processed: int, total: int) -> None:
            _update_job(job_id, processed=processed, total=total, state="running")

        # If the zip had a single top-level directory (e.g. sample_mission/thermal/)
        # the extracted layout is extract_dir/sample_mission/thermal/ — walk up to
        # the actual mission root that contains a thermal/ subdir.
        mission_root = extract_dir
        subdirs = [d for d in extract_dir.iterdir() if d.is_dir()]
        if len(subdirs) == 1 and (subdirs[0] / "thermal").exists():
            mission_root = subdirs[0]
            logger.info("Detected single-folder zip; using mission root: %s", mission_root)

        orch = get_orchestrator()
        result = orch.inspect_folder(
            folder=mission_root, park_id=park_id,
            altitude_m=altitude_m, progress_callback=progress_cb,
            site_meta=site_meta,
        )
        generate_json_report(result, extract_dir / "inspection_report.json")
        generate_excel_report(result, extract_dir / "inspection_report.xlsx", site_meta=site_meta)
        write_geojson(result, extract_dir / "park_anomaly_map.geojson")
        try:
            generate_pdf_report(result, extract_dir / "inspection_report.pdf", site_meta=site_meta)
        except Exception:
            logger.exception("PDF report generation failed for batch job %s", job_id)

        total_images = int(result.get("total_images") or 0)
        _update_job(
            job_id,
            state="succeeded",
            processed=total_images,
            total=total_images,
            message=None,
            result_path=str(extract_dir / "inspection_report.json"),
        )
    except Exception:
        logger.exception("Batch job %s failed", job_id)
        # Do NOT expose exception message to clients — log it, return generic error
        _update_job(
            job_id,
            state="failed",
            message="Inspection failed. Check server logs for details.",
        )
        return

    _send_job_alerts(job_id, result)


def _send_job_alerts(job_id: str, result: dict) -> None:
    """Fire fault alerts for a job whose success is already committed.

    Runs outside the job's try block so an alerting bug can never flip a
    succeeded job to failed. The per-channel outcome is logged rather than
    written to Job.message, because the console renders a non-null message as
    the job's error.
    """
    try:
        notify_inspection_complete(job_id, result)
    except Exception:
        logger.exception("Alerting failed for job %s (job result unaffected)", job_id)


__all__ = [
    "_REPORT_FORMAT_MAP",
    "_cleanup_old_results",
    "_corrections_for_job",
    "_create_job",
    "_get_job",
    "_read_inspection_report",
    "_run_batch_job",
    "_state_from_status",
    "_update_job",
]
