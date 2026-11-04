"""Unit/integration tests for platform/pipeline/tracking.py.

dedup_detections is pure; reconcile_inspection persists PanelFault rows via the
real in-memory SQLite session from conftest (no mocked DB).
"""
from __future__ import annotations

from axalon.db.models import (
    Detection as DbDetection,
    FAULT_OPEN,
    FAULT_RESOLVED,
    FAULT_STALE,
    Inspection,
    PanelFault,
    Park,
)
from axalon.pipeline.tracking import dedup_detections, reconcile_inspection


def _det(panel_id, cls, severity="HIGH", conf=0.8, bbox=None) -> dict:
    return {
        "panel_id": panel_id,
        "class": cls,
        "class_id": 9,
        "severity": severity,
        "confidence": conf,
        "bbox": bbox or [0, 0, 10, 10],
    }


# ── dedup_detections (pure) ───────────────────────────────────────────────────

def test_dedup_merges_same_class_on_known_panel():
    # Arrange — two boxes of the same class on the same known panel
    dets = [
        _det("R1-C1", "hot-spot-low", conf=0.6, bbox=[0, 0, 10, 10]),
        _det("R1-C1", "hot-spot-low", conf=0.9, bbox=[5, 5, 15, 15]),
    ]

    # Act
    out = dedup_detections(dets)

    # Assert — collapsed to one detection, union bbox, max confidence
    assert len(out) == 1
    assert out[0]["confidence"] == 0.9
    assert out[0]["bbox"] == [0, 0, 15, 15]
    assert out[0]["merged_from"] == 2


def test_dedup_keeps_distinct_classes_separate():
    # Arrange
    dets = [_det("R1-C1", "soiling"), _det("R1-C1", "hot-spot-high")]

    # Act
    out = dedup_detections(dets)

    # Assert
    assert len(out) == 2


def test_dedup_unknown_panel_only_merges_overlapping_boxes():
    # Arrange — same class, unknown panel, but the boxes do not overlap
    dets = [
        _det("R?-C?", "module", bbox=[0, 0, 10, 10]),
        _det("R?-C?", "module", bbox=[100, 100, 110, 110]),
    ]

    # Act
    out = dedup_detections(dets, iou_threshold=0.3)

    # Assert — kept separate because IoU is 0
    assert len(out) == 2


# ── reconcile_inspection (DB) ─────────────────────────────────────────────────

def _seed_inspection(session, park_id, inspection_id, detections):
    """Create park + inspection + detection rows the way the pipeline would."""
    if session.query(Park).filter_by(id=park_id).first() is None:
        session.add(Park(id=park_id, name=park_id))
        session.commit()
    session.add(Inspection(id=inspection_id, park_id=park_id))
    session.commit()
    for d in detections:
        session.add(DbDetection(
            inspection_id=inspection_id,
            panel_id=d["panel_id"],
            class_=d["class"],
            class_id=d.get("class_id"),
            severity=d["severity"],
            confidence=d["confidence"],
        ))
    session.commit()


def test_tracking_marks_new_fault_as_open(db_session):
    # Arrange
    park, insp = "PARK_T1", "insp-1"
    dets = [_det("R1-C1", "hot-spot-high", "CRITICAL")]
    _seed_inspection(db_session, park, insp, dets)

    # Act
    counts = reconcile_inspection(db_session, park, insp, "2026-01-01", dets)

    # Assert
    fault = db_session.query(PanelFault).filter_by(park_id=park).one()
    assert fault.status == FAULT_OPEN
    assert counts["new"] == 1
    assert counts["stale"] == 0


def test_tracking_recurring_fault_bumps_occurrences(db_session):
    # Arrange — same fault seen in two inspections
    park = "PARK_T2"
    dets1 = [_det("R1-C1", "hot-spot-high", "CRITICAL")]
    _seed_inspection(db_session, park, "insp-1", dets1)
    reconcile_inspection(db_session, park, "insp-1", "2026-01-01", dets1)

    dets2 = [_det("R1-C1", "hot-spot-high", "CRITICAL")]
    _seed_inspection(db_session, park, "insp-2", dets2)

    # Act
    counts = reconcile_inspection(db_session, park, "insp-2", "2026-02-01", dets2)

    # Assert
    fault = db_session.query(PanelFault).filter_by(park_id=park).one()
    assert counts["recurring"] == 1
    assert counts["new"] == 0
    assert fault.occurrences == 2
    assert fault.status == FAULT_OPEN


def test_tracking_marks_missing_fault_as_stale(db_session):
    # Arrange — fault present in inspection 1, absent in inspection 2
    park = "PARK_T3"
    dets1 = [_det("R1-C1", "hot-spot-high", "CRITICAL")]
    _seed_inspection(db_session, park, "insp-1", dets1)
    reconcile_inspection(db_session, park, "insp-1", "2026-01-01", dets1)

    dets2 = [_det("R9-C9", "soiling", "LOW")]
    _seed_inspection(db_session, park, "insp-2", dets2)

    # Act
    reconcile_inspection(db_session, park, "insp-2", "2026-02-01", dets2)

    # Assert — the original fault is now STALE
    stale = db_session.query(PanelFault).filter_by(park_id=park, panel_id="R1-C1").one()
    assert stale.status == FAULT_STALE


def test_tracking_resolved_fault_stays_resolved(db_session):
    # Arrange — operator resolved a fault; it must not flip back to stale
    park = "PARK_T4"
    dets1 = [_det("R1-C1", "hot-spot-high", "CRITICAL")]
    _seed_inspection(db_session, park, "insp-1", dets1)
    reconcile_inspection(db_session, park, "insp-1", "2026-01-01", dets1)
    fault = db_session.query(PanelFault).filter_by(park_id=park).one()
    fault.status = FAULT_RESOLVED
    db_session.commit()

    dets2 = [_det("R9-C9", "soiling", "LOW")]
    _seed_inspection(db_session, park, "insp-2", dets2)

    # Act — fault not seen this inspection
    reconcile_inspection(db_session, park, "insp-2", "2026-02-01", dets2)

    # Assert — stays resolved (stale logic only touches OPEN faults)
    db_session.refresh(fault)
    assert fault.status == FAULT_RESOLVED
