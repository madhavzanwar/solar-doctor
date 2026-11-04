"""Mission request schemas."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class MissionCreate(BaseModel):
    name: str | None = None
    park_id: str | None = None
    mission_type: str | None = None
    camera_id: str | None = None
    params: Any | None = None
    polygon: Any | None = None
    waypoints: Any | None = None
    area_ha: float | None = None
    image_count: int | None = None
