# drone/common/telemetry.py
"""Wire format shared by the drone agent and the relay.

This is the single source of truth for the telemetry frame. Both the agent
(producer) and the relay/browser (consumers) validate against it so the wire
contract can never silently drift.
"""
from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field

from drone.common.commands import Ack, Command, ControlMsg
from drone.common.signaling import SignalMsg
from drone.common.manual import ManualInput


class LinkTier(str, Enum):
    GREEN = "GREEN"   # low latency, manual unlocked (later phases)
    AMBER = "AMBER"   # usable, mission-control only
    RED = "RED"       # degraded/lost, commands disabled


class Telemetry(BaseModel):
    """One telemetry sample, normalized from MAVLink."""
    drone_id: str
    ts: float = Field(..., description="Unix seconds when sampled on the agent")
    seq: int = Field(..., ge=0, description="Monotonic frame counter from the agent")

    lat: float = Field(..., ge=-90.0, le=90.0)
    lon: float = Field(..., ge=-180.0, le=180.0)
    alt_rel_m: float
    alt_amsl_m: float
    heading_deg: float = Field(..., ge=0.0, le=360.0)
    groundspeed_ms: float = Field(..., ge=0.0)

    battery_pct: float = Field(..., ge=0.0, le=100.0)
    battery_voltage: float = Field(..., ge=0.0)

    mode: str
    armed: bool
    gps_fix: int = Field(..., ge=0)
    satellites: int = Field(..., ge=0)

    roll_deg: float
    pitch_deg: float
    yaw_deg: float

    link_tier: LinkTier = LinkTier.GREEN


class Envelope(BaseModel):
    """Top-level frame on the wire. `type` discriminates message kinds:
    'telemetry' | 'command' | 'ack' | 'control' | 'signal' | 'manual' | 'heartbeat'."""
    type: str
    telemetry: Telemetry | None = None
    command: Command | None = None
    ack: Ack | None = None
    control: ControlMsg | None = None
    signal: SignalMsg | None = None
    manual: ManualInput | None = None
    ts: float | None = None   # used by heartbeat frames for RTT measurement
