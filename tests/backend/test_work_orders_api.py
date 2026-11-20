"""Tests for Work Orders lifecycle API and verification (P0.4)."""
import pytest
from fastapi.testclient import TestClient

from solardoctor.api.app import app
from solardoctor.api.deps import get_session
from solardoctor.physics.models import PlantAlert


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


def test_work_order_full_lifecycle(client):
    # 1. Create linked plant alert to test auto-resolution
    session = get_session()
    alert = PlantAlert(
        plant_id=1,
        timestamp=session.query(PlantAlert).first().timestamp if session.query(PlantAlert).first() else None,
        alert_type="soiling",
        severity="WARNING",
        message="Soiling shortfall detected on S-04",
        expected_power_kw=25.0,
        actual_power_kw=21.0,
        deviation_percent=16.0,
        is_resolved=False,
    )
    from datetime import datetime, timezone
    if not alert.timestamp:
        alert.timestamp = datetime.now(timezone.utc)
    session.add(alert)
    session.commit()
    session.refresh(alert)
    alert_id = alert.id
    session.close()

    import uuid
    panel_id = f"R02-C{uuid.uuid4().hex[:6]}"

    # 2. Create work order in open state
    create_payload = {
        "plant_id": 1,
        "alert_id": alert_id,
        "panel_id": panel_id,
        "class": "dusty",
        "severity": "MEDIUM",
        "priority": "high",
        "notes": "Cleaning required on string S-04",
    }
    r = client.post("/api/v1/work-orders", json=create_payload)
    assert r.status_code == 201
    wo = r.json()
    wo_id = wo["id"]
    assert wo["status"] == "open"
    assert wo["panel_id"] == panel_id
    assert len(wo["checklist"]) == 3
    assert wo["alert_id"] == alert_id

    # 3. Direct transition to 'verified' must be rejected (422)
    bad_transition = client.patch(f"/api/v1/work-orders/{wo_id}", json={"status": "verified"})
    assert bad_transition.status_code == 422

    # 4. Direct transition to 'resolved' without assignee, note or evidence must be rejected
    bad_resolve = client.patch(f"/api/v1/work-orders/{wo_id}", json={"status": "resolved"})
    assert bad_resolve.status_code == 422

    # 5. Transition to 'assigned' requires assignee
    bad_assign = client.patch(f"/api/v1/work-orders/{wo_id}", json={"status": "assigned"})
    assert bad_assign.status_code == 422

    good_assign = client.patch(
        f"/api/v1/work-orders/{wo_id}",
        json={"status": "assigned", "assignee": "Ramesh Kumar"},
    )
    assert good_assign.status_code == 200
    assert good_assign.json()["status"] == "assigned"
    assert good_assign.json()["assignee"] == "Ramesh Kumar"

    # 6. Transition to 'in_progress'
    in_prog = client.patch(f"/api/v1/work-orders/{wo_id}", json={"status": "in_progress"})
    assert in_prog.status_code == 200
    assert in_prog.json()["status"] == "in_progress"

    # 7. Transition to 'resolved' requires resolution note, photo evidence, and checklist
    resolve_missing_photo = client.patch(
        f"/api/v1/work-orders/{wo_id}",
        json={"status": "resolved", "resolution_note": "Cleaned the module"},
    )
    assert resolve_missing_photo.status_code == 422

    # Complete checklist, add photo evidence and resolution note
    checklist = [
        {"id": "c1", "text": "Inspect physical connections and module surface", "done": True},
        {"id": "c2", "text": "Perform required cleaning or defect repair", "done": True},
        {"id": "c3", "text": "Capture and upload post-repair proof photo", "done": True},
    ]
    good_resolve = client.patch(
        f"/api/v1/work-orders/{wo_id}",
        json={
            "status": "resolved",
            "resolution_note": "Fully washed with demineralized water and microfibre squeegee.",
            "after_photo_path": "uploads/fault_photos/proof_after_cleaned.jpg",
            "checklist": checklist,
        },
    )
    assert good_resolve.status_code == 200
    assert good_resolve.json()["status"] == "resolved"
    assert good_resolve.json()["resolved_at"] is not None

    # 8. Post-repair telemetry verification
    verify_res = client.post(f"/api/v1/work-orders/{wo_id}/verify")
    assert verify_res.status_code == 200
    v_data = verify_res.json()
    assert v_data["verified"] is True
    wo_verified = v_data["work_order"]
    assert wo_verified["status"] == "verified"
    assert wo_verified["verified_at"] is not None
    assert wo_verified["pi_after"] >= 0.90
    assert wo_verified["recovery_percent"] >= 50.0

    # 9. Verify linked alert was auto-resolved
    s2 = get_session()
    updated_alert = s2.query(PlantAlert).filter_by(id=alert_id).first()
    assert updated_alert.is_resolved is True
    assert updated_alert.resolved_at is not None
    s2.close()
