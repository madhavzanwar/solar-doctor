# drone/common/commands.py
"""Command, acknowledgement, and control-lock message schemas.

These ride the same WebSocket as telemetry via the shared Envelope. Keeping them
in their own module avoids an import cycle: telemetry.Envelope imports these, and
these import nothing from telemetry.
"""
from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class CommandType(str, Enum):
    ARM = "ARM"
    DISARM = "DISARM"
    TAKEOFF = "TAKEOFF"
    RTL = "RTL"
    LAND = "LAND"
    PAUSE = "PAUSE"            # hold position (BRAKE)
    RESUME = "RESUME"          # continue AUTO mission
    GOTO = "GOTO"             # fly to a lat/lon/alt (guided)
    SET_MODE = "SET_MODE"
    UPLOAD_MISSION = "UPLOAD_MISSION"


class Command(BaseModel):
    cmd_id: str
    type: CommandType
    params: dict = Field(default_factory=dict)


class Ack(BaseModel):
    cmd_id: str
    success: bool
    message: str = ""


class ControlAction(str, Enum):
    ACQUIRE = "acquire"
    RELEASE = "release"
    STATUS = "status"


class ControlMsg(BaseModel):
    action: ControlAction
    operator_id: str = ""
    granted: bool | None = None   # set by relay in the reply
    holder: str | None = None     # current lock holder, set by relay in the reply
