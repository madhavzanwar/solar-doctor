# drone/tests/test_telemetry_schema.py
import time
import pytest
from pydantic import ValidationError
from drone.common.telemetry import Telemetry, LinkTier


def _valid_kwargs():
    return dict(
        drone_id="sitl-01",
        ts=time.time(),
        lat=28.4001,
        lon=77.1002,
        alt_rel_m=40.0,
        alt_amsl_m=255.0,
        heading_deg=90.0,
        groundspeed_ms=7.5,
        battery_pct=82.0,
        battery_voltage=22.1,
        mode="GUIDED",
        armed=False,
        gps_fix=3,
        satellites=14,
        roll_deg=1.2,
        pitch_deg=-0.5,
        yaw_deg=90.0,
        seq=42,
    )


def test_telemetry_roundtrips_through_json():
    t = Telemetry(**_valid_kwargs())
    raw = t.model_dump_json()
    again = Telemetry.model_validate_json(raw)
    assert again == t
    assert again.link_tier == LinkTier.GREEN  # default until computed


def test_heading_must_be_within_0_360():
    kw = _valid_kwargs()
    kw["heading_deg"] = 400.0
    with pytest.raises(ValidationError):
        Telemetry(**kw)


def test_battery_pct_clamped_range():
    kw = _valid_kwargs()
    kw["battery_pct"] = 150.0
    with pytest.raises(ValidationError):
        Telemetry(**kw)
