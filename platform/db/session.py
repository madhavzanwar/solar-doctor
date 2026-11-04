"""Database session management for the Axalon platform."""
import os
import threading
from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from axalon.db.models import Base
from axalon.db.url import resolve_db_url

_engine = None
_SessionLocal = None
_lock = threading.Lock()


def init_db(db_url: str | None = None) -> None:
    """Initialize engine and create all tables. Call once at startup."""
    global _engine, _SessionLocal
    # resolve_db_url() anchors a relative SQLite path to the repo root, so the
    # API finds the same file regardless of the directory uvicorn is started in.
    db_url = resolve_db_url(db_url)

    is_sqlite = db_url.startswith("sqlite")
    # check_same_thread is a SQLite-only connect arg; Postgres/MySQL reject it.
    connect_args = {"check_same_thread": False} if is_sqlite else {}
    _engine = create_engine(db_url, connect_args=connect_args)

    if is_sqlite:
        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragma(conn, _record):
            conn.execute("PRAGMA foreign_keys=ON")
            # WAL lets the API read while a background job writes, avoiding
            # "database is locked" errors; synchronous=NORMAL is the safe,
            # recommended pairing with WAL. SQLite-only — never reached for
            # PostgreSQL since this listener is gated by is_sqlite.
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")

    Base.metadata.create_all(_engine)

    # Apply local-dev migrations for columns added to existing tables.
    from axalon.db.migrate import run_migrations
    run_migrations(_engine)

    _SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False)


def get_engine():
    """Return the shared engine, initializing it on first call."""
    if _engine is None:
        with _lock:
            if _engine is None:
                init_db()
    return _engine


def get_session():
    """Return a new SQLAlchemy session. Caller is responsible for closing."""
    if _SessionLocal is None:
        with _lock:
            if _SessionLocal is None:
                init_db()
    return _SessionLocal()


@contextmanager
def session_scope(engine=None):
    """Context manager yielding a session that auto-commits/rolls back on exit."""
    session = get_session()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
