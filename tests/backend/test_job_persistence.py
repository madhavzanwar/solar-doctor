"""Verify that job state written by the API is readable after a fresh DB session."""
import pytest
from sqlalchemy import text


@pytest.fixture
def engine(tmp_path):
    from axalon.db.session import get_engine, init_db

    init_db(f"sqlite:///{tmp_path / 'jobs.db'}")
    return get_engine()


def test_job_table_exists(engine):
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'")
        ).fetchone()
    assert row is not None, "jobs table must exist after init_db"


def test_job_row_survives_reconnect(engine):
    from axalon.db.models import Job
    from axalon.db.session import session_scope

    job_id = "persist-test-001"
    with session_scope(engine) as s:
        s.add(Job(id=job_id, state="succeeded", park_id="P1", total=20, processed=20))

    with session_scope(engine) as s:
        job = s.query(Job).filter(Job.id == job_id).first()

    assert job is not None
    assert job.state == "succeeded"
    assert job.processed == 20


from axalon.db.models import FaultComment


def test_inspection_has_metadata_columns(db_session):
    from axalon.db.models import Inspection, Park
    park = Park(id="PARK_META_TEST", name="Meta Test Park")
    db_session.add(park)
    db_session.flush()
    insp = Inspection(
        id="TEST-META-01",
        park_id="PARK_META_TEST",
        flight_date="2026-06-01",
        client="Tata Solar",
        location="Rajasthan, India",
        capacity_mw=5.0,
        inspection_type="commissioning",
        inspection_level="standard",
        irradiance_wm2=850.0,
        wind_speed_bft=2.0,
        cloud_coverage_okta=1.0,
    )
    db_session.add(insp)
    db_session.commit()
    fetched = db_session.query(Inspection).filter_by(id="TEST-META-01").first()
    assert fetched.client == "Tata Solar"
    assert fetched.inspection_type == "commissioning"
    assert fetched.irradiance_wm2 == 850.0


def test_fault_comment_create_and_list(db_session):
    from axalon.db.models import Park, PanelFault, FAULT_OPEN
    park = Park(id="PARK_COMMENT_TEST", name="Comment Park")
    db_session.add(park)
    db_session.flush()
    fault = PanelFault(
        park_id="PARK_COMMENT_TEST",
        panel_id="R1-C1",
        class_="cell",
        class_id=0,
        severity="MEDIUM",
        status=FAULT_OPEN,
    )
    db_session.add(fault)
    db_session.flush()
    c1 = FaultComment(fault_id=fault.id, author="pilot", body="Anomaly detected")
    c2 = FaultComment(fault_id=fault.id, author="ground_crew", body="Physically confirmed")
    db_session.add_all([c1, c2])
    db_session.commit()
    comments = db_session.query(FaultComment).filter_by(fault_id=fault.id).all()
    assert len(comments) == 2
    assert comments[0].author == "pilot"
