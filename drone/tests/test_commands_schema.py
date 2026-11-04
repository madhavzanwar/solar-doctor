# drone/tests/test_commands_schema.py
import pytest
from pydantic import ValidationError
from drone.common.commands import (
    Command, Ack, ControlMsg, CommandType, ControlAction,
)
from drone.common.telemetry import Envelope


def test_command_roundtrips():
    c = Command(cmd_id="abc", type=CommandType.TAKEOFF, params={"alt": 40.0})
    again = Command.model_validate_json(c.model_dump_json())
    assert again == c
    assert again.type is CommandType.TAKEOFF
    assert again.params["alt"] == 40.0


def test_command_defaults_empty_params():
    c = Command(cmd_id="x", type=CommandType.RTL)
    assert c.params == {}


def test_unknown_command_type_rejected():
    with pytest.raises(ValidationError):
        Command(cmd_id="x", type="FLIP")


def test_envelope_carries_command_and_ack_and_control():
    env = Envelope(
        type="command",
        command=Command(cmd_id="1", type=CommandType.ARM),
    )
    rt = Envelope.model_validate_json(env.model_dump_json())
    assert rt.command is not None and rt.command.type is CommandType.ARM

    ack_env = Envelope(type="ack", ack=Ack(cmd_id="1", success=True, message="ok"))
    assert Envelope.model_validate_json(ack_env.model_dump_json()).ack.success is True

    ctl_env = Envelope(
        type="control",
        control=ControlMsg(action=ControlAction.ACQUIRE, operator_id="op-7"),
    )
    rt2 = Envelope.model_validate_json(ctl_env.model_dump_json())
    assert rt2.control.action is ControlAction.ACQUIRE
