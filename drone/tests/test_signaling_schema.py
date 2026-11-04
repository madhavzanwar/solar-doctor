# drone/tests/test_signaling_schema.py
import pytest
from pydantic import ValidationError
from drone.common.signaling import SignalMsg, SignalKind
from drone.common.telemetry import Envelope


def test_offer_roundtrips():
    s = SignalMsg(kind=SignalKind.OFFER, operator_id="op-1", sdp="v=0...")
    again = SignalMsg.model_validate_json(s.model_dump_json())
    assert again == s
    assert again.kind is SignalKind.OFFER


def test_ice_candidate_carries_dict():
    s = SignalMsg(kind=SignalKind.ICE, operator_id="op-1",
                  candidate={"candidate": "candidate:...", "sdpMLineIndex": 0})
    assert s.candidate["sdpMLineIndex"] == 0


def test_unknown_kind_rejected():
    with pytest.raises(ValidationError):
        SignalMsg(kind="banana", operator_id="op-1")


def test_envelope_carries_signal():
    env = Envelope(type="signal",
                   signal=SignalMsg(kind=SignalKind.ANSWER, operator_id="op-2", sdp="v=0"))
    rt = Envelope.model_validate_json(env.model_dump_json())
    assert rt.signal is not None
    assert rt.signal.operator_id == "op-2"
    assert rt.signal.kind is SignalKind.ANSWER
