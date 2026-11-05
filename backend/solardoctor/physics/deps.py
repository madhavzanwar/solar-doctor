"""FastAPI dependency: one sync SQLAlchemy session per request (Axalon's get_session pattern)."""
from __future__ import annotations

from typing import Iterator

from sqlalchemy.orm import Session

from solardoctor.db.session import get_session


def get_db() -> Iterator[Session]:
    session = get_session()
    try:
        yield session
    finally:
        session.close()
