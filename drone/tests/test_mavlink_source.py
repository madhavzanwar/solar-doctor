# drone/tests/test_mavlink_source.py
from types import SimpleNamespace
from drone.agent.mavlink_source import TelemetryAccumulator


def msg(type_name, **fields):
    m = SimpleNamespace(**fields)
    m.get_type = lambda: type_name
    return m


def test_accumulator_builds_telemetry_from_message_stream():
    acc = TelemetryAccumulator(drone_id="sitl-01")

    acc.update(msg("GLOBAL_POSITION_INT",
                   lat=284_000_000, lon=771_000_000,  # 1e7 degrees
                   relative_alt=40_000, alt=255_000,  # mm
                   hdg=9000,                            # cdeg
                   vx=500, vy=0))                       # cm/s
    acc.update(msg("ATTITUDE", roll=0.02, pitch=-0.01, yaw=1.57))
    acc.update(msg("SYS_STATUS", battery_remaining=82, voltage_battery=22100))
    acc.update(msg("GPS_RAW_INT", fix_type=3, satellites_visible=14))
    acc.update(msg("HEARTBEAT", custom_mode=4, base_mode=128))  # GUIDED, armed

    t = acc.build(ts=123.0, seq=1)
    assert t.drone_id == "sitl-01"
    assert round(t.lat, 4) == 28.4
    assert round(t.lon, 4) == 77.1
    assert t.alt_rel_m == 40.0
    assert t.alt_amsl_m == 255.0
    assert t.heading_deg == 90.0
    assert round(t.groundspeed_ms, 2) == 5.0
    assert t.battery_pct == 82.0
    assert round(t.battery_voltage, 1) == 22.1
    assert t.gps_fix == 3
    assert t.satellites == 14
    assert t.mode == "GUIDED"
    assert t.armed is True


def test_build_before_any_position_returns_none():
    acc = TelemetryAccumulator(drone_id="sitl-01")
    assert acc.build(ts=1.0, seq=0) is None
