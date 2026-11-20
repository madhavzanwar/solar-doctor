"""Inspections router — Unified single-image defect classification, XAI, telemetry cross-check, fusion & ROI.

Implements:
- POST /api/v1/inspections: Upload image, classify, generate XAI (Grad-CAM & LIME), fuse with telemetry & ROI, persist.
- GET  /api/v1/inspections: Query historical inspections with filtering.
- GET  /api/v1/inspections/{id}: Fetch inspection details.
- GET  /api/v1/inspections/{id}/image: Stream original uploaded image.
- GET  /api/v1/inspections/{id}/gradcam: Stream Grad-CAM overlay PNG.
- GET  /api/v1/inspections/{id}/lime: Stream LIME overlay PNG.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from PIL import Image

from solardoctor.api.deps import get_session
from solardoctor.api.support.paths import INSPECTIONS_DIR
from solardoctor.db.models import Inspection
from solardoctor.fusion.engine import fuse
from solardoctor.fusion.models import FusionSettings, PhotoEvidence, TelemetryEvidence
from solardoctor.physics.models import Plant, PlantAlert, PvString
from solardoctor.roi.models import RoiSettings
from solardoctor.vision.classifier import VisionModelUnavailable, get_classifier

logger = logging.getLogger("solardoctor.api.inspections")

router = APIRouter(prefix="/inspections", tags=["inspections"])

MAX_UPLOAD_BYTES = 15 * 1024 * 1024
_FORMATS = {"JPEG", "MPO", "PNG", "WEBP"}


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


async def _read_image(file: UploadFile) -> tuple[bytes, str]:
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
    if fmt not in _FORMATS or w * h > 50_000_000:
        raise HTTPException(status_code=422, detail="unsupported image (JPEG/PNG/WebP up to 50 MP)")
    ext = ".webp" if fmt == "WEBP" else (".png" if fmt == "PNG" else ".jpg")
    return data, ext


def _serialize_inspection(insp: Inspection) -> dict[str, Any]:
    probs = {}
    if insp.probs_json:
        try:
            probs = json.loads(insp.probs_json)
        except Exception:
            probs = {}

    top3 = []
    if probs:
        sorted_probs = sorted(probs.items(), key=lambda kv: -kv[1])
        top3 = [{"class": k, "prob": v} for k, v in sorted_probs[:3]]

    return {
        "id": insp.id,
        "plant_id": insp.plant_id,
        "string_id": insp.string_id,
        "alert_id": insp.alert_id,
        "park_id": insp.park_id,
        "created_at": insp.created_at.isoformat() if insp.created_at else None,
        "captured_at": insp.captured_at.isoformat() if insp.captured_at else None,
        "source": insp.source,
        "status": insp.status,
        "image_url": f"/api/v1/inspections/{insp.id}/image" if insp.image_path else None,
        "xai_gradcam_url": f"/api/v1/inspections/{insp.id}/gradcam" if insp.xai_gradcam_path else None,
        "xai_lime_url": f"/api/v1/inspections/{insp.id}/lime" if insp.xai_lime_path else None,
        "prediction": {
            "model_version": insp.model_version,
            "predicted_class": insp.predicted_class,
            "confidence": insp.confidence,
            "probs": probs,
            "top3": top3,
            "ood_score": insp.ood_score,
            "is_ood": (insp.field_check_reason == "out_of_distribution") or (insp.ood_score is not None and insp.ood_score > 0.75),
            "needs_field_check": bool(insp.needs_field_check),
            "field_check_reason": insp.field_check_reason,
            "image_sha256": insp.image_sha256,
        },
        "fusion": {
            "verdict": insp.fused_verdict,
            "action": insp.fused_action,
            "severity": insp.fused_severity,
            "reason": insp.fused_reason,
        },
        "roi": {
            "recoverable_kwh_day": insp.recoverable_kwh_day,
            "recoverable_inr_day": insp.recoverable_inr_day,
            "payback_days": insp.payback_days,
            "decision": insp.fused_action,
        },
    }


@router.post("", status_code=201)
async def create_inspection(
    file: UploadFile = File(..., description="JPEG/PNG/WebP solar panel image"),
    plant_id: Optional[int] = Form(None),
    string_id: Optional[int] = Form(None),
    alert_id: Optional[int] = Form(None),
    generate_xai: bool = Form(True),
    notes: Optional[str] = Form(None),
):
    """Upload solar panel image, classify defects, generate XAI, fuse with telemetry, and persist."""
    image_bytes, ext = await _read_image(file)
    sha256_hash = hashlib.sha256(image_bytes).hexdigest()

    # Obtain classifier
    try:
        clf = get_classifier()
    except VisionModelUnavailable as exc:
        logger.warning("Classifier unavailable: %s", exc)
        raise HTTPException(
            status_code=503,
            detail="RGB vision model is unavailable. Configure SOLARDOCTOR_RGB_MODEL_DIR or set SOLARDOCTOR_RGB_FALLBACK=1.",
        ) from exc

    # Run inference
    pred = clf.predict(image_bytes)

    # Generate XAI overlays
    cam_png_b64 = None
    lime_png_b64 = None
    cam_file_path = None
    lime_file_path = None

    insp_id = f"INSP-{uuid.uuid4().hex[:10].upper()}"
    insp_dir = INSPECTIONS_DIR / insp_id
    insp_dir.mkdir(parents=True, exist_ok=True)

    orig_image_path = insp_dir / f"original{ext}"
    orig_image_path.write_bytes(image_bytes)

    if generate_xai:
        try:
            cam_res = clf.explain(image_bytes, method="gradcam")
            cam_png_b64 = cam_res.get("png_base64")
            if cam_png_b64:
                cam_file = insp_dir / "gradcam.png"
                cam_file.write_bytes(base64.b64decode(cam_png_b64))
                cam_file_path = str(cam_file)
        except Exception as exc:
            logger.warning("Grad-CAM generation failed: %s", exc)

        try:
            lime_res = clf.explain(image_bytes, method="lime")
            lime_png_b64 = lime_res.get("png_base64")
            if lime_png_b64:
                lime_file = insp_dir / "lime.png"
                lime_file.write_bytes(base64.b64decode(lime_png_b64))
                lime_file_path = str(lime_file)
        except Exception as exc:
            logger.warning("LIME generation failed: %s", exc)

    # Telemetry cross-check & Fusion
    session = get_session()
    try:
        plant: Optional[Plant] = None
        if plant_id is not None:
            plant = session.query(Plant).filter_by(id=plant_id).first()

        alert: Optional[PlantAlert] = None
        if alert_id is not None:
            alert = session.query(PlantAlert).filter_by(id=alert_id).first()
            if alert and plant is None:
                plant = session.query(Plant).filter_by(id=alert.plant_id).first()
                plant_id = alert.plant_id
        elif plant is not None:
            # Look up any active unresolved alert for this plant / string
            q = session.query(PlantAlert).filter(
                PlantAlert.plant_id == plant.id,
                PlantAlert.is_resolved.is_(False),
            )
            if string_id is not None:
                q = q.filter(PlantAlert.string_id == string_id)
            alert = q.order_by(PlantAlert.timestamp.desc()).first()
            if alert:
                alert_id = alert.id

        # Build TelemetryEvidence
        if alert is not None:
            usable_hrs = 4
            exp_kwh = (alert.expected_power_kw or 20.0) * usable_hrs
            dev_frac = (alert.deviation_percent / 100.0) if alert.deviation_percent else 0.15
            t_ev = TelemetryEvidence(
                status="ok",
                usable_clear_hours=usable_hrs,
                deficit_severity=alert.severity,
                pi_median=(alert.actual_power_kw / alert.expected_power_kw) if (alert.actual_power_kw and alert.expected_power_kw) else 0.85,
                deviation_percent=alert.deviation_percent,
                expected_kwh_day=exp_kwh,
                attributable_deficit_fraction=dev_frac,
            )
        else:
            t_ev = TelemetryEvidence(
                status="no_telemetry" if plant is None else "ok",
                usable_clear_hours=4 if plant else None,
                deficit_severity=None,
                pi_median=0.98 if plant else None,
                deviation_percent=2.0 if plant else None,
                expected_kwh_day=(plant.dc_kw * 4.2) if plant else None,
                attributable_deficit_fraction=0.02 if plant else None,
            )

        # Build PhotoEvidence
        p_ev = PhotoEvidence(
            predicted_class=pred["predicted_class"],
            confidence=pred["confidence"],
            is_ood=pred["is_ood"],
            needs_field_check=pred["needs_field_check"],
            field_check_reason=pred["field_check_reason"],
            model_version=pred["model_version"],
        )

        # Build FusionSettings
        tariff = (plant.tariff_inr_kwh if plant and plant.tariff_inr_kwh else 5.5)
        cleaning_cost = (plant.cleaning_cost_per_module_inr if plant else 50.0)
        water_l = (plant.water_l_per_module if plant else 2.5)
        labour = (plant.labour_cost_inr if plant else 1500.0)
        mod_count = (plant.module_count if plant and plant.module_count else 100)

        roi_cfg = RoiSettings(
            cleaning_cost_per_module_inr=cleaning_cost,
            water_l_per_module=water_l,
            labour_cost_inr=labour,
            tariff_inr_per_kwh=tariff,
            module_count=mod_count,
        )
        f_settings = FusionSettings(roi=roi_cfg, conf_threshold=0.6)

        # Run Fusion
        verdict = fuse(t_ev, p_ev, f_settings)

        rec_kwh = verdict.roi.recoverable_kwh_day if verdict.roi else None
        rec_inr = verdict.roi.inr_per_day if verdict.roi else None
        payback = verdict.roi.payback_days if verdict.roi else None

        # Persist Inspection record
        db_insp = Inspection(
            id=insp_id,
            plant_id=plant_id,
            string_id=string_id,
            alert_id=alert_id,
            park_id=plant.park_id if plant else None,
            image_path=str(orig_image_path),
            image_sha256=sha256_hash,
            captured_at=_utcnow(),
            source="upload",
            model_version=pred["model_version"],
            predicted_class=pred["predicted_class"],
            probs_json=json.dumps(pred.get("probs", {})),
            confidence=pred["confidence"],
            ood_score=pred.get("ood_score"),
            needs_field_check=pred["needs_field_check"],
            field_check_reason=pred["field_check_reason"],
            xai_gradcam_path=cam_file_path,
            xai_lime_path=lime_file_path,
            fused_verdict=verdict.verdict,
            fused_action=verdict.action,
            fused_severity=verdict.severity.value,
            fused_reason=verdict.reason,
            recoverable_kwh_day=rec_kwh,
            recoverable_inr_day=rec_inr,
            payback_days=payback,
            status="completed",
            created_at=_utcnow(),
        )
        session.add(db_insp)
        session.commit()
        session.refresh(db_insp)

        serialized = _serialize_inspection(db_insp)
        # Attach in-memory base64 overlays for immediate single-response UI render
        if cam_png_b64:
            serialized["gradcam_base64"] = cam_png_b64
        if lime_png_b64:
            serialized["lime_base64"] = lime_png_b64
        return serialized
    finally:
        session.close()


@router.get("")
def list_inspections(
    plant_id: Optional[int] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    """List historical inspection records."""
    session = get_session()
    try:
        q = session.query(Inspection)
        if plant_id is not None:
            q = q.filter(Inspection.plant_id == plant_id)
        if status:
            q = q.filter(Inspection.status == status)
        q = q.order_by(Inspection.created_at.desc())
        items = q.offset(offset).limit(limit).all()
        return [_serialize_inspection(i) for i in items]
    finally:
        session.close()


@router.get("/{id}")
def get_inspection(id: str):
    """Fetch single inspection record by ID."""
    session = get_session()
    try:
        insp = session.query(Inspection).filter_by(id=id).first()
        if insp is None:
            raise HTTPException(status_code=404, detail="Inspection not found")
        return _serialize_inspection(insp)
    finally:
        session.close()


@router.get("/{id}/image")
def get_inspection_image(id: str):
    session = get_session()
    try:
        insp = session.query(Inspection).filter_by(id=id).first()
        if insp is None or not insp.image_path:
            raise HTTPException(status_code=404, detail="Inspection image not found")
        p = Path(insp.image_path)
        if not p.exists():
            raise HTTPException(status_code=404, detail="Image file missing from storage")
        media = "image/webp" if p.suffix == ".webp" else ("image/png" if p.suffix == ".png" else "image/jpeg")
        return FileResponse(p, media_type=media)
    finally:
        session.close()


@router.get("/{id}/gradcam")
def get_inspection_gradcam(id: str):
    session = get_session()
    try:
        insp = session.query(Inspection).filter_by(id=id).first()
        if insp is None or not insp.xai_gradcam_path:
            raise HTTPException(status_code=404, detail="Grad-CAM overlay not found")
        p = Path(insp.xai_gradcam_path)
        if not p.exists():
            raise HTTPException(status_code=404, detail="Grad-CAM file missing from storage")
        return FileResponse(p, media_type="image/png")
    finally:
        session.close()


@router.get("/{id}/lime")
def get_inspection_lime(id: str):
    session = get_session()
    try:
        insp = session.query(Inspection).filter_by(id=id).first()
        if insp is None or not insp.xai_lime_path:
            raise HTTPException(status_code=404, detail="LIME overlay not found")
        p = Path(insp.xai_lime_path)
        if not p.exists():
            raise HTTPException(status_code=404, detail="LIME file missing from storage")
        return FileResponse(p, media_type="image/png")
    finally:
        session.close()
