"""settings router — extracted from app.py (Plan 01)."""
from __future__ import annotations

from fastapi import APIRouter
from axalon.api.deps import *  # noqa: F401,F403
from axalon.api.schemas.responses import SettingsOut
from axalon.api.schemas import SettingsUpdate

router = APIRouter(tags=["settings"])

@router.get("/settings", response_model=SettingsOut)
def get_settings():
    """Return current platform settings.yaml as JSON."""
    try:
        import yaml  # lazy — keep top-level imports lean
        if not _SETTINGS_PATH.exists():
            raise HTTPException(404, "settings.yaml not found")
        with _SETTINGS_PATH.open("r") as f:
            data = yaml.safe_load(f) or {}
        return {"settings": data, "path": str(_SETTINGS_PATH)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to read settings.yaml")
        raise HTTPException(500, f"Failed to read settings: {exc}")


@router.put("/settings")
def update_settings(payload: SettingsUpdate):
    """Overwrite settings.yaml with the provided dict (top-level key 'settings').

    Sync `def` (not `async def`): the body only does blocking file I/O, so
    FastAPI runs it in its thread pool instead of stalling the event loop.
    """
    payload = payload.model_dump(exclude_unset=True)
    try:
        import yaml
        new_settings = payload.get("settings") if isinstance(payload, dict) else None
        if not isinstance(new_settings, dict):
            raise HTTPException(400, "Body must be {'settings': {...}}")
        # Atomic write: temp file → rename
        tmp = _SETTINGS_PATH.with_suffix(".yaml.tmp")
        with tmp.open("w") as f:
            yaml.safe_dump(new_settings, f, sort_keys=False, default_flow_style=False)
        tmp.replace(_SETTINGS_PATH)
        return {"ok": True, "path": str(_SETTINGS_PATH)}
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to write settings.yaml")
        raise HTTPException(500, f"Failed to write settings: {exc}")


# ── Thermal↔RGB rig calibration ──────────────────────────────────────────────

_MAX_CALIBRATION_BYTES = 256 * 1024  # a calibration is a few hundred bytes


def _calibration_status() -> dict:
    """The calibration the pipeline will use (env > settings.yaml > DB)."""
    from axalon.core.fusion_calibration import resolve_active_calibration

    active = resolve_active_calibration()
    return {
        "configured": active.calibration is not None,
        "source": active.source,
        "path": active.path,
        "error": active.error,
        "calibration": active.calibration.summary() if active.calibration else None,
    }


@router.get("/settings/fusion-calibration")
def get_fusion_calibration():
    """Summary of the thermal→RGB calibration the pipeline will use."""
    return _calibration_status()


@router.post("/settings/fusion-calibration", status_code=201)
async def upload_fusion_calibration(
    file: UploadFile = File(..., description="Calibration JSON from scripts/calibrate_fusion.py"),
):
    """Validate and store a rig calibration in the database (app_config)."""
    from axalon.core.fusion_calibration import (
        CalibrationError,
        loads_calibration,
        store_calibration,
    )

    payload = await file.read(_MAX_CALIBRATION_BYTES + 1)
    if len(payload) > _MAX_CALIBRATION_BYTES:
        raise HTTPException(413, "Calibration file exceeds 256 KB")
    try:
        calibration = loads_calibration(payload)
    except CalibrationError as exc:
        raise HTTPException(400, f"Invalid calibration: {exc}")

    session = get_session()
    try:
        store_calibration(session, calibration)
    finally:
        session.close()
    logger.info("Stored fusion calibration for rig %s", calibration.rig_id)
    return {"ok": True, "calibration": calibration.summary(), "active": _calibration_status()}
