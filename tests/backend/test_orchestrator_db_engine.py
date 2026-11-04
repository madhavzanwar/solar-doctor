"""Constructing the API's orchestrator must not repoint the shared DB engine.

InspectionOrchestrator defaulted to db_url="sqlite:///axalon.db" and called
init_db(db_url). The old init_db silently swapped that literal for
AXALON_DB_URL; once URL resolution honoured explicit arguments, the first batch
job re-initialised the process-wide engine onto a SQLite file. In production
(Supabase) the job row was created in Postgres and every later write — progress,
park, inspection, detections — went to SQLite, so the job stayed "queued".
Locally both URLs were SQLite, so nothing noticed.
"""


def test_default_orchestrator_keeps_the_configured_engine(tmp_path, monkeypatch):
    from axalon.db import session as db_session
    from axalon.pipeline import orchestrator as orch_module

    configured = tmp_path / "configured.db"
    monkeypatch.setenv("AXALON_DB_URL", f"sqlite:///{configured}")
    monkeypatch.setattr(db_session, "_engine", None)
    monkeypatch.setattr(db_session, "_SessionLocal", None)
    monkeypatch.setattr(orch_module, "SolarDetector", lambda **_kw: object())
    engine_before = db_session.get_engine()

    orch_module.InspectionOrchestrator(output_dir=tmp_path)

    assert db_session.get_engine() is engine_before
    assert str(db_session.get_engine().url).endswith("configured.db")


def test_explicit_db_url_still_initialises_that_database(tmp_path, monkeypatch):
    from axalon.db import session as db_session
    from axalon.pipeline import orchestrator as orch_module

    monkeypatch.setattr(db_session, "_engine", None)
    monkeypatch.setattr(db_session, "_SessionLocal", None)
    monkeypatch.setattr(orch_module, "SolarDetector", lambda **_kw: object())
    explicit = tmp_path / "explicit.db"

    orch_module.InspectionOrchestrator(output_dir=tmp_path, db_url=f"sqlite:///{explicit}")

    assert str(db_session.get_engine().url).endswith("explicit.db")
