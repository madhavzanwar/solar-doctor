"""
tracking.py — Cross-inspection fault tracking and per-inspection dedup.

Two responsibilities:
  1. dedup_detections: collapse multiple detections of the SAME class on the
     SAME panel within a single inspection (overlapping flight tiles or
     repeated boxes from the detector) into one canonical detection.
  2. reconcile_inspection: upsert PanelFault rows so we can answer
     "is this fault new this inspection, recurring, or no longer seen?"
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from typing import Iterable

from axalon.db.models import (
    Detection as DbDetection,
    PanelFault,
    FAULT_ASSIGNED,
    FAULT_IN_PROGRESS,
    FAULT_OPEN,
    FAULT_STALE,
)

# Repair work in these states survives re-detection (the crew hasn't finished).
_DISPATCHED_STATUSES = (FAULT_ASSIGNED, FAULT_IN_PROGRESS)

# Severity rank — higher is worse. Used to keep the worst severity ever
# observed on a given (panel, class) pair.
_SEVERITY_RANK = {"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}


def _bbox_iou(a: list[float], b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = a
    bx1, by1, bx2, by2 = b
    ix1, iy1 = max(ax1, bx1), max(ay1, by1)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0.0, ix2 - ix1), max(0.0, iy2 - iy1)
    inter = iw * ih
    a_area = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    b_area = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = a_area + b_area - inter
    return inter / union if union > 0 else 0.0


def _merge_bboxes(boxes: list[list[float]]) -> list[float]:
    """Union of bounding boxes — smallest box covering all inputs."""
    x1 = min(b[0] for b in boxes)
    y1 = min(b[1] for b in boxes)
    x2 = max(b[2] for b in boxes)
    y2 = max(b[3] for b in boxes)
    return [x1, y1, x2, y2]


def _worst_severity(severities: Iterable[str]) -> str:
    return max(severities, key=lambda s: _SEVERITY_RANK.get(s, 0))


def dedup_detections(
    detections: list[dict],
    iou_threshold: float = 0.3,
) -> list[dict]:
    """Collapse duplicate detections within a single inspection.

    Strategy:
      * Detections sharing the SAME (panel_id, class) are candidates to merge.
      * For known panels (panel_id != "R?-C?") we always merge — multiple
        boxes on the same panel for the same fault class are duplicates.
      * For unknown panels we fall back to IoU >= iou_threshold to avoid
        merging genuinely separate faults that happen to lack a panel ID.
      * Merged detections take the union bbox, max confidence, worst severity,
        and accumulate `merged_from` count for traceability.
    """
    # Group by (panel_id, class)
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for det in detections:
        key = (det.get("panel_id") or "R?-C?", det.get("class") or "")
        groups[key].append(det)

    out: list[dict] = []
    for (panel_id, cls), bucket in groups.items():
        if len(bucket) == 1:
            d = dict(bucket[0])
            d.setdefault("merged_from", 1)
            out.append(d)
            continue

        # Known panel — merge everything in the bucket.
        if panel_id != "R?-C?":
            out.append(_merge_bucket(bucket))
            continue

        # Unknown panel — only merge boxes that physically overlap.
        clusters: list[list[dict]] = []
        for det in bucket:
            placed = False
            for cluster in clusters:
                if any(_bbox_iou(det["bbox"], c["bbox"]) >= iou_threshold for c in cluster):
                    cluster.append(det)
                    placed = True
                    break
            if not placed:
                clusters.append([det])
        for cluster in clusters:
            out.append(_merge_bucket(cluster) if len(cluster) > 1 else {**cluster[0], "merged_from": 1})

    return out


def _merge_bucket(bucket: list[dict]) -> dict:
    """Combine a list of duplicate detections into one canonical detection."""
    # Anchor on the highest-confidence detection — preserves its GPS, image_id, etc.
    anchor = max(bucket, key=lambda d: d.get("confidence") or 0.0)
    merged = dict(anchor)
    merged["bbox"] = _merge_bboxes([d["bbox"] for d in bucket])
    merged["confidence"] = max(d.get("confidence") or 0.0 for d in bucket)
    severities = [d.get("severity") for d in bucket if d.get("severity")]
    if severities:
        merged["severity"] = _worst_severity(severities)
    merged["merged_from"] = len(bucket)
    return merged


def reconcile_inspection(
    session,
    park_id: str,
    inspection_id: str,
    flight_date: str | None,
    detections: list[dict],
) -> dict:
    """Upsert PanelFault rows and link Detection rows in the DB.

    Must be called AFTER detections for this inspection have been written to
    the `detections` table (we look them up by inspection_id to set fault_id).

    Returns counts: {new, recurring, stale, total}.

    Workflow:
      1. For every unique (panel_id, class) in `detections`, find or create
         a PanelFault. Update last_seen_*, occurrences, max_confidence,
         worst severity. Status flips to OPEN.
      2. Mark any PanelFault for this park that wasn't seen this inspection
         as STALE (if previously OPEN). Resolved faults stay resolved.
      3. Backfill Detection.fault_id for rows written this inspection.
    """
    now = datetime.utcnow()
    seen_keys: set[tuple[str, str]] = set()
    new_count = 0
    recurring_count = 0

    # Map (panel_id, class) → fault_id for backfilling detections later.
    key_to_fault_id: dict[tuple[str, str], int] = {}

    # Index dedup'd detections by key so we can grab a representative bbox/gps.
    by_key: dict[tuple[str, str], dict] = {}
    for det in detections:
        key = (det.get("panel_id") or "R?-C?", det.get("class") or "")
        # Keep the highest-confidence representative.
        prev = by_key.get(key)
        if prev is None or (det.get("confidence") or 0.0) > (prev.get("confidence") or 0.0):
            by_key[key] = det

    for (panel_id, cls), det in by_key.items():
        if not cls:
            continue  # skip detections with no class

        seen_keys.add((panel_id, cls))
        fault = (
            session.query(PanelFault)
            .filter_by(park_id=park_id, panel_id=panel_id, class_=cls)
            .first()
        )
        conf = float(det.get("confidence") or 0.0)
        sev = det.get("severity") or "LOW"
        bbox_json = json.dumps(det.get("bbox")) if det.get("bbox") is not None else None
        gps_json = json.dumps(det.get("gps")) if det.get("gps") else None

        if fault is None:
            fault = PanelFault(
                park_id=park_id,
                panel_id=panel_id,
                class_=cls,
                class_id=det.get("class_id"),
                severity=sev,
                status=FAULT_OPEN,
                occurrences=1,
                max_confidence=conf,
                first_seen_inspection_id=inspection_id,
                last_seen_inspection_id=inspection_id,
                first_seen_date=flight_date,
                last_seen_date=flight_date,
                last_bbox=bbox_json,
                last_gps=gps_json,
                created_at=now,
                updated_at=now,
            )
            session.add(fault)
            session.flush()  # populate fault.id for FK backfill
            new_count += 1
        else:
            # Only bump occurrences if this is a new inspection for this fault.
            if fault.last_seen_inspection_id != inspection_id:
                fault.occurrences = (fault.occurrences or 0) + 1
                recurring_count += 1
            fault.last_seen_inspection_id = inspection_id
            fault.last_seen_date = flight_date or fault.last_seen_date
            # Seen again: stale → open and a "fixed" fault recurs → reopen, but
            # never clobber repair work that is already dispatched or underway.
            if fault.status not in _DISPATCHED_STATUSES:
                fault.status = FAULT_OPEN
                fault.resolved_at = None
            fault.max_confidence = max(fault.max_confidence or 0.0, conf)
            if _SEVERITY_RANK.get(sev, 0) > _SEVERITY_RANK.get(fault.severity or "LOW", 0):
                fault.severity = sev
            if bbox_json:
                fault.last_bbox = bbox_json
            if gps_json:
                fault.last_gps = gps_json
            fault.updated_at = now

        key_to_fault_id[(panel_id, cls)] = fault.id

    # Mark previously-open faults that weren't seen this inspection as STALE.
    stale_count = 0
    open_faults = (
        session.query(PanelFault)
        .filter(PanelFault.park_id == park_id, PanelFault.status == FAULT_OPEN)
        .all()
    )
    for f in open_faults:
        if (f.panel_id, f.class_) not in seen_keys:
            f.status = FAULT_STALE
            f.updated_at = now
            stale_count += 1

    # Backfill fault_id on detections written for this inspection.
    rows = (
        session.query(DbDetection)
        .filter(DbDetection.inspection_id == inspection_id)
        .all()
    )
    for row in rows:
        fid = key_to_fault_id.get((row.panel_id or "R?-C?", row.class_ or ""))
        if fid is not None:
            row.fault_id = fid

    session.commit()
    return {
        "new": new_count,
        "recurring": recurring_count,
        "stale": stale_count,
        "total": len(seen_keys),
    }
