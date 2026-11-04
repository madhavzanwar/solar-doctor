# drone/tests/test_manual_schema.py
import pytest
from pydantic import ValidationError
from drone.common.manual import ManualInput
from drone.common.telemetry import Envelope


def test_manual_roundtrips():
    m = ManualInput(operator_id="op-1", vx=1.0, vy=-0.5, vz=0.0, yaw_rate=0.2, seq=3)
    again = ManualInput.model_validate_json(m.model_dump_json())
    assert again == m


def test_velocity_clamped_to_limits():
    with pytest.raises(ValidationError):
        ManualInput(operator_id="op-1", vx=999, vy=0, vz=0, yaw_rate=0, seq=0)


def test_envelope_carries_manual():
    env = Envelope(type="manual",
                   manual=ManualInput(operator_id="op-1", vx=0, vy=0, vz=0, yaw_rate=0, seq=0))
    rt = Envelope.model_validate_json(env.model_dump_json())
    assert rt.manual is not None and rt.manual.operator_id == "op-1"
