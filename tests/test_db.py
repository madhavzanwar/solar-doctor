"""Tests for SQLAlchemy database layer."""
import json
import pytest


@pytest.fixture
def db_session():
    """Provide an in-memory DB session with FK enforcement enabled."""
    from axalon.db.session import init_db, get_session
    init_db("sqlite:///:memory:")
    session = get_session()
    yield session
    session.close()


def test_models_importable():
    from axalon.db.models import Base, Park, Inspection, Detection
    assert Park.__tablename__ == "parks"
    assert Inspection.__tablename__ == "inspections"
    assert Detection.__tablename__ == "detections"


def test_init_db_creates_tables(db_session):
    from axalon.db.models import Park
    assert db_session.query(Park).count() == 0


def test_create_park(db_session):
    from axalon.db.models import Park
    park = Park(id="PARK_01", name="Test Farm", mode="auto", total_panels=120, rows=10, cols=12)
    db_session.add(park)
    db_session.commit()
    retrieved = db_session.query(Park).filter_by(id="PARK_01").first()
    assert retrieved is not None
    assert retrieved.name == "Test Farm"
    assert retrieved.total_panels == 120


def test_create_inspection_and_detection(db_session):
    from axalon.db.models import Park, Inspection, Detection
    park = Park(id="PARK_02", name="Alpha Farm", mode="auto")
    db_session.add(park)
    db_session.flush()  # insert park before inspection references it
    insp = Inspection(
        id="BATCH-PARK_02-20260411-120000",
        park_id="PARK_02",
        flight_date="2026-04-11",
        total_images=10,
        total_detections=3,
        summary=json.dumps({"CRITICAL": 1, "HIGH": 1, "MEDIUM": 1, "LOW": 0}),
    )
    db_session.add(insp)
    db_session.flush()  # insert inspection before detection references it
    det = Detection(
        inspection_id="BATCH-PARK_02-20260411-120000",
        image_id="thermal_001",
        panel_id="R3-C7",
        class_="hot-spot-high",
        class_id=10,
        severity="CRITICAL",
        confidence=0.87,
        bbox=json.dumps([100, 200, 150, 250]),
        gps=json.dumps({"lat": 28.4, "lon": 77.1}),
    )
    db_session.add(det)
    db_session.commit()
    detections = db_session.query(Detection).filter_by(inspection_id="BATCH-PARK_02-20260411-120000").all()
    assert len(detections) == 1
    assert detections[0].severity == "CRITICAL"
    assert detections[0].panel_id == "R3-C7"


def test_get_session_auto_inits(monkeypatch):
    """get_session() auto-calls init_db() if not yet initialized."""
    import axalon.db.session as sess_mod
    # Patch default URL to in-memory so no file is written to disk
    original_init = sess_mod.init_db
    monkeypatch.setattr(sess_mod, "_engine", None)
    monkeypatch.setattr(sess_mod, "_SessionLocal", None)
    monkeypatch.setattr(sess_mod, "init_db",
                        lambda url="sqlite:///:memory:": original_init(url))
    session = sess_mod.get_session()
    assert session is not None
    session.close()
