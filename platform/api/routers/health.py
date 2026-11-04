"""health router — extracted from app.py (Plan 01)."""
from __future__ import annotations

from fastapi import APIRouter
from axalon.api.deps import *  # noqa: F401,F403
from axalon.api.schemas.responses import HealthOut
from axalon.core.detector import DEFAULT_WEIGHTS
from axalon.core.model_info import empty_model_info, get_model_info
from axalon.api.support.odm_jobs import odm_capability

router = APIRouter(tags=["health"])

# The weights the orchestrator loads (InspectionOrchestrator → SolarDetector default).
MODEL_WEIGHTS = DEFAULT_WEIGHTS


def _model_info() -> dict:
    """Checkpoint facts for /health; degrades to 'unknown' rather than failing."""
    try:
        return get_model_info(MODEL_WEIGHTS)
    except Exception:
        logger.exception("Health check model info failed")
        return empty_model_info(MODEL_WEIGHTS)


@router.get("/health", response_model=HealthOut)
def health():
    try:
        session = get_session()
        try:
            park_count = session.query(Park).count()
            db_status = "ok"
        finally:
            session.close()
    except Exception:
        logger.exception("Health check DB query failed")
        park_count = 0
        db_status = "error"
    model_info = _model_info()
    return {
        "status": "ok",
        "model": model_info["name"],
        "weights": model_info["weights_path"],
        "model_info": model_info,
        "version": "1.0.0",
        "db": db_status,
        "parks_in_db": park_count,
        "capabilities": {"odm": odm_capability()},
        "migrations": {"state": MIGRATION_STATUS["state"]},
    }
