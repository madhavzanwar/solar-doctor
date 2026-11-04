"""Single source of truth for the platform's database URL.

The API is started from an unrelated working directory on purpose: the repo
contains a ``platform/`` package directory that shadows the stdlib ``platform``
module, so ``run.sh`` runs uvicorn from ``/tmp``. A relative SQLite URL like
``sqlite:///axalon.db`` is resolved against the *process* working directory, so
that choice silently pointed the database at ``/tmp/axalon.db``: every restart
looked like a brand new install and every inspection written during a session
disappeared with the next reboot.

Relative SQLite paths are therefore anchored to the repository root instead of
the working directory. Absolute URLs (``sqlite:////var/lib/axalon.db``),
in-memory URLs, and non-SQLite URLs (Postgres in production) pass through
untouched.
"""
from __future__ import annotations

import os
from pathlib import Path

#: Repository root — ``platform/db/url.py`` → ``platform/db`` → ``platform`` → root.
REPO_ROOT = Path(__file__).resolve().parents[2]

DEFAULT_SQLITE_FILENAME = "axalon.db"


def resolve_db_url(db_url: str | None = None) -> str:
    """Return an absolute, cwd-independent database URL.

    Args:
        db_url: Explicit URL. Falls back to ``AXALON_DB_URL``, then to the
            default SQLite file in the repository root.
    """
    url = (db_url or "").strip() or os.getenv("AXALON_DB_URL", "").strip()
    if not url:
        return _sqlite_url(REPO_ROOT / DEFAULT_SQLITE_FILENAME)

    if not url.startswith("sqlite"):
        return url

    # sqlite:///relative/path → three slashes then a non-slash character.
    prefix, _, path = url.partition(":///")
    if not prefix or prefix != "sqlite" or not path:
        return url  # sqlite://, sqlite:////absolute, or a driver-qualified URL
    if path.startswith(":memory:") or path.startswith("/"):
        return url
    return _sqlite_url(REPO_ROOT / path)


def _sqlite_url(path: Path) -> str:
    return f"sqlite:///{path.resolve().as_posix()}"
