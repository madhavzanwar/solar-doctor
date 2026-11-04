"""Park request schemas."""
from __future__ import annotations

from pydantic import BaseModel


class ParkUpdate(BaseModel):
    name: str | None = None
    project_id: int | None = None
