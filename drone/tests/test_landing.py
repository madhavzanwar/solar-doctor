# drone/tests/test_landing.py
from drone.agent.landing import LandingDetector


def test_detects_arm_then_disarm_transition():
    d = LandingDetector()
    assert d.update(armed=False) is False
    assert d.update(armed=True) is False   # took off
    assert d.update(armed=True) is False
    assert d.update(armed=False) is True   # landed -> fire once


def test_fires_only_once_per_flight():
    d = LandingDetector()
    d.update(armed=True)
    assert d.update(armed=False) is True
    assert d.update(armed=False) is False  # already fired
    d.update(armed=True)                    # new flight
    assert d.update(armed=False) is True    # fires again


def test_no_fire_if_never_armed():
    d = LandingDetector()
    assert d.update(armed=False) is False
    assert d.update(armed=False) is False
