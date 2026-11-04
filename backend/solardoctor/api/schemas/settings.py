"""Settings request schemas."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class SettingsUpdate(BaseModel):
    settings: Any | None = None
