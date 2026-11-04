# drone/tests/test_tier_policy_manual.py
from drone.common.telemetry import LinkTier
from drone.relay.tier_policy import authorize_manual


def test_manual_allowed_on_green_with_lock():
    ok, reason = authorize_manual(holds_lock=True, tier=LinkTier.GREEN)
    assert ok is True and reason == ""


def test_manual_blocked_on_amber():
    ok, reason = authorize_manual(holds_lock=True, tier=LinkTier.AMBER)
    assert ok is False
    assert "green" in reason.lower()


def test_manual_blocked_on_red():
    ok, _ = authorize_manual(holds_lock=True, tier=LinkTier.RED)
    assert ok is False


def test_manual_requires_lock():
    ok, reason = authorize_manual(holds_lock=False, tier=LinkTier.GREEN)
    assert ok is False
    assert "lock" in reason.lower()
