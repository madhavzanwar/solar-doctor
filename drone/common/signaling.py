# drone/common/signaling.py
"""WebRTC signaling messages, carried over the same Envelope as everything else.

The relay treats these as opaque except for `operator_id`, which it uses to route
the frame to the right peer (signaling is per-peer, unlike telemetry fan-out).
"""
from __future__ import annotations

from enum import Enum
from pydantic import BaseModel


class SignalKind(str, Enum):
    OFFER = "offer"
    ANSWER = "answer"
    ICE = "ice"
    BYE = "bye"


class SignalMsg(BaseModel):
    kind: SignalKind
    operator_id: str
    sdp: str | None = None
    candidate: dict | None = None
