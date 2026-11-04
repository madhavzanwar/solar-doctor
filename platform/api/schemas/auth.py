"""Users-mode request schemas: login, user admin, share links.

Permissive like the other schemas — `axalon.core.auth` owns validation so the
error messages stay consistent between the API and the bootstrap path.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class UserLogin(BaseModel):
    email: Any | None = None
    password: Any | None = None


class UserCreate(BaseModel):
    email: Any | None = None
    password: Any | None = None
    role: Any | None = None
    project_ids: list[int] | None = None


class UserUpdate(BaseModel):
    role: Any | None = None
    disabled: bool | None = None
    password: Any | None = None
    project_ids: list[int] | None = None


class ShareLinkCreate(BaseModel):
    project_id: int | None = None
    label: str | None = None
    expires_in_days: Any | None = 7
