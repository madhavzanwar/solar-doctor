"""park router — extracted from app.py (Plan 01)."""
from __future__ import annotations

from fastapi import APIRouter
from axalon.api.deps import *  # noqa: F401,F403
from axalon.api.schemas.responses import GridOut, ParkDiffOut, ParksOut, ParkSummaryOut, RecurringOut, TrendOut
from axalon.api.schemas import ParkUpdate
from axalon.api.support.revenue import REVENUE_CURRENCY, revenue_loss_by_inspection

router = APIRouter(tags=["park"])

@router.get("/park/{park_id}", response_model=ParkSummaryOut)
def get_park_summary(park_id: str, principal: Principal = Depends(current_principal)):
    """Get park summary + inspection history from DB."""
    park_id = _validate_park_id(park_id)
    session = get_session()
    try:
        park = session.query(Park).filter_by(id=park_id).first()
        if park is None or not principal.can_see_project(park.project_id):
            raise HTTPException(status_code=404, detail="Park not found")
        inspections = (
            session.query(Inspection)
            .filter_by(park_id=park_id)
            .order_by(Inspection.created_at.desc())
            .all()
        )
        losses = revenue_loss_by_inspection(session, [insp.id for insp in inspections])
        return {
            "park_id": park_id,
            "name": park.name,
            "mode": park.mode,
            "total_panels": park.total_panels,
            "rows": park.rows,
            "cols": park.cols,
            "total_inspections": len(inspections),
            "inspections": [
                {
                    "id": insp.id,
                    "flight_date": insp.flight_date,
                    "total_images": insp.total_images,
                    "total_detections": insp.total_detections,
                    "summary": json.loads(insp.summary) if insp.summary else {},
                    "inspection_type": insp.inspection_type,
                    "inspection_level": insp.inspection_level,
                    "client": insp.client,
                    "location": insp.location,
                    "capacity_mw": insp.capacity_mw,
                    "irradiance_wm2": insp.irradiance_wm2,
                    "wind_speed_bft": insp.wind_speed_bft,
                    "cloud_coverage_okta": insp.cloud_coverage_okta,
                    # Estimate only — see compute_revenue_loss for assumptions.
                    "revenue_loss_usd": losses.get(insp.id),
                    "revenue_currency": REVENUE_CURRENCY,
                }
                for insp in inspections
            ],
        }
    finally:
        session.close()


@router.get("/park/{park_id}/grid", response_model=GridOut)
def get_park_grid(
    park_id: str,
    inspection_id: str | None = None,
    principal: Principal = Depends(current_principal),
):
    """Per-panel grid summary for a park's most recent (or specified) inspection."""
    from axalon.park.grid import build_grid

    session = get_session()
    try:
        park = session.query(Park).filter(Park.id == park_id).first()
        if park is None or not principal.can_see_project(park.project_id):
            raise HTTPException(status_code=404, detail=f"Park {park_id!r} not found")

        if inspection_id:
            insp = session.query(Inspection).filter(
                Inspection.id == inspection_id,
                Inspection.park_id == park_id,
            ).first()
            if insp is None:
                raise HTTPException(
                    status_code=404,
                    detail=f"Inspection {inspection_id!r} not found for park {park_id!r}",
                )
        else:
            insp = (
                session.query(Inspection)
                .filter(Inspection.park_id == park_id)
                .order_by(Inspection.created_at.desc())
                .first()
            )

        if insp is None:
            return {
                "park_id": park_id,
                "inspection_id": None,
                "rows": int(park.rows or 0),
                "cols": int(park.cols or 0),
                "panels": [],
            }

        rows = session.query(DbDetection).filter(DbDetection.inspection_id == insp.id).all()
        detections = []
        for d in rows:
            try:
                bbox = json.loads(d.bbox) if d.bbox else None
            except json.JSONDecodeError:
                bbox = None
            try:
                gps = json.loads(d.gps) if d.gps else None
            except json.JSONDecodeError:
                gps = None
            detections.append({
                "panel_id": d.panel_id,
                "severity": d.severity,
                "class": d.class_,
                "confidence": d.confidence,
                "image_id": d.image_id,
                "thermal_filename": f"{d.image_id}.jpg" if d.image_id else None,
                "bbox": bbox,
                "gps": gps,
                **_serialize_detection_temps(d),
            })

        return build_grid(detections=detections, park=park, inspection_id=insp.id)
    finally:
        session.close()


@router.get("/park/{park_id}/trend", response_model=list[TrendOut])
def get_park_trend(park_id: str, principal: Principal = Depends(current_principal)):
    """Per-inspection severity count trend for a park, oldest first."""
    from sqlalchemy import text
    from axalon.park.trend import build_trend

    park_id = _validate_park_id(park_id)
    session = get_session()
    try:
        park = session.query(Park).filter(Park.id == park_id).first()
        if park is None or not principal.can_see_project(park.project_id):
            raise HTTPException(status_code=404, detail=f"Park {park_id!r} not found")
        rows = session.execute(
            text("""
                SELECT i.id,
                       i.flight_date,
                       SUM(CASE WHEN d.severity = 'CRITICAL' THEN 1 ELSE 0 END) AS critical_count,
                       SUM(CASE WHEN d.severity = 'HIGH'     THEN 1 ELSE 0 END) AS high_count,
                       SUM(CASE WHEN d.severity = 'MEDIUM'   THEN 1 ELSE 0 END) AS medium_count,
                       SUM(CASE WHEN d.severity = 'LOW'      THEN 1 ELSE 0 END) AS low_count
                FROM inspections i
                LEFT JOIN detections d ON d.inspection_id = i.id
                WHERE i.park_id = :park_id
                GROUP BY i.id, i.flight_date
                ORDER BY i.flight_date ASC
            """),
            {"park_id": park_id},
        ).fetchall()
        return build_trend(rows)
    finally:
        session.close()


@router.get("/park/{park_id}/recurring", response_model=list[RecurringOut])
def get_park_recurring(
    park_id: str, min_inspections: int = 2, principal: Principal = Depends(current_principal),
):
    """Panels with anomalies in at least min_inspections inspections."""
    from sqlalchemy import text
    from axalon.park.recurring import build_recurring

    park_id = _validate_park_id(park_id)
    min_inspections = max(1, int(min_inspections))
    session = get_session()
    try:
        park = session.query(Park).filter(Park.id == park_id).first()
        if park is None or not principal.can_see_project(park.project_id):
            raise HTTPException(status_code=404, detail=f"Park {park_id!r} not found")
        rows = session.execute(
            text("""
                SELECT d.panel_id,
                       COUNT(DISTINCT d.inspection_id) AS inspection_count,
                       MAX(CASE d.severity
                           WHEN 'CRITICAL' THEN 4
                           WHEN 'HIGH'     THEN 3
                           WHEN 'MEDIUM'   THEN 2
                           ELSE 1 END) AS sev_rank,
                       GROUP_CONCAT(DISTINCT d.class) AS classes,
                       MIN(i.flight_date) AS first_seen,
                       MAX(i.flight_date) AS last_seen
                FROM detections d
                JOIN inspections i ON i.id = d.inspection_id
                WHERE i.park_id = :park_id
                  AND d.panel_id IS NOT NULL
                GROUP BY d.panel_id
                HAVING COUNT(DISTINCT d.inspection_id) >= :min_inspections
                ORDER BY sev_rank DESC, inspection_count DESC
            """),
            {"park_id": park_id, "min_inspections": min_inspections},
        ).fetchall()
        return build_recurring(rows)
    finally:
        session.close()


@router.get("/park/{park_id}/diff", response_model=ParkDiffOut)
def diff_park_inspections(
    park_id: str, inspection_a: str, inspection_b: str,
    principal: Principal = Depends(current_principal),
):
    """Compare two inspections of the same park, returning a rich per-panel diff.

    Query params:
        inspection_a: ID of the baseline inspection
        inspection_b: ID of the comparison inspection

    Returns a panel-level diff with status new | resolved | changed | unchanged,
    plus full detection lists for both inspections on each affected panel.
    """
    park_id = _validate_park_id(park_id)
    inspection_a = _validate_job_id(inspection_a)
    inspection_b = _validate_job_id(inspection_b)

    session = get_session()
    try:
        # 1. Validate park exists (and is visible to the caller)
        park = session.query(Park).filter(Park.id == park_id).first()
        if park is None or not principal.can_see_project(park.project_id):
            raise HTTPException(status_code=404, detail=f"Park {park_id!r} not found")

        # 2. Validate both inspections exist for this park
        insp_a = session.query(Inspection).filter(
            Inspection.id == inspection_a,
            Inspection.park_id == park_id,
        ).first()
        if insp_a is None:
            raise HTTPException(
                status_code=404,
                detail=f"Inspection {inspection_a!r} not found for park {park_id!r}",
            )

        insp_b = session.query(Inspection).filter(
            Inspection.id == inspection_b,
            Inspection.park_id == park_id,
        ).first()
        if insp_b is None:
            raise HTTPException(
                status_code=404,
                detail=f"Inspection {inspection_b!r} not found for park {park_id!r}",
            )

        # 3. Fetch all detections for both inspections
        def _fetch_detections(insp_id: str) -> list[dict]:
            rows = session.query(DbDetection).filter(
                DbDetection.inspection_id == insp_id
            ).all()
            result = []
            for d in rows:
                result.append({
                    "panel_id": d.panel_id or "R?-C?",
                    "class": d.class_,
                    "severity": d.severity,
                    "confidence": d.confidence,
                })
            return result

        dets_a = _fetch_detections(inspection_a)
        dets_b = _fetch_detections(inspection_b)

        # 4. Compute diff
        diff = build_diff(dets_a, dets_b)

        # 5. Build per-panel response
        # Collect all panel_ids that appear in either inspection
        all_panel_ids: set[str] = set()
        for det in dets_a + dets_b:
            all_panel_ids.add(det["panel_id"])

        # Index detections by panel_id for quick lookup
        def _panel_index(dets: list[dict]) -> dict[str, list[dict]]:
            idx: dict[str, list[dict]] = {}
            for det in dets:
                pid = det["panel_id"]
                idx.setdefault(pid, []).append({
                    "class": det["class"],
                    "severity": det["severity"],
                    "confidence": det["confidence"],
                })
            return idx

        panel_a = _panel_index(dets_a)
        panel_b = _panel_index(dets_b)

        # Build a (panel_id, class) -> status mapping from diff result
        panel_status: dict[str, str] = {}
        for item in diff["new"]:
            panel_status[item["panel_id"]] = "new"
        for item in diff["resolved"]:
            pid = item["panel_id"]
            # Don't downgrade a panel already marked "new" (edge case: mixed panel)
            if pid not in panel_status:
                panel_status[pid] = "resolved"
        for item in diff["changed"]:
            pid = item["panel_id"]
            # "changed" takes precedence over new/resolved if mixed
            if pid not in panel_status or panel_status[pid] == "unchanged":
                panel_status[pid] = "changed"

        panels: list[dict] = []
        for pid in sorted(all_panel_ids):
            dets_a_panel = panel_a.get(pid, [])
            dets_b_panel = panel_b.get(pid, [])

            status = panel_status.get(pid, "unchanged")

            # Derive severity_a / severity_b from the panel's highest-severity detection
            # (or None if not present in that inspection)
            _severity_order = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1, "": 0}

            def _top_severity(det_list: list[dict]) -> str | None:
                if not det_list:
                    return None
                return max(
                    (d["severity"] or "" for d in det_list),
                    key=lambda s: _severity_order.get(s, 0),
                ) or None

            panels.append({
                "panel_id": pid,
                "status": status,
                "severity_a": _top_severity(dets_a_panel),
                "severity_b": _top_severity(dets_b_panel),
                "detections_a": dets_a_panel,
                "detections_b": dets_b_panel,
            })

        summary = {
            "new": len(diff["new"]),
            "resolved": len(diff["resolved"]),
            "changed": len(diff["changed"]),
        }

        return {
            "park_id": park_id,
            "inspection_a": inspection_a,
            "inspection_b": inspection_b,
            "summary": summary,
            "panels": panels,
        }
    finally:
        session.close()


@router.get("/parks", response_model=ParksOut)
def list_parks(principal: Principal = Depends(current_principal)):
    """List parks from DB — only those the caller may see."""
    session = get_session()
    try:
        parks = scope_parks(session.query(Park), principal).all()
        return {
            "parks": [
                {"id": p.id, "name": p.name, "mode": p.mode,
                 "total_panels": p.total_panels, "rows": p.rows, "cols": p.cols}
                for p in parks
            ],
            "total": len(parks),
        }
    finally:
        session.close()


@router.patch("/park/{park_id}")
def update_park(park_id: str, payload: ParkUpdate, principal: Principal = Depends(current_principal)):
    """Assign/unassign a park to a project (and rename)."""
    payload = payload.model_dump(exclude_unset=True)
    park_id = _validate_park_id(park_id)
    session = get_session()
    try:
        park = session.query(Park).filter_by(id=park_id).first()
        if park is None or not principal.can_see_project(park.project_id):
            raise HTTPException(status_code=404, detail=f"Park {park_id!r} not found")
        if "project_id" in payload:
            project_id = payload.get("project_id")
            # A scoped user may only move a park between their own projects —
            # unassigning (None) would also put it out of their reach.
            if principal.is_restricted and not principal.can_see_project(project_id):
                raise HTTPException(status_code=404, detail="Project not found")
            if project_id is not None:
                proj = session.query(Project).filter_by(id=int(project_id)).first()
                if proj is None:
                    raise HTTPException(status_code=404, detail="Project not found")
            park.project_id = project_id
        if "name" in payload:
            name = str(payload.get("name") or "").strip()
            if name:
                park.name = name[:200]
        session.commit()
        session.refresh(park)
        return {
            "id": park.id,
            "name": park.name,
            "project_id": park.project_id,
            "total_panels": park.total_panels,
        }
    finally:
        session.close()
