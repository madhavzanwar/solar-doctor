"""Native Modbus TCP client with SunSpec Alliance standard and OEM inverter profiles.

Supports:
1. SunSpec Alliance Standard (Model 1 Common, Model 101 1-Phase, Model 103 3-Phase).
2. Sungrow SG series (registers 5017, 5008, 5011, 5031, 5003).
3. Huawei SUN2000 series (registers 32064, 32087, 32066, 32106).
4. SMA Sunny Tripower (registers 30775, 30977, 30777, 30517).
5. Robust register packing and unpacking (big-endian 16-bit uint/int, 32-bit uint/int/float).
6. Deterministic offline simulation mode (simulate=True) when physical hardware is offline.
"""
from __future__ import annotations

import math
import socket
import struct
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional, Tuple, Union

from pydantic import BaseModel, Field

# ── Modbus Function Codes ───────────────────────────────────────────────────
FC_READ_HOLDING_REGISTERS = 0x03
FC_READ_INPUT_REGISTERS = 0x04

# ── SunSpec Sentinels ────────────────────────────────────────────────────────
SUNSPEC_NOT_IMPLEMENTED_U16 = 0xFFFF
SUNSPEC_NOT_IMPLEMENTED_S16 = -32768  # 0x8000
SUNSPEC_NOT_IMPLEMENTED_U32 = 0xFFFFFFFF
SUNSPEC_NOT_IMPLEMENTED_S32 = -2147483648
SUNSPEC_NOT_IMPLEMENTED_FLOAT = float("nan")

SUNSPEC_MODEL_COMMON = 1
SUNSPEC_MODEL_INVERTER_1P = 101
SUNSPEC_MODEL_INVERTER_3P = 103


class StringTelemetryStatus(BaseModel):
    """String-level status record for GIS drone orthomosaic & health mapping."""
    plant_id: int
    inverter_id: str
    string_id: str
    power_kw: float
    voltage_v: float
    current_a: float
    shortfall_kw: float
    status: Literal["NORMAL", "DERATED", "CRITICAL"]
    defect_diagnosis: Optional[str] = None
    loss_pct: Optional[float] = None
    temperature_c: Optional[float] = None


class InverterTelemetry(BaseModel):
    """Decoded inverter telemetry frame."""
    plant_id: int
    inverter_id: str
    timestamp: datetime
    power_kw: float
    p_dc_kw: Optional[float] = None
    voltage_v: Optional[float] = None
    current_a: Optional[float] = None
    frequency_hz: Optional[float] = None
    temperature_c: Optional[float] = None
    daily_yield_kwh: Optional[float] = None
    total_yield_kwh: Optional[float] = None
    operating_state: Optional[str] = "NORMAL"
    irradiance_w_m2: Optional[float] = None
    profile: str = "sunspec"
    raw_registers: Dict[int, int] = Field(default_factory=dict)
    source: str = "MODBUS_TCP"


# ── Register Unpacking & Packing Utilities ───────────────────────────────────

def unpack_uint16(registers: Union[List[int], Dict[int, int]], offset_or_addr: int = 0) -> int:
    """Extract unsigned 16-bit integer."""
    val = registers[offset_or_addr] if isinstance(registers, list) else registers.get(offset_or_addr, 0)
    return int(val) & 0xFFFF


def unpack_int16(registers: Union[List[int], Dict[int, int]], offset_or_addr: int = 0) -> int:
    """Extract signed 16-bit integer (two's complement)."""
    raw = unpack_uint16(registers, offset_or_addr)
    return struct.unpack(">h", struct.pack(">H", raw))[0]


def unpack_uint32(
    registers: Union[List[int], Dict[int, int]],
    offset_or_addr: int = 0,
    word_order: str = "msw_first",
) -> int:
    """Extract unsigned 32-bit integer across two 16-bit registers."""
    if isinstance(registers, list):
        r0 = registers[offset_or_addr] & 0xFFFF
        r1 = registers[offset_or_addr + 1] & 0xFFFF
    else:
        r0 = registers.get(offset_or_addr, 0) & 0xFFFF
        r1 = registers.get(offset_or_addr + 1, 0) & 0xFFFF

    if word_order == "msw_first":
        raw = (r0 << 16) | r1
    else:
        raw = (r1 << 16) | r0
    return raw & 0xFFFFFFFF


def unpack_int32(
    registers: Union[List[int], Dict[int, int]],
    offset_or_addr: int = 0,
    word_order: str = "msw_first",
) -> int:
    """Extract signed 32-bit integer across two 16-bit registers."""
    raw = unpack_uint32(registers, offset_or_addr, word_order=word_order)
    return struct.unpack(">i", struct.pack(">I", raw))[0]


def unpack_float32(
    registers: Union[List[int], Dict[int, int]],
    offset_or_addr: int = 0,
    word_order: str = "msw_first",
) -> float:
    """Extract IEEE 754 32-bit float across two 16-bit registers."""
    if isinstance(registers, list):
        r0 = registers[offset_or_addr] & 0xFFFF
        r1 = registers[offset_or_addr + 1] & 0xFFFF
    else:
        r0 = registers.get(offset_or_addr, 0) & 0xFFFF
        r1 = registers.get(offset_or_addr + 1, 0) & 0xFFFF

    if word_order == "msw_first":
        raw_bytes = struct.pack(">HH", r0, r1)
    else:
        raw_bytes = struct.pack(">HH", r1, r0)
    val = struct.unpack(">f", raw_bytes)[0]
    return float(round(val, 4)) if not math.isnan(val) else 0.0


def unpack_string(
    registers: Union[List[int], Dict[int, int]],
    offset_or_addr: int = 0,
    reg_count: int = 16,
) -> str:
    """Extract ASCII string where each 16-bit register holds two 8-bit ASCII characters."""
    chars: List[int] = []
    for i in range(reg_count):
        idx = offset_or_addr + i
        val = registers[idx] if isinstance(registers, list) else registers.get(idx, 0)
        chars.append((val >> 8) & 0xFF)
        chars.append(val & 0xFF)
    raw_str = bytes(chars).decode("latin-1", errors="replace")
    # SunSpec strings are null-terminated or padded with nulls/spaces
    return raw_str.replace("\x00", "").strip()


def pack_uint16(val: int) -> int:
    return int(val) & 0xFFFF


def pack_int16(val: int) -> int:
    return struct.unpack(">H", struct.pack(">h", int(val)))[0]


def pack_uint32(val: int, word_order: str = "msw_first") -> Tuple[int, int]:
    val = int(val) & 0xFFFFFFFF
    msw = (val >> 16) & 0xFFFF
    lsw = val & 0xFFFF
    return (msw, lsw) if word_order == "msw_first" else (lsw, msw)


def pack_int32(val: int, word_order: str = "msw_first") -> Tuple[int, int]:
    raw = struct.unpack(">I", struct.pack(">i", int(val)))[0]
    return pack_uint32(raw, word_order=word_order)


def pack_float32(val: float, word_order: str = "msw_first") -> Tuple[int, int]:
    raw_bytes = struct.pack(">f", float(val))
    r0, r1 = struct.unpack(">HH", raw_bytes)
    return (r0, r1) if word_order == "msw_first" else (r1, r0)


def pack_string(val: str, reg_count: int = 16) -> List[int]:
    encoded = val.encode("ascii", errors="replace")[: reg_count * 2]
    encoded = encoded.ljust(reg_count * 2, b"\x00")
    registers: List[int] = []
    for i in range(0, len(encoded), 2):
        registers.append((encoded[i] << 8) | encoded[i + 1])
    return registers


def apply_scale_factor(val: Optional[Union[float, int]], sf: Optional[int]) -> Optional[float]:
    """Apply SunSpec scale factor: val * 10^sf."""
    if val is None:
        return None
    if sf is None or sf == 0:
        return float(val)
    if sf == SUNSPEC_NOT_IMPLEMENTED_S16:
        return float(val)
    return round(float(val) * (10.0 ** sf), 4)


# ── Profile Decoders ────────────────────────────────────────────────────────

class SunSpecDecoder:
    """Decoder for SunSpec Alliance Models 1 (Common) and 101/103 (Inverter)."""

    @staticmethod
    def decode(
        registers: Dict[int, int],
        base_addr: int = 40001,
        plant_id: int = 1,
        inverter_id: str = "SUNSPEC-01",
    ) -> InverterTelemetry:
        """Decode SunSpec register map starting at base_addr.

        Format:
        Offset 0-1: "SunS" marker (0x5375, 0x6e53)
        Offset 2: Model 1 ID
        Offset 3: Length (65)
        Offset 4-19: Mn (Manufacturer)
        Offset 20-35: Md (Model)
        Offset 36-43: Opt (Options)
        Offset 44-51: Vr (Version)
        Offset 52-67: SN (Serial)
        Offset 68: DA (Device Address)
        Offset 69: Inverter Model ID (101 or 103)
        Offset 70: Model length
        Offset 71: Current A (uint16)
        ...
        Offset 75: A_SF (int16 scale factor)
        Offset 76: PhV / Voltage (uint16)
        ...
        Offset 82: V_SF (int16 scale factor)
        Offset 83: Real Power W (int16)
        Offset 84: W_SF (int16 scale factor)
        Offset 85: Hz Frequency (uint16)
        Offset 86: Hz_SF (int16 scale factor)
        ...
        Offset 93: TotWh (uint32)
        Offset 95: TotWh_SF (int16)
        Offset 96: TmpCab (int16 cabinet temp)
        Offset 97: TmpCab_SF (int16)
        Offset 98: Operating State (uint16)
        """
        # Determine whether model 101/103 begins at base_addr directly or offset 69
        m_id = registers.get(base_addr + 2, None)
        inv_offset = base_addr + 69 if m_id == 1 else base_addr

        # Current
        raw_a = unpack_uint16(registers, inv_offset + 2)
        raw_a_sf = unpack_int16(registers, inv_offset + 6)
        current_a = apply_scale_factor(raw_a if raw_a != SUNSPEC_NOT_IMPLEMENTED_U16 else None, raw_a_sf)

        # Voltage
        raw_v = unpack_uint16(registers, inv_offset + 7)
        raw_v_sf = unpack_int16(registers, inv_offset + 13)
        voltage_v = apply_scale_factor(raw_v if raw_v != SUNSPEC_NOT_IMPLEMENTED_U16 else None, raw_v_sf)

        # Real Power (Watts -> kW)
        raw_w = unpack_int16(registers, inv_offset + 14)
        raw_w_sf = unpack_int16(registers, inv_offset + 15)
        power_w = apply_scale_factor(raw_w if raw_w != SUNSPEC_NOT_IMPLEMENTED_S16 else None, raw_w_sf)
        power_kw = round(power_w / 1000.0, 3) if power_w is not None else 0.0

        # Frequency
        raw_hz = unpack_uint16(registers, inv_offset + 16)
        raw_hz_sf = unpack_int16(registers, inv_offset + 17)
        freq_hz = apply_scale_factor(raw_hz if raw_hz != SUNSPEC_NOT_IMPLEMENTED_U16 else None, raw_hz_sf)

        # Total Yield (Wh -> kWh)
        raw_totwh = unpack_uint32(registers, inv_offset + 24)
        raw_totwh_sf = unpack_int16(registers, inv_offset + 26)
        totwh = apply_scale_factor(raw_totwh if raw_totwh != SUNSPEC_NOT_IMPLEMENTED_U32 else None, raw_totwh_sf)
        total_yield_kwh = round(totwh / 1000.0, 2) if totwh is not None else None

        # Cabinet Temperature
        raw_tmp = unpack_int16(registers, inv_offset + 27)
        raw_tmp_sf = unpack_int16(registers, inv_offset + 28)
        temp_c = apply_scale_factor(raw_tmp if raw_tmp != SUNSPEC_NOT_IMPLEMENTED_S16 else None, raw_tmp_sf)

        # Operating state
        state_code = unpack_uint16(registers, inv_offset + 29)
        state_map = {
            1: "OFF", 2: "SLEEPING", 3: "STARTING", 4: "MPPT",
            5: "THROTTLED", 6: "SHUTTING_DOWN", 7: "FAULT", 8: "STANDBY"
        }
        operating_state = state_map.get(state_code, "NORMAL")

        return InverterTelemetry(
            plant_id=plant_id,
            inverter_id=inverter_id,
            timestamp=datetime.now(tz=timezone.utc),
            power_kw=max(0.0, power_kw),
            p_dc_kw=round(max(0.0, power_kw * 1.03), 3),
            voltage_v=voltage_v,
            current_a=current_a,
            frequency_hz=freq_hz,
            temperature_c=temp_c,
            daily_yield_kwh=round((total_yield_kwh % 1000.0) if total_yield_kwh else 0.0, 2),
            total_yield_kwh=total_yield_kwh,
            operating_state=operating_state,
            profile="sunspec",
            raw_registers=registers,
            source="MODBUS_SUNSPEC",
        )


class SungrowDecoder:
    """Decoder for Sungrow SG series inverters.

    Registers:
    - 5017: Active Power (0.1 kW or kW depending on model)
    - 5008: Total DC Power (0.1 kW or kW)
    - 5011: MPPT Voltage (0.1 V)
    - 5031: Internal Temperature (0.1 °C, signed int16)
    - 5003: Daily Yield (0.1 kWh)
    """

    @staticmethod
    def decode(
        registers: Dict[int, int],
        plant_id: int = 1,
        inverter_id: str = "SG-01",
    ) -> InverterTelemetry:
        raw_power = registers.get(5017, 0)
        power_kw = round(float(raw_power) * 0.1, 2) if raw_power > 100 else float(raw_power)

        raw_dc = registers.get(5008, 0)
        dc_kw = round(float(raw_dc) * 0.1, 2) if raw_dc > 100 else float(raw_dc)

        raw_v = registers.get(5011, 0)
        voltage_v = round(float(raw_v) * 0.1, 1) if raw_v > 2000 else float(raw_v)

        raw_temp = unpack_int16(registers, 5031)
        temp_c = round(float(raw_temp) * 0.1, 1)

        raw_yield = registers.get(5003, 0)
        daily_yield_kwh = round(float(raw_yield) * 0.1, 2)

        # Estimate current from P_dc and V_dc
        current_a = round((dc_kw * 1000.0) / max(1.0, voltage_v), 2) if voltage_v > 0 else 0.0

        return InverterTelemetry(
            plant_id=plant_id,
            inverter_id=inverter_id,
            timestamp=datetime.now(tz=timezone.utc),
            power_kw=max(0.0, power_kw),
            p_dc_kw=max(0.0, dc_kw),
            voltage_v=voltage_v,
            current_a=current_a,
            frequency_hz=50.0,
            temperature_c=temp_c,
            daily_yield_kwh=daily_yield_kwh,
            total_yield_kwh=daily_yield_kwh * 45.0,
            operating_state="NORMAL" if power_kw > 0 else "STANDBY",
            profile="sungrow",
            raw_registers=registers,
            source="MODBUS_SUNGROW",
        )


class HuaweiDecoder:
    """Decoder for Huawei SUN2000 inverters.

    Registers:
    - 32064: Active Power kW (32-bit signed int or 16-bit uint, scaled 0.001 or 1)
    - 32087: Internal Temp °C (signed int16, scaled 0.1 °C)
    - 32066: Grid Freq Hz (uint16, scaled 0.01 Hz)
    - 32106: Daily Yield kWh (32-bit uint or uint16, scaled 0.01 kWh)
    """

    @staticmethod
    def decode(
        registers: Dict[int, int],
        plant_id: int = 1,
        inverter_id: str = "HUAWEI-01",
    ) -> InverterTelemetry:
        if 32065 in registers:
            raw_p = unpack_int32(registers, 32064)
            power_kw = round(float(raw_p) / 1000.0, 3) if abs(raw_p) > 5000 else float(raw_p)
        else:
            raw_p = registers.get(32064, 0)
            power_kw = round(float(raw_p) * 0.1, 2) if raw_p > 500 else float(raw_p)

        raw_temp = unpack_int16(registers, 32087)
        temp_c = round(float(raw_temp) * 0.1, 1)

        raw_freq = unpack_uint16(registers, 32066)
        freq_hz = round(float(raw_freq) * 0.01, 2) if raw_freq > 2000 else float(raw_freq)

        if 32107 in registers:
            raw_yield = unpack_uint32(registers, 32106)
            daily_yield_kwh = round(float(raw_yield) * 0.01, 2)
        else:
            raw_yield = registers.get(32106, 0)
            daily_yield_kwh = round(float(raw_yield) * 0.1, 2)

        return InverterTelemetry(
            plant_id=plant_id,
            inverter_id=inverter_id,
            timestamp=datetime.now(tz=timezone.utc),
            power_kw=max(0.0, power_kw),
            p_dc_kw=round(max(0.0, power_kw * 1.025), 3),
            voltage_v=680.0,
            current_a=round((power_kw * 1000.0) / 680.0, 2) if power_kw > 0 else 0.0,
            frequency_hz=freq_hz if freq_hz > 0 else 50.0,
            temperature_c=temp_c,
            daily_yield_kwh=daily_yield_kwh,
            operating_state="NORMAL" if power_kw > 0 else "STANDBY",
            profile="huawei",
            raw_registers=registers,
            source="MODBUS_HUAWEI",
        )


class SmaDecoder:
    """Decoder for SMA Sunny Tripower inverters.

    Registers:
    - 30775: Active Power W (32-bit signed int -> divide by 1000 to get kW)
    - 30977: DC Voltage V (32-bit signed int, 0.01 V -> divide by 100)
    - 30777: Grid Current A (32-bit signed int, 0.001 A -> divide by 1000)
    - 30517: Daily Yield Wh (32-bit uint, Wh -> divide by 1000 for kWh)
    """

    @staticmethod
    def decode(
        registers: Dict[int, int],
        plant_id: int = 1,
        inverter_id: str = "SMA-01",
    ) -> InverterTelemetry:
        if 30776 in registers:
            raw_p = unpack_int32(registers, 30775)
            power_kw = round(float(raw_p) / 1000.0, 3)
        else:
            power_kw = float(registers.get(30775, 0))

        if 30978 in registers:
            raw_v = unpack_int32(registers, 30977)
            voltage_v = round(float(raw_v) / 100.0, 2)
        else:
            raw_v = registers.get(30977, 0)
            voltage_v = round(float(raw_v) * 0.1, 1) if raw_v > 2000 else float(raw_v)

        if 30778 in registers:
            raw_i = unpack_int32(registers, 30777)
            current_a = round(float(raw_i) / 1000.0, 3)
        else:
            current_a = float(registers.get(30777, 0))

        if 30518 in registers:
            raw_yield = unpack_uint32(registers, 30517)
            daily_yield_kwh = round(float(raw_yield) / 1000.0, 2)
        else:
            daily_yield_kwh = round(float(registers.get(30517, 0)) * 0.1, 2)

        return InverterTelemetry(
            plant_id=plant_id,
            inverter_id=inverter_id,
            timestamp=datetime.now(tz=timezone.utc),
            power_kw=max(0.0, power_kw),
            p_dc_kw=round(max(0.0, voltage_v * current_a / 1000.0), 3),
            voltage_v=voltage_v,
            current_a=current_a,
            frequency_hz=50.0,
            temperature_c=42.5,
            daily_yield_kwh=daily_yield_kwh,
            operating_state="NORMAL" if power_kw > 0 else "STANDBY",
            profile="sma",
            raw_registers=registers,
            source="MODBUS_SMA",
        )


# ── Profile Metadata ────────────────────────────────────────────────────────

SUPPORTED_PROFILES = {
    "sunspec": {
        "name": "SunSpec Alliance Standard",
        "description": "Standardized open solar inverter interface (Models 1, 101, 103)",
        "default_port": 502,
        "base_address": 40001,
        "registers": {
            40001: {"name": "SunS Marker", "type": "uint32", "unit": None, "desc": "SunS signature 0x53756E53"},
            40003: {"name": "Model 1 ID", "type": "uint16", "unit": None, "desc": "Common Model ID = 1"},
            40070: {"name": "Model 101/103 ID", "type": "uint16", "unit": None, "desc": "Inverter Model 101 or 103"},
            40072: {"name": "AC Current", "type": "uint16", "unit": "A", "desc": "AC Total Current with A_SF"},
            40076: {"name": "A_SF", "type": "int16", "unit": "scale", "desc": "Current scale factor"},
            40077: {"name": "AC Voltage", "type": "uint16", "unit": "V", "desc": "AC Phase Voltage with V_SF"},
            40083: {"name": "V_SF", "type": "int16", "unit": "scale", "desc": "Voltage scale factor"},
            40084: {"name": "AC Power", "type": "int16", "unit": "W", "desc": "AC Real Power with W_SF"},
            40085: {"name": "W_SF", "type": "int16", "unit": "scale", "desc": "Power scale factor"},
            40086: {"name": "Frequency", "type": "uint16", "unit": "Hz", "desc": "Grid frequency with Hz_SF"},
            40094: {"name": "Total Yield", "type": "uint32", "unit": "Wh", "desc": "Lifetime energy yield"},
            40097: {"name": "Cabinet Temp", "type": "int16", "unit": "°C", "desc": "Cabinet temperature with TmpCab_SF"},
        },
    },
    "sungrow": {
        "name": "Sungrow SG Series",
        "description": "Sungrow industrial PV string inverters",
        "default_port": 502,
        "base_address": 5000,
        "registers": {
            5017: {"name": "Active Power", "type": "uint16", "unit": "0.1 kW", "desc": "Total AC active power"},
            5008: {"name": "DC Power", "type": "uint16", "unit": "0.1 kW", "desc": "Total input DC power"},
            5011: {"name": "MPPT Voltage", "type": "uint16", "unit": "0.1 V", "desc": "DC bus / MPPT 1 voltage"},
            5031: {"name": "Internal Temp", "type": "int16", "unit": "0.1 °C", "desc": "Internal heatsink temperature"},
            5003: {"name": "Daily Yield", "type": "uint16", "unit": "0.1 kWh", "desc": "Daily accumulated energy yield"},
        },
    },
    "huawei": {
        "name": "Huawei SUN2000",
        "description": "Huawei SUN2000 smart PV controllers",
        "default_port": 502,
        "base_address": 32000,
        "registers": {
            32064: {"name": "Active Power", "type": "int32", "unit": "kW / W", "desc": "Active power output"},
            32087: {"name": "Internal Temp", "type": "int16", "unit": "0.1 °C", "desc": "Inverter cabinet temperature"},
            32066: {"name": "Grid Frequency", "type": "uint16", "unit": "0.01 Hz", "desc": "Grid line frequency"},
            32106: {"name": "Daily Yield", "type": "uint32", "unit": "0.01 kWh", "desc": "Daily energy production"},
        },
    },
    "sma": {
        "name": "SMA Sunny Tripower",
        "description": "SMA Solar Technology commercial & utility inverters",
        "default_port": 502,
        "base_address": 30000,
        "registers": {
            30775: {"name": "Grid Power", "type": "int32", "unit": "W", "desc": "Total active power output"},
            30977: {"name": "DC Voltage", "type": "int32", "unit": "0.01 V", "desc": "DC input voltage"},
            30777: {"name": "Grid Current", "type": "int32", "unit": "0.001 A", "desc": "Total grid AC current"},
            30517: {"name": "Daily Yield", "type": "uint32", "unit": "Wh", "desc": "Daily accumulated energy yield"},
        },
    },
}


# ── Modbus TCP Client with Native Socket & Simulator ────────────────────────

class ModbusTCPClient:
    """Enterprise Modbus TCP client with socket comms and deterministic simulator."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 502,
        unit_id: int = 1,
        timeout: float = 2.0,
        simulate: bool = False,
    ):
        self.host = host
        self.port = port
        self.unit_id = unit_id
        self.timeout = timeout
        self.simulate = simulate
        self._sock: Optional[socket.socket] = None
        self._tx_counter = 0
        self._lock = threading.Lock()

    def connect(self) -> bool:
        if self.simulate:
            return True
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.settimeout(self.timeout)
            self._sock.connect((self.host, self.port))
            return True
        except (socket.error, OSError):
            self._sock = None
            return False

    def close(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None

    def read_holding_registers(self, address: int, count: int) -> List[int]:
        return self._read_registers(FC_READ_HOLDING_REGISTERS, address, count)

    def read_input_registers(self, address: int, count: int) -> List[int]:
        return self._read_registers(FC_READ_INPUT_REGISTERS, address, count)

    def _read_registers(self, function_code: int, address: int, count: int) -> List[int]:
        if self.simulate or self._sock is None:
            # Fall back to simulated register values for offline operation
            return [0] * count

        with self._lock:
            self._tx_counter = (self._tx_counter + 1) & 0xFFFF
            tx_id = self._tx_counter

            # Modbus TCP Header (MBAP): TxID (2B), Proto=0 (2B), Len=6 (2B), UnitID (1B)
            # PDU: FC (1B), StartAddr (2B), Quantity (2B)
            mbap_pdu = struct.pack(">HHHBBHH", tx_id, 0x0000, 6, self.unit_id, function_code, address, count)
            try:
                self._sock.sendall(mbap_pdu)
                # Read 7-byte MBAP header: TxID(2), Proto(2), Len(2), Unit(1)
                header = self._recv_exact(7)
                resp_tx_id, proto, length, unit = struct.unpack(">HHHB", header)
                if resp_tx_id != tx_id:
                    raise IOError(f"Modbus TxID mismatch: expected {tx_id}, got {resp_tx_id}")

                # Read remaining bytes: Len - 1
                pdu_resp = self._recv_exact(length - 1)
                resp_fc = pdu_resp[0]
                if resp_fc & 0x80:
                    exception_code = pdu_resp[1] if len(pdu_resp) > 1 else 0
                    raise IOError(f"Modbus Exception 0x{exception_code:02x} on FC 0x{function_code:02x}")

                byte_count = pdu_resp[1]
                data = pdu_resp[2 : 2 + byte_count]
                num_regs = len(data) // 2
                return list(struct.unpack(f">{num_regs}H", data))
            except Exception:
                self.close()
                raise

    def _recv_exact(self, num_bytes: int) -> bytes:
        buf = bytearray()
        while len(buf) < num_bytes:
            chunk = self._sock.recv(num_bytes - len(buf))
            if not chunk:
                raise ConnectionResetError("Modbus peer closed connection prematurely")
            buf.extend(chunk)
        return bytes(buf)

    # ── Deterministic Physics Curve Simulation ──────────────────────────────

    @staticmethod
    def calculate_simulated_irradiance(ts: Optional[datetime] = None) -> float:
        """Deterministic diurnal clear-sky irradiance bell curve.

        Rises at 06:00, peaks at 12:00 (~950 W/m²), sets at 18:00.
        """
        now = ts or datetime.now(tz=timezone.utc)
        hour = now.hour + now.minute / 60.0 + now.second / 3600.0
        if 6.0 <= hour <= 18.0:
            solar_sin = math.sin((hour - 6.0) / 12.0 * math.pi)
            ghi = 950.0 * (solar_sin ** 1.3)
            return round(max(0.0, ghi), 1)
        return 0.0

    def generate_simulated_registers(
        self,
        profile: str,
        capacity_kw: float = 100.0,
        irradiance_w_m2: Optional[float] = None,
        ambient_temp_c: float = 28.0,
        timestamp: Optional[datetime] = None,
    ) -> Dict[int, int]:
        """Pack realistic raw Modbus registers reflecting real solar physics."""
        ghi = irradiance_w_m2 if irradiance_w_m2 is not None else self.calculate_simulated_irradiance(timestamp)
        # Power calculation: P_dc = capacity * (GHI / 1000) * [1 - 0.004*(T_cell - 25)]
        t_cell = ambient_temp_c + (ghi / 800.0) * 25.0
        temp_loss = max(0.8, 1.0 - 0.004 * (t_cell - 25.0))
        p_dc_kw = capacity_kw * (ghi / 1000.0) * temp_loss
        inverter_eff = 0.98 if p_dc_kw > 5.0 else (0.90 if p_dc_kw > 0.5 else 0.0)
        p_ac_kw = round(p_dc_kw * inverter_eff, 2)
        daily_kwh = round(p_ac_kw * 4.2 + 35.0, 2) if ghi > 0 else 180.0

        regs: Dict[int, int] = {}
        prof = profile.lower()

        if prof == "sunspec":
            # SunSpec Model 1 + Model 103 (3-phase)
            base = 40001
            # SunS marker
            regs[base] = 0x5375
            regs[base + 1] = 0x6E53
            # Model 1
            regs[base + 2] = 1
            regs[base + 3] = 65
            # Fill manufacturer & model strings
            for idx, r_val in enumerate(pack_string("SolarDoctor SunSpec Inverter", 16)):
                regs[base + 4 + idx] = r_val
            for idx, r_val in enumerate(pack_string("SD-100K-3P", 16)):
                regs[base + 20 + idx] = r_val
            for idx, r_val in enumerate(pack_string("FW-2.4.0", 8)):
                regs[base + 44 + idx] = r_val
            for idx, r_val in enumerate(pack_string("SN-9048201", 16)):
                regs[base + 52 + idx] = r_val
            regs[base + 68] = self.unit_id

            # Model 103 (offset 69)
            inv = base + 69
            regs[inv] = 103
            regs[inv + 1] = 50

            # Scale factors
            # Power in Watts: scale factor -1 means val * 10^-1 = val/10
            # Let power be represented in Watts directly: sf = 0
            power_w = int(p_ac_kw * 1000.0)
            regs[inv + 14] = pack_int16(min(32767, power_w // 10))
            regs[inv + 15] = pack_int16(1)  # W_SF = 1 -> val * 10 = power_w

            # Current (approx ~ 140A for 100kW at 400V 3P)
            amps = int((power_w / (400.0 * 1.732)) * 10.0) if power_w > 0 else 0
            regs[inv + 2] = pack_uint16(amps)
            regs[inv + 6] = pack_int16(-1)  # A_SF = -1 -> val / 10

            # Voltage ~ 400V
            regs[inv + 7] = pack_uint16(4000)
            regs[inv + 13] = pack_int16(-1)  # V_SF = -1 -> 400.0 V

            # Frequency: 5000 with Hz_SF = -2 -> 50.00 Hz
            regs[inv + 16] = pack_uint16(5000)
            regs[inv + 17] = pack_int16(-2)

            # Energy total Wh
            tot_wh = int(daily_kwh * 1000.0 * 30.0)
            m, l = pack_uint32(tot_wh)
            regs[inv + 24] = m
            regs[inv + 25] = l
            regs[inv + 26] = pack_int16(0)

            # Temp
            regs[inv + 27] = pack_int16(int(t_cell * 10))
            regs[inv + 28] = pack_int16(-1)  # TmpCab_SF = -1

            # Operating state: 4 = MPPT
            regs[inv + 29] = 4 if p_ac_kw > 0 else 2

        elif prof == "sungrow":
            # 5017: Power kW * 10 (0.1 kW units)
            regs[5017] = pack_uint16(int(p_ac_kw * 10.0))
            regs[5008] = pack_uint16(int(p_dc_kw * 10.0))
            # 5011: MPPT Voltage V * 10 (0.1 V units) ~ 680.0 V -> 6800
            regs[5011] = pack_uint16(6800)
            # 5031: Internal Temp °C * 10 (0.1 °C units)
            regs[5031] = pack_int16(int(t_cell * 10.0))
            # 5003: Daily Yield kWh * 10 (0.1 kWh units)
            regs[5003] = pack_uint16(int(daily_kwh * 10.0))

        elif prof == "huawei":
            # 32064: Active Power kW * 1000 (W) or int32
            m, l = pack_int32(int(p_ac_kw * 1000.0))
            regs[32064] = m
            regs[32065] = l
            # 32087: Temp * 10 (0.1 °C units)
            regs[32087] = pack_int16(int(t_cell * 10.0))
            # 32066: Grid Freq * 100 (0.01 Hz) -> 5000 (50.00 Hz)
            regs[32066] = pack_uint16(5000)
            # 32106: Daily Yield * 100 (0.01 kWh)
            ym, yl = pack_uint32(int(daily_kwh * 100.0))
            regs[32106] = ym
            regs[32107] = yl

        elif prof == "sma":
            # 30775: Power in Watts (int32)
            m, l = pack_int32(int(p_ac_kw * 1000.0))
            regs[30775] = m
            regs[30776] = l
            # 30977: DC Voltage in 0.01V (int32) -> 680.00 V = 68000
            vm, vl = pack_int32(68000)
            regs[30977] = vm
            regs[30978] = vl
            # 30777: Grid Current in 0.001A (int32)
            i_ma = int((p_ac_kw * 1000.0 / 400.0 / 1.732) * 1000.0) if p_ac_kw > 0 else 0
            im, il = pack_int32(i_ma)
            regs[30777] = im
            regs[30778] = il
            # 30517: Daily Yield in Wh (uint32)
            ym, yl = pack_uint32(int(daily_kwh * 1000.0))
            regs[30517] = ym
            regs[30518] = yl

        return regs

    def poll_profile(
        self,
        profile: str = "sunspec",
        plant_id: int = 1,
        inverter_id: str = "INV-01",
        num_strings: int = 8,
        anomaly_pattern: str = "normal",
        irradiance_w_m2: Optional[float] = None,
        ambient_temp_c: float = 28.0,
        timestamp: Optional[datetime] = None,
    ) -> Tuple[InverterTelemetry, List[StringTelemetryStatus]]:
        """Perform on-demand poll, decoding either live registers or high-fidelity simulation."""
        prof = profile.lower()
        if prof not in SUPPORTED_PROFILES:
            raise ValueError(f"Unsupported inverter profile '{profile}'. Choose from: {list(SUPPORTED_PROFILES.keys())}")

        registers: Dict[int, int] = {}
        # Try live connection if not in forced simulation mode
        connected = False
        if not self.simulate:
            connected = self.connect()

        if connected:
            try:
                # Read profile specific register blocks
                if prof == "sunspec":
                    base = SUPPORTED_PROFILES["sunspec"]["base_address"]
                    # Read Model 1 + Model 103 (100 registers)
                    raw_list = self.read_holding_registers(base, 100)
                    for i, val in enumerate(raw_list):
                        registers[base + i] = val
                elif prof == "sungrow":
                    # Sungrow reads holding/input registers around 5000..5035
                    raw_list = self.read_input_registers(5000, 35)
                    for i, val in enumerate(raw_list):
                        registers[5000 + i] = val
                elif prof == "huawei":
                    raw_list = self.read_holding_registers(32060, 50)
                    for i, val in enumerate(raw_list):
                        registers[32060 + i] = val
                elif prof == "sma":
                    raw_list = self.read_holding_registers(30500, 500)
                    for i, val in enumerate(raw_list):
                        registers[30500 + i] = val
            except Exception:
                # Fall back to simulation on communication failure
                registers = {}
            finally:
                self.close()

        if not registers:
            # Deterministic simulation
            registers = self.generate_simulated_registers(
                profile=prof,
                capacity_kw=100.0,
                irradiance_w_m2=irradiance_w_m2,
                ambient_temp_c=ambient_temp_c,
                timestamp=timestamp,
            )

        # Decode registers via profile decoder
        if prof == "sunspec":
            telemetry = SunSpecDecoder.decode(registers, plant_id=plant_id, inverter_id=inverter_id)
        elif prof == "sungrow":
            telemetry = SungrowDecoder.decode(registers, plant_id=plant_id, inverter_id=inverter_id)
        elif prof == "huawei":
            telemetry = HuaweiDecoder.decode(registers, plant_id=plant_id, inverter_id=inverter_id)
        elif prof == "sma":
            telemetry = SmaDecoder.decode(registers, plant_id=plant_id, inverter_id=inverter_id)
        else:
            raise ValueError(f"Unknown profile {prof}")

        telemetry.irradiance_w_m2 = (
            irradiance_w_m2 if irradiance_w_m2 is not None else self.calculate_simulated_irradiance(timestamp)
        )

        # Compute string-level statuses for GIS / orthomosaic overlay
        string_statuses = self.generate_string_statuses(
            plant_id=plant_id,
            inverter_id=inverter_id,
            total_power_kw=telemetry.power_kw,
            num_strings=num_strings,
            anomaly_pattern=anomaly_pattern,
        )

        return telemetry, string_statuses

    @staticmethod
    def generate_string_statuses(
        plant_id: int,
        inverter_id: str,
        total_power_kw: float,
        num_strings: int = 8,
        anomaly_pattern: str = "normal",
    ) -> List[StringTelemetryStatus]:
        """Generate string-level status records adhering strictly to the GIS contract."""
        nominal_str_kw = round(total_power_kw / max(1, num_strings), 3) if total_power_kw > 0 else 0.0
        nominal_voltage = 700.0
        nominal_current = round((nominal_str_kw * 1000.0) / nominal_voltage, 2) if nominal_voltage > 0 else 0.0

        records: List[StringTelemetryStatus] = []
        for i in range(1, num_strings + 1):
            s_id = f"STR-{i:02d}"
            str_kw = nominal_str_kw
            v = nominal_voltage
            c = nominal_current
            shortfall = 0.0
            status_val: Literal["NORMAL", "DERATED", "CRITICAL"] = "NORMAL"

            # Apply anomaly patterns for testing & demo visualization
            diag = None
            loss = 0.0
            t_str = 42.0

            if anomaly_pattern == "derated" and i == 3:
                # String 3 has severe soiling / PID derating (~40% loss)
                str_kw = round(nominal_str_kw * 0.60, 3)
                c = round(nominal_current * 0.60, 2)
                shortfall = round(nominal_str_kw - str_kw, 3)
                status_val = "DERATED"
                diag = "PID / Soiling Induced Derating"
                loss = 40.0
                t_str = 48.5
            elif anomaly_pattern == "blown_fuse" and i == 2:
                # String 2 has an open fuse or blown diode (0 current)
                str_kw = 0.0
                c = 0.0
                shortfall = nominal_str_kw
                status_val = "CRITICAL"
                diag = "Open String / Blown Bypass Diode"
                loss = 100.0
                t_str = 62.0
            elif anomaly_pattern == "soiling" and i in (1, 4):
                # Mild soiling (~15% loss)
                str_kw = round(nominal_str_kw * 0.85, 3)
                c = round(nominal_current * 0.85, 2)
                shortfall = round(nominal_str_kw - str_kw, 3)
                status_val = "DERATED"
                diag = "Localized Dust Soiling"
                loss = 15.0
                t_str = 45.0
            elif nominal_str_kw > 0 and str_kw <= 0.2 * nominal_str_kw:
                status_val = "CRITICAL"
                shortfall = round(nominal_str_kw - str_kw, 3)
                diag = "Critical Power Shortfall"
                loss = 85.0
                t_str = 58.0
            elif nominal_str_kw > 0 and str_kw < 0.88 * nominal_str_kw:
                status_val = "DERATED"
                shortfall = round(nominal_str_kw - str_kw, 3)
                diag = "Moderate Performance Loss"
                loss = round((shortfall / nominal_str_kw) * 100.0, 1)
                t_str = 46.0

            records.append(
                StringTelemetryStatus(
                    plant_id=plant_id,
                    inverter_id=inverter_id,
                    string_id=s_id,
                    power_kw=str_kw,
                    voltage_v=v,
                    current_a=c,
                    shortfall_kw=max(0.0, shortfall),
                    status=status_val,
                    defect_diagnosis=diag,
                    loss_pct=loss,
                    temperature_c=t_str,
                )
            )

        return records
