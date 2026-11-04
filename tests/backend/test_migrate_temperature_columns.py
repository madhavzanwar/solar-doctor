"""run_migrations must add the nullable temperature columns to pre-existing DBs."""
from sqlalchemy import create_engine, inspect, text

from axalon.core.temp_extractor import TEMP_FIELDS


def test_run_migrations_adds_temperature_columns_to_legacy_detections(tmp_path):
    from axalon.db.migrate import run_migrations

    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with engine.begin() as conn:
        # Legacy detections table predating radiometric columns.
        conn.execute(text(
            "CREATE TABLE detections (id INTEGER PRIMARY KEY, inspection_id VARCHAR NOT NULL, "
            "fault_id INTEGER, image_id VARCHAR, panel_id VARCHAR, class VARCHAR, class_id INTEGER, "
            "severity VARCHAR, confidence FLOAT, bbox TEXT, gps TEXT, created_at DATETIME)"
        ))
        conn.execute(text("INSERT INTO detections (inspection_id, severity) VALUES ('I1', 'LOW')"))

    actions = run_migrations(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("detections")}
    assert set(TEMP_FIELDS) <= cols
    assert any("max_temp" in a for a in actions)

    with engine.connect() as conn:
        assert conn.execute(text("SELECT max_temp FROM detections")).scalar() is None

    # Idempotent: a second run adds nothing.
    assert not any("temp" in a for a in run_migrations(engine))
