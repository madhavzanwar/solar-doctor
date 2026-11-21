"""SolarDoctor Edge & IoT Telemetry Ingestion package.

Industrial telemetry interfaces supporting Modbus TCP (SunSpec, Sungrow, Huawei, SMA)
and MQTT gateway telemetry with offline ingestion and digital twin synchronization.
"""
from __future__ import annotations

from solardoctor.edge.modbus_client import (
    InverterTelemetry,
    ModbusTCPClient,
    SmaDecoder,
    StringTelemetryStatus,
    SunSpecDecoder,
    SungrowDecoder,
    HuaweiDecoder,
    SUPPORTED_PROFILES,
    apply_scale_factor,
    unpack_float32,
    unpack_int16,
    unpack_int32,
    unpack_string,
    unpack_uint16,
    unpack_uint32,
)
from solardoctor.edge.mqtt_client import (
    MQTTListener,
    ParsedEdgePacket,
    TelemetryPacketParser,
)
from solardoctor.edge.manager import EdgeManager, get_edge_manager

__all__ = [
    "ModbusTCPClient",
    "InverterTelemetry",
    "StringTelemetryStatus",
    "SunSpecDecoder",
    "SungrowDecoder",
    "HuaweiDecoder",
    "SmaDecoder",
    "SUPPORTED_PROFILES",
    "unpack_uint16",
    "unpack_int16",
    "unpack_uint32",
    "unpack_int32",
    "unpack_float32",
    "unpack_string",
    "apply_scale_factor",
    "MQTTListener",
    "ParsedEdgePacket",
    "TelemetryPacketParser",
    "EdgeManager",
    "get_edge_manager",
]
