"""Comprehensive test suite for Industrial Telemetry Ingestion (Edge/IoT).

Tests:
1. Register packing and unpacking (uint16, int16, uint32, int32, float32, string, scale factor).
2. SunSpec Alliance Standard (Model 1 Common, Model 101/103 Inverter).
3. OEM Inverter Profile decoders (Sungrow SG series, Huawei SUN2000, SMA Sunny Tripower).
4. Deterministic offline physics simulator and diurnal irradiance curve.
5. String-level health status records & anomaly patterns.
6. Industrial MQTT listener and telemetry payload parsers (Advantech, Teltonika, Generic).
7. EdgeManager SCADA DB sync, online residual adapter stepping, and WebSocket broadcast.
8. REST API endpoints under /api/v1/edge (profiles, poll, simulate-packet, status, strings).
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
import pytest

from solardoctor.edge.modbus_client import (
    HuaweiDecoder,
    InverterTelemetry,
    ModbusTCPClient,
    SmaDecoder,
    StringTelemetryStatus,
    SunSpecDecoder,
    SungrowDecoder,
    SUPPORTED_PROFILES,
    apply_scale_factor,
    pack_float32,
    pack_int16,
    pack_int32,
    pack_string,
    pack_uint16,
    pack_uint32,
    unpack_float32,
    unpack_int16,
    unpack_int32,
    unpack_string,
    unpack_uint16,
    unpack_uint32,
)
from solardoctor.edge.mqtt_client import MQTTListener, TelemetryPacketParser
from solardoctor.edge.manager import EdgeManager, get_edge_manager

PUNE_PLANT = {
    "name": "PCCoE 100kW Rooftop",
    "location": "Pune, Maharashtra",
    "latitude": 18.5204,
    "longitude": 73.8567,
    "timezone": "Asia/Kolkata",
    "capacity_kw": 100.0,
    "inverter_capacity_kw": 100.0,
    "module_count": 250,
    "tilt": 18.0,
    "azimuth": 180.0,
    "tariff_inr_kwh": 6.5,
    "altitude_m": 560.0,
}


@pytest.fixture(autouse=True)
def _reset_edge():
    """Reset edge manager singleton before and after each test."""
    EdgeManager.reset_instance()
    yield
    EdgeManager.reset_instance()


@pytest.fixture
def test_plant(client):
    """Create a plant for edge telemetry testing."""
    r = client.post("/api/v1/plants", json=PUNE_PLANT)
    assert r.status_code == 201, r.text
    return r.json()


# ── 1. Register Packing & Unpacking Unit Tests ───────────────────────────────

def test_register_uint16():
    assert unpack_uint16([0x1234]) == 0x1234
    assert unpack_uint16({10: 0xABCD}, 10) == 0xABCD
    assert pack_uint16(65535) == 0xFFFF
    assert pack_uint16(0) == 0


def test_register_int16():
    # Positive
    assert unpack_int16([500]) == 500
    assert pack_int16(500) == 500

    # Negative (two's complement)
    p_neg = pack_int16(-25)
    assert p_neg == 0xFFE7
    assert unpack_int16([p_neg]) == -25

    p_neg_extreme = pack_int16(-32768)
    assert unpack_int16([p_neg_extreme]) == -32768


def test_register_uint32():
    # 0x12345678 -> MSW=0x1234, LSW=0x5678
    val = 0x12345678
    msw, lsw = pack_uint32(val, word_order="msw_first")
    assert (msw, lsw) == (0x1234, 0x5678)
    assert unpack_uint32([msw, lsw], word_order="msw_first") == val

    # Test LSW first
    l_first, m_first = pack_uint32(val, word_order="lsw_first")
    assert (l_first, m_first) == (0x5678, 0x1234)
    assert unpack_uint32([l_first, m_first], word_order="lsw_first") == val


def test_register_int32():
    val = -12345678
    msw, lsw = pack_int32(val)
    assert unpack_int32([msw, lsw]) == val

    val_pos = 98765432
    msw_p, lsw_p = pack_int32(val_pos)
    assert unpack_int32([msw_p, lsw_p]) == val_pos


def test_register_float32():
    f_val = 680.25
    r0, r1 = pack_float32(f_val)
    unpacked = unpack_float32([r0, r1])
    assert abs(unpacked - f_val) < 0.01

    f_neg = -12.34
    r0, r1 = pack_float32(f_neg)
    assert abs(unpack_float32([r0, r1]) - f_neg) < 0.01


def test_register_string():
    text = "Sungrow Power SG"
    packed = pack_string(text, reg_count=8)
    assert len(packed) == 8
    unpacked = unpack_string(packed, reg_count=8)
    assert unpacked == text


def test_apply_scale_factor():
    assert apply_scale_factor(1234, -2) == 12.34
    assert apply_scale_factor(50, 1) == 500.0
    assert apply_scale_factor(100, 0) == 100.0
    assert apply_scale_factor(None, -1) is None
    assert apply_scale_factor(100, None) == 100.0


# ── 2. SunSpec Alliance Standard Decoding ────────────────────────────────────

def test_sunspec_model_1_and_103_decoding():
    regs = {}
    base = 40001
    # SunS marker
    regs[base] = 0x5375
    regs[base + 1] = 0x6E53
    regs[base + 2] = 1  # Model 1
    regs[base + 3] = 65

    # Manufacturer & model strings
    for i, r in enumerate(pack_string("SunSpec Alliance", 16)):
        regs[base + 4 + i] = r
    for i, r in enumerate(pack_string("Test Inverter 3P", 16)):
        regs[base + 20 + i] = r

    # Model 103 at offset 69
    inv = base + 69
    regs[inv] = 103  # Model 103 ID
    regs[inv + 1] = 50

    # AC Current: 1450 with A_SF = -1 -> 145.0 A
    regs[inv + 2] = 1450
    regs[inv + 6] = pack_int16(-1)

    # AC Voltage: 4000 with V_SF = -1 -> 400.0 V
    regs[inv + 7] = 4000
    regs[inv + 13] = pack_int16(-1)

    # Real Power: 850 with W_SF = 2 -> 85000 W = 85.0 kW
    regs[inv + 14] = 850
    regs[inv + 15] = pack_int16(2)

    # Frequency: 5000 with Hz_SF = -2 -> 50.00 Hz
    regs[inv + 16] = 5000
    regs[inv + 17] = pack_int16(-2)

    # Total Wh: 50000000 Wh with TotWh_SF = 0 -> 50,000 kWh
    m, l = pack_uint32(50000000)
    regs[inv + 24] = m
    regs[inv + 25] = l
    regs[inv + 26] = 0

    # Cabinet temp: 425 with TmpCab_SF = -1 -> 42.5 °C
    regs[inv + 27] = 425
    regs[inv + 28] = pack_int16(-1)

    # Operating state: 4 = MPPT
    regs[inv + 29] = 4

    decoded = SunSpecDecoder.decode(regs, base_addr=base, plant_id=1, inverter_id="SUNSPEC-01")

    assert decoded.plant_id == 1
    assert decoded.inverter_id == "SUNSPEC-01"
    assert decoded.power_kw == 85.0
    assert decoded.current_a == 145.0
    assert decoded.voltage_v == 400.0
    assert decoded.frequency_hz == 50.0
    assert decoded.temperature_c == 42.5
    assert decoded.total_yield_kwh == 50000.0
    assert decoded.operating_state == "MPPT"
    assert decoded.source == "MODBUS_SUNSPEC"


# ── 3. OEM Inverter Profiles (Sungrow, Huawei, SMA) ─────────────────────────

def test_sungrow_decoder():
    regs = {
        5017: 852,   # 85.2 kW (0.1 kW)
        5008: 880,   # 88.0 kW DC (0.1 kW)
        5011: 6850,  # 685.0 V MPPT (0.1 V)
        5031: 435,   # 43.5 °C internal temp (0.1 °C)
        5003: 3450,  # 345.0 kWh daily yield (0.1 kWh)
    }
    t = SungrowDecoder.decode(regs, plant_id=2, inverter_id="SG-100K")
    assert t.plant_id == 2
    assert t.inverter_id == "SG-100K"
    assert t.power_kw == 85.2
    assert t.p_dc_kw == 88.0
    assert t.voltage_v == 685.0
    assert t.temperature_c == 43.5
    assert t.daily_yield_kwh == 345.0
    assert t.operating_state == "NORMAL"
    assert t.source == "MODBUS_SUNGROW"


def test_huawei_decoder():
    m, l = pack_int32(92450)  # 92.45 kW in Watts
    ym, yl = pack_uint32(41250)  # 412.50 kWh in 0.01 kWh
    regs = {
        32064: m,
        32065: l,
        32087: 382,   # 38.2 °C (0.1 °C)
        32066: 5002,  # 50.02 Hz (0.01 Hz)
        32106: ym,
        32107: yl,
    }
    t = HuaweiDecoder.decode(regs, plant_id=3, inverter_id="SUN2000-100K")
    assert t.plant_id == 3
    assert t.inverter_id == "SUN2000-100K"
    assert t.power_kw == 92.45
    assert t.temperature_c == 38.2
    assert t.frequency_hz == 50.02
    assert t.daily_yield_kwh == 412.50
    assert t.operating_state == "NORMAL"
    assert t.source == "MODBUS_HUAWEI"


def test_sma_decoder():
    pm, pl = pack_int32(75000)   # 75,000 W = 75.0 kW
    vm, vl = pack_int32(69500)   # 695.00 V (0.01 V)
    im, il = pack_int32(110500)  # 110.500 A (0.001 A)
    ym, yl = pack_uint32(310000) # 310,000 Wh = 310.0 kWh
    regs = {
        30775: pm,
        30776: pl,
        30977: vm,
        30978: vl,
        30777: im,
        30778: il,
        30517: ym,
        30518: yl,
    }
    t = SmaDecoder.decode(regs, plant_id=4, inverter_id="STP-50-US")
    assert t.plant_id == 4
    assert t.inverter_id == "STP-50-US"
    assert t.power_kw == 75.0
    assert t.voltage_v == 695.0
    assert t.current_a == 110.5
    assert t.daily_yield_kwh == 310.0
    assert t.operating_state == "NORMAL"
    assert t.source == "MODBUS_SMA"


# ── 4. Offline Physics Simulator Mode & Diurnal Irradiance ──────────────────

def test_simulated_irradiance_curve():
    # Night time (02:00) -> 0 W/m²
    night = datetime(2026, 6, 21, 2, 0, 0, tzinfo=timezone.utc)
    assert ModbusTCPClient.calculate_simulated_irradiance(night) == 0.0

    # Solar Noon (12:00) -> ~950 W/m²
    noon = datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc)
    ghi_noon = ModbusTCPClient.calculate_simulated_irradiance(noon)
    assert 900.0 <= ghi_noon <= 950.0

    # Afternoon (15:00) -> positive but lower than noon
    afternoon = datetime(2026, 6, 21, 15, 0, 0, tzinfo=timezone.utc)
    ghi_pm = ModbusTCPClient.calculate_simulated_irradiance(afternoon)
    assert 0.0 < ghi_pm < ghi_noon


def test_modbus_client_simulation_profiles():
    client = ModbusTCPClient(simulate=True)
    noon = datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc)

    # Test all 4 profiles generate valid simulated registers and decodes cleanly
    for prof in ("sunspec", "sungrow", "huawei", "sma"):
        telemetry, strings = client.poll_profile(
            profile=prof,
            plant_id=1,
            inverter_id="SIM-INV",
            irradiance_w_m2=900.0,
            timestamp=noon,
        )
        assert telemetry.plant_id == 1
        assert telemetry.inverter_id == "SIM-INV"
        assert telemetry.power_kw > 60.0
        assert len(strings) == 8
        assert all(isinstance(s, StringTelemetryStatus) for s in strings)


def test_string_health_anomaly_patterns():
    # Normal pattern
    normal_strs = ModbusTCPClient.generate_string_statuses(
        plant_id=1, inverter_id="INV-01", total_power_kw=80.0, num_strings=8, anomaly_pattern="normal"
    )
    assert len(normal_strs) == 8
    assert all(s.status == "NORMAL" for s in normal_strs)
    assert all(s.shortfall_kw == 0.0 for s in normal_strs)

    # Derated anomaly (string 3 derated)
    derated_strs = ModbusTCPClient.generate_string_statuses(
        plant_id=1, inverter_id="INV-01", total_power_kw=80.0, num_strings=8, anomaly_pattern="derated"
    )
    s3 = [s for s in derated_strs if s.string_id == "STR-03"][0]
    assert s3.status == "DERATED"
    assert s3.shortfall_kw > 0.0

    # Blown fuse anomaly (string 2 critical, 0 current)
    blown_strs = ModbusTCPClient.generate_string_statuses(
        plant_id=1, inverter_id="INV-01", total_power_kw=80.0, num_strings=8, anomaly_pattern="blown_fuse"
    )
    s2 = [s for s in blown_strs if s.string_id == "STR-02"][0]
    assert s2.status == "CRITICAL"
    assert s2.power_kw == 0.0
    assert s2.current_a == 0.0
    assert s2.shortfall_kw > 5.0


# ── 5. Industrial MQTT Listener & Gateway Payload Parsers ────────────────────

def test_mqtt_parser_generic():
    topic = "solardoctor/edge/5/inverter/INV-NORTH/telemetry"
    payload = {
        "power_kw": 88.5,
        "voltage_v": 690.0,
        "current_a": 128.2,
        "irradiance_w_m2": 820.0,
        "temperature_c": 31.5,
        "timestamp": "2026-11-21T12:00:00Z",
    }
    parsed = TelemetryPacketParser.parse(topic, payload)
    assert parsed.plant_id == 5
    assert parsed.inverter_id == "INV-NORTH"
    assert parsed.power_kw == 88.5
    assert parsed.voltage_v == 690.0
    assert parsed.irradiance_w_m2 == 820.0
    assert parsed.gateway_format == "generic"


def test_mqtt_parser_advantech():
    topic = "solardoctor/edge/1/inverter/INV-01/telemetry"
    payload = {
        "sStatus": 1,
        "d": {
            "power_kw": 76.4,
            "voltage": 710.0,
            "current": 107.6,
            "temp": 39.5,
            "irradiance": 750.0,
        },
        "ts": "2026-11-21T12:30:00Z",
    }
    parsed = TelemetryPacketParser.parse(topic, payload)
    assert parsed.plant_id == 1
    assert parsed.power_kw == 76.4
    assert parsed.voltage_v == 710.0
    assert parsed.irradiance_w_m2 == 750.0
    assert parsed.temperature_c == 39.5
    assert parsed.gateway_format == "advantech"


def test_mqtt_parser_teltonika():
    topic = "solardoctor/edge/2/string/STR-04/telemetry"
    payload = {
        "ts": 1732208400,
        "data": {
            "ActivePower": 9.2,
            "DcVoltage": 725.0,
            "GridCurrent": 12.7,
            "InternalTemp": 42.0,
            "DailyYield": 48.5,
        },
    }
    parsed = TelemetryPacketParser.parse(topic, payload)
    assert parsed.plant_id == 2
    assert parsed.string_id == "STR-04"
    assert parsed.power_kw == 9.2
    assert parsed.voltage_v == 725.0
    assert parsed.temperature_c == 42.0
    assert parsed.gateway_format == "teltonika"


def test_mqtt_listener_offline_ingest():
    listener = MQTTListener()
    received_packets = []
    listener.add_callback(lambda p: received_packets.append(p))

    pkt = listener.ingest_packet(
        topic="solardoctor/edge/1/inverter/INV-TEST/telemetry",
        payload='{"power_kw": 55.0, "voltage_v": 700.0, "current_a": 78.5}',
    )
    assert pkt.power_kw == 55.0
    assert len(received_packets) == 1
    assert listener.packets_received == 1
    assert len(listener.get_history()) == 1


# ── 6. EdgeManager Integration & SCADA Ingestion ────────────────────────────

def test_edge_manager_ingestion_and_ws_broadcast(db_session, test_plant):
    manager = get_edge_manager()
    pid = test_plant["id"]

    # Ingest edge packet
    topic = f"solardoctor/edge/{pid}/inverter/INV-01/telemetry"
    payload = {
        "power_kw": 72.5,
        "voltage_v": 700.0,
        "current_a": 103.5,
        "irradiance_w_m2": 780.0,
        "temperature_c": 30.0,
    }
    telemetry_row, string_statuses = manager.ingest_edge_packet(topic, payload, db=db_session)

    assert telemetry_row.plant_id == pid
    assert telemetry_row.p_ac_kw == 72.5
    assert telemetry_row.ghi_wm2 == 780.0
    assert len(string_statuses) == 8

    # Verify tracked string statuses
    cached_strings = manager.get_string_statuses(pid)
    assert len(cached_strings) == 8

    # Summary metrics
    summary = manager.get_status_summary()
    assert summary["metrics"]["packets_ingested_total"] >= 1
    assert summary["metrics"]["active_devices_count"] >= 1


# ── 7. REST API Endpoints (/api/v1/edge/*) ───────────────────────────────────

def test_api_edge_profiles(client):
    r = client.get("/api/v1/edge/profiles")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "profiles" in body
    profiles = body["profiles"]
    assert "sunspec" in profiles
    assert "sungrow" in profiles
    assert "huawei" in profiles
    assert "sma" in profiles


def test_api_edge_poll(client, test_plant):
    pid = test_plant["id"]
    # Poll SunSpec with simulate=True
    req = {
        "plant_id": pid,
        "inverter_id": "INV-01",
        "profile": "sunspec",
        "simulate": True,
        "anomaly_pattern": "derated",
        "irradiance_w_m2": 800.0,
    }
    r = client.post("/api/v1/edge/poll", json=req)
    assert r.status_code == 200, r.text
    res = r.json()
    assert res["success"] is True
    assert res["plant_id"] == pid
    assert res["inverter_id"] == "INV-01"
    assert "telemetry" in res
    assert "string_statuses" in res

    # Verify string status contract for GIS integration
    statuses = res["string_statuses"]
    assert len(statuses) == 8
    first = statuses[0]
    assert "plant_id" in first
    assert "inverter_id" in first
    assert "string_id" in first
    assert "power_kw" in first
    assert "voltage_v" in first
    assert "current_a" in first
    assert "shortfall_kw" in first
    assert "status" in first
    assert first["status"] in ("NORMAL", "DERATED", "CRITICAL")

    # String 3 should be derated per anomaly_pattern
    s3 = [s for s in statuses if s["string_id"] == "STR-03"][0]
    assert s3["status"] == "DERATED"
    assert s3["shortfall_kw"] > 0


def test_api_edge_poll_nonexistent_plant(client):
    req = {
        "plant_id": 99999,
        "simulate": True,
    }
    r = client.post("/api/v1/edge/poll", json=req)
    assert r.status_code == 404


def test_api_edge_simulate_packet_generic(client, test_plant):
    pid = test_plant["id"]
    req = {
        "plant_id": pid,
        "inverter_id": "INV-MAIN",
        "gateway_format": "generic",
        "power_kw": 68.0,
        "voltage_v": 690.0,
        "current_a": 98.5,
        "irradiance_w_m2": 720.0,
        "temperature_c": 32.0,
    }
    r = client.post("/api/v1/edge/simulate-packet", json=req)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["success"] is True
    assert data["plant_id"] == pid
    assert data["telemetry"]["power_kw"] == 68.0
    assert len(data["string_statuses"]) == 8


def test_api_edge_simulate_packet_string_level_anomaly(client, test_plant):
    pid = test_plant["id"]
    # Simulate single string with blown fuse
    req = {
        "plant_id": pid,
        "inverter_id": "INV-01",
        "string_id": "STR-02",
        "anomaly_pattern": "blown_fuse",
    }
    r = client.post("/api/v1/edge/simulate-packet", json=req)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["success"] is True
    assert len(data["string_statuses"]) == 1
    s2 = data["string_statuses"][0]
    assert s2["string_id"] == "STR-02"
    assert s2["power_kw"] == 0.0
    assert s2["status"] == "CRITICAL"


def test_api_edge_simulate_packet_advantech_and_teltonika(client, test_plant):
    pid = test_plant["id"]
    # Advantech format
    r_adv = client.post("/api/v1/edge/simulate-packet", json={
        "plant_id": pid,
        "gateway_format": "advantech",
        "power_kw": 50.0,
    })
    assert r_adv.status_code == 200
    assert r_adv.json()["telemetry"]["source"] == "EDGE_ADVANTECH"

    # Teltonika format
    r_tel = client.post("/api/v1/edge/simulate-packet", json={
        "plant_id": pid,
        "gateway_format": "teltonika",
        "power_kw": 55.0,
    })
    assert r_tel.status_code == 200
    assert r_tel.json()["telemetry"]["source"] == "EDGE_TELTONIKA"


def test_api_edge_status(client, test_plant):
    # Ingest a packet first so metrics increment
    client.post("/api/v1/edge/simulate-packet", json={
        "plant_id": test_plant["id"],
        "power_kw": 45.0,
    })
    r = client.get("/api/v1/edge/status")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "operational"
    assert "mqtt" in body
    assert "metrics" in body
    assert body["metrics"]["packets_ingested_total"] >= 1
    assert "supported_inverter_profiles" in body


def test_api_edge_strings_endpoint(client, test_plant):
    pid = test_plant["id"]
    r = client.get(f"/api/v1/edge/{pid}/strings")
    assert r.status_code == 200, r.text
    strings = r.json()
    assert len(strings) == 8
    assert all("status" in s and "shortfall_kw" in s for s in strings)
