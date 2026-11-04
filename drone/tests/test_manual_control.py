# drone/tests/test_manual_control.py
from drone.common.manual import ManualInput
from drone.agent.manual_control import ManualController, ManualDeadman


class FakeCommander:
    def __init__(self):
        self.velocities = []

    def send_velocity(self, vx, vy, vz, yaw_rate):
        self.velocities.append((vx, vy, vz, yaw_rate))


def test_apply_forwards_velocity_to_commander():
    c = FakeCommander()
    mc = ManualController(c)
    mc.apply(ManualInput(operator_id="op", seq=1, vx=1.0, vy=0.5, vz=0.0, yaw_rate=0.2))
    assert c.velocities == [(1.0, 0.5, 0.0, 0.2)]


def test_apply_ignores_stale_seq():
    c = FakeCommander()
    mc = ManualController(c)
    mc.apply(ManualInput(operator_id="op", seq=5, vx=1.0, vy=0, vz=0, yaw_rate=0))
    mc.apply(ManualInput(operator_id="op", seq=3, vx=2.0, vy=0, vz=0, yaw_rate=0))  # older
    assert c.velocities == [(1.0, 0, 0, 0)]  # stale frame ignored


def test_deadman_triggers_zero_velocity_after_timeout():
    c = FakeCommander()
    mc = ManualController(c)
    dm = ManualDeadman(timeout_s=0.4)
    mc.apply(ManualInput(operator_id="op", seq=1, vx=1.0, vy=0, vz=0, yaw_rate=0))
    dm.beat(now=10.0)
    assert dm.expired(now=10.2) is False
    assert dm.expired(now=10.5) is True
    mc.hover()
    assert c.velocities[-1] == (0.0, 0.0, 0.0, 0.0)
