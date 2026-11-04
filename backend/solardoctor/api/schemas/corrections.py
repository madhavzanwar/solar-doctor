"""Correction request schemas."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class CorrectionCreate(BaseModel):
    class_: str | None = None
    class_id: int | None = None
    bbox_norm: Any | None = None
    severity: str | None = None
    notes: str | None = None
    image_id: str | None = None
    panel_id: str | None = None
