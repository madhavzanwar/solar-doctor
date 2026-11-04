"""Alembic must reach head on a database whose tables the app already created.

`axalon.db.session.init_db` runs `Base.metadata.create_all()`, so any process that
touches the database before migrations run (a request, a script, an earlier app
version) creates tables for every model. A migration that then issues a bare
CREATE TABLE fails, `_run_alembic_migrations` only logs the error, and the
database is stuck at the previous revision forever — every later migration
silently never runs. Found on a real dev database stuck at 0008.
"""
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config


def _alembic_cfg(db_url: str) -> Config:
    repo_root = Path(__file__).resolve().parents[2]
    cfg = Config(str(repo_root / "alembic.ini"))
    cfg.set_main_option("script_location", str(repo_root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def _head_revision(cfg: Config) -> str:
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(cfg).get_current_head()


def test_upgrade_reaches_head_when_create_all_ran_first(tmp_path, monkeypatch):
    from axalon.db.models import Base

    # Arrange: schema at 0007 via alembic, then the app's create_all adds every
    # newer model table before the newer migrations get a chance to run.
    db_url = f"sqlite:///{tmp_path / 'pre_created.db'}"
    monkeypatch.setenv("AXALON_DB_URL", db_url)
    cfg = _alembic_cfg(db_url)
    command.upgrade(cfg, "0007")
    engine = sa.create_engine(db_url)
    Base.metadata.create_all(engine)

    # Act
    command.upgrade(cfg, "head")

    # Assert
    with engine.connect() as conn:
        version = conn.execute(sa.text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == _head_revision(cfg)


def test_upgrade_and_downgrade_round_trip_on_fresh_database(tmp_path, monkeypatch):
    db_url = f"sqlite:///{tmp_path / 'fresh.db'}"
    monkeypatch.setenv("AXALON_DB_URL", db_url)
    cfg = _alembic_cfg(db_url)

    command.upgrade(cfg, "head")
    command.downgrade(cfg, "0007")
    command.upgrade(cfg, "head")

    engine = sa.create_engine(db_url)
    insp = sa.inspect(engine)
    assert {"users", "user_sessions", "project_members", "share_links", "fault_photos"} <= set(
        insp.get_table_names()
    )
