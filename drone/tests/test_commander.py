# drone/tests/test_commander.py
from drone.agent.commander import MavCommander


def test_protocol_surface_is_callable_via_duck_typing():
    # A fake satisfying the protocol can be used wherever MavCommander is expected.
    class Fake:
        def __init__(self):
            self.calls = []

        def arm(self): self.calls.append(("arm",))
        def disarm(self): self.calls.append(("disarm",))
        def set_mode(self, mode): self.calls.append(("set_mode", mode))
        def takeoff(self, alt_m): self.calls.append(("takeoff", alt_m))
        def rtl(self): self.calls.append(("rtl",))
        def land(self): self.calls.append(("land",))
        def goto(self, lat, lon, alt_m): self.calls.append(("goto", lat, lon, alt_m))
        def upload_mission(self, waypoints): self.calls.append(("upload_mission", len(waypoints)))

    f: MavCommander = Fake()
    f.arm()
    f.takeoff(40.0)
    assert f.calls == [("arm",), ("takeoff", 40.0)]
