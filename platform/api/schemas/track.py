"""Track workspace request schemas (login, password, notes)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class LoginRequest(BaseModel):
    password: str | None = None


class PasswordSetRequest(BaseModel):
    new_password: str | None = None
    current_password: str | None = None


class NoteBody(BaseModel):
    title: str | None = None
    kind: str | None = None
    body: str | None = None
    url: str | None = None
    tags: Any | None = None
