"""Project request schemas."""
from __future__ import annotations

from pydantic import BaseModel


class ProjectBody(BaseModel):
    name: str | None = None
    status: str | None = None
    client: str | None = None
    description: str | None = None
