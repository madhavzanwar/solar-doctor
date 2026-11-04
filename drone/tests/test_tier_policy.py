# drone/tests/test_tier_policy.py
from drone.common.commands import CommandType
from drone.common.telemetry import LinkTier
from drone.relay.tier_policy import is_allowed, authorize_command


def test_amber_allows_mission_control_commands():
    assert is_allowed(LinkTier.AMBER, CommandType.TAKEOFF)
    assert is_allowed(LinkTier.AMBER, CommandType.RTL)
    assert is_allowed(LinkTier.AMBER, CommandType.UPLOAD_MISSION)


def test_green_allows_everything_amber_allows():
    for ct in CommandType:
        assert is_allowed(LinkTier.GREEN, ct)


def test_red_blocks_all_commands():
    for ct in CommandType:
        assert not is_allowed(LinkTier.RED, ct)


def test_authorize_requires_lock():
    ok, reason = authorize_command(
        holds_lock=False, tier=LinkTier.AMBER, cmd_type=CommandType.ARM
    )
    assert ok is False
    assert "lock" in reason.lower()


def test_authorize_blocks_command_on_red_tier():
    ok, reason = authorize_command(
        holds_lock=True, tier=LinkTier.RED, cmd_type=CommandType.TAKEOFF
    )
    assert ok is False
    assert "tier" in reason.lower()


def test_authorize_allows_when_lock_held_and_tier_permits():
    ok, reason = authorize_command(
        holds_lock=True, tier=LinkTier.AMBER, cmd_type=CommandType.GOTO
    )
    assert ok is True
    assert reason == ""
