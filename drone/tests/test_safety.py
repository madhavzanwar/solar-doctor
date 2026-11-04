# drone/tests/test_safety.py
from drone.common.telemetry import LinkTier
from drone.agent.safety import Deadman, tier_from_rtt


def test_tier_green_under_50ms():
    assert tier_from_rtt(0.02) is LinkTier.GREEN


def test_tier_amber_under_300ms():
    assert tier_from_rtt(0.20) is LinkTier.AMBER


def test_tier_red_above_300ms():
    assert tier_from_rtt(0.5) is LinkTier.RED


def test_tier_red_when_rtt_unknown():
    assert tier_from_rtt(None) is LinkTier.RED


def test_deadman_not_expired_after_recent_beat():
    dm = Deadman(timeout_s=3.0)
    dm.beat(now=100.0)
    assert dm.expired(now=102.0) is False


def test_deadman_expires_after_timeout():
    dm = Deadman(timeout_s=3.0)
    dm.beat(now=100.0)
    assert dm.expired(now=104.0) is True


def test_deadman_expired_before_any_beat():
    dm = Deadman(timeout_s=3.0)
    assert dm.expired(now=1.0) is True
