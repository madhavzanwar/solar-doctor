"""Revision 0011 (physics tables) upgrades and downgrades cleanly on SQLite."""
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config

PHYSICS_TABLES = {
    "plants", "inverters", "strings", "telemetry", "forecasts",
    "plant_alerts", "diagnoses", "weather_cache",
}


def _cfg(db_url: str) -> Config:
    root = Path(__file__).resolve().parents[3]
    cfg = Config(str(root / "alembic.ini"))
    cfg.set_main_option("script_location", str(root / "alembic"))
    cfg.set_main_option("sqlalchemy.url", db_url)
    return cfg


def test_0011_upgrade_downgrade(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    monkeypatch.setenv("SOLARDOCTOR_DB_URL", url)
    cfg = _cfg(url)
    command.upgrade(cfg, "0010")
    eng = sa.create_engine(url)
    assert not (PHYSICS_TABLES & set(sa.inspect(eng).get_table_names()))

    command.upgrade(cfg, "0011")
    insp = sa.inspect(eng)
    assert PHYSICS_TABLES <= set(insp.get_table_names())
    assert any(i["column_names"] == ["plant_id", "ts"] for i in insp.get_indexes("telemetry"))
    assert any(fk["referred_table"] == "parks" for fk in insp.get_foreign_keys("plants"))
    assert any(u["column_names"] == ["park_id"] for u in insp.get_unique_constraints("plants"))

    command.downgrade(cfg, "0010")
    assert not (PHYSICS_TABLES & set(sa.inspect(eng).get_table_names()))
    command.upgrade(cfg, "head")
    assert PHYSICS_TABLES <= set(sa.inspect(eng).get_table_names())


def test_orm_models_match_migration_columns(tmp_path, monkeypatch):
    """The ORM (used by create_all) and the migration describe the same columns."""
    from solardoctor.physics import models  # noqa: F401
    from solardoctor.db.models import Base

    url = f"sqlite:///{tmp_path / 'm2.db'}"
    monkeypatch.setenv("SOLARDOCTOR_DB_URL", url)
    command.upgrade(_cfg(url), "head")
    insp = sa.inspect(sa.create_engine(url))
    for name in PHYSICS_TABLES:
        mig = {c["name"] for c in insp.get_columns(name)}
        orm = {c.name for c in Base.metadata.tables[name].columns}
        assert mig == orm, name


def test_0012_up_down_and_idempotent_over_create_all(tmp_path, monkeypatch):
    """0012 adds the deficit columns, removes them again, and tolerates create_all having run first."""
    from solardoctor.physics import models  # noqa: F401
    from solardoctor.db.models import Base

    new = {
        "plant_alerts": {"scope", "inverter_id", "string_id", "baseline", "evidence_json"},
        "plants": {"pi_warning", "pi_critical", "deficit_min_clear_hours"},
        "telemetry": {"curtailed"},
    }
    url = f"sqlite:///{tmp_path / 'm3.db'}"
    monkeypatch.setenv("SOLARDOCTOR_DB_URL", url)
    cfg = _cfg(url)
    eng = sa.create_engine(url)
    command.upgrade(cfg, "0011")
    for t, cols in new.items():
        assert not cols & {c["name"] for c in sa.inspect(eng).get_columns(t)}
    command.upgrade(cfg, "0012")
    for t, cols in new.items():
        assert cols <= {c["name"] for c in sa.inspect(eng).get_columns(t)}
    command.downgrade(cfg, "0011")
    for t, cols in new.items():
        assert not cols & {c["name"] for c in sa.inspect(eng).get_columns(t)}

    # create_all (ORM, already has the columns) before 0012 must not make it fail
    url2 = f"sqlite:///{tmp_path / 'm4.db'}"
    monkeypatch.setenv("SOLARDOCTOR_DB_URL", url2)
    cfg2 = _cfg(url2)
    command.upgrade(cfg2, "0011")
    command.downgrade(cfg2, "0010")
    Base.metadata.create_all(sa.create_engine(url2))
    command.upgrade(cfg2, "0012")
