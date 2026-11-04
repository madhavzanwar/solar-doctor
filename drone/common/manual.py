# drone/common/manual.py
"""High-rate manual flight input. Sent ~15 Hz, no per-frame ack.

Velocities are body-frame and clamped at the schema boundary so a malformed or
hostile frame can never request an absurd speed.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

MAX_HORIZ_MS = 8.0
MAX_VERT_MS = 3.0
MAX_YAW_RATE = 1.5  # rad/s


class ManualInput(BaseModel):
    operator_id: str
    seq: int = Field(..., ge=0)
    vx: float = Field(..., ge=-MAX_HORIZ_MS, le=MAX_HORIZ_MS)  # forward
    vy: float = Field(..., ge=-MAX_HORIZ_MS, le=MAX_HORIZ_MS)  # right
    vz: float = Field(..., ge=-MAX_VERT_MS, le=MAX_VERT_MS)    # down
    yaw_rate: float = Field(..., ge=-MAX_YAW_RATE, le=MAX_YAW_RATE)
