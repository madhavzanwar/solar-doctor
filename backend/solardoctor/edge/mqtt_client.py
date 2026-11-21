"""Industrial MQTT listener and edge gateway telemetry parser.

Subscribes to standard edge gateway topics:
- solardoctor/edge/{plant_id}/inverter/{inverter_id}/telemetry
- solardoctor/edge/{plant_id}/string/{string_id}/telemetry

Supports decoding from:
- Advantech IoT gateways (WISE-4000, ECU-1000 series)
- Teltonika IoT gateways (RUT955, TRB140/245 series)
- Raspberry Pi / Generic IoT gateway JSON formats
- Native offline packet ingestion and testing capability
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Union

from pydantic import BaseModel, Field

logger = logging.getLogger("solardoctor.edge.mqtt")

# Topic Patterns
TOPIC_INVERTER_REGEX = re.compile(
    r"^solardoctor/edge/(?P<plant_id>\d+)/inverter/(?P<inverter_id>[^/]+)/telemetry$"
)
TOPIC_STRING_REGEX = re.compile(
    r"^solardoctor/edge/(?P<plant_id>\d+)/string/(?P<string_id>[^/]+)/telemetry$"
)
TOPIC_GENERAL_REGEX = re.compile(
    r"^solardoctor/edge/(?P<plant_id>\d+)/(?P<device_type>inverter|string)/(?P<device_id>[^/]+)/telemetry$"
)


class ParsedEdgePacket(BaseModel):
    """Normalized edge telemetry packet."""
    plant_id: int
    inverter_id: Optional[str] = None
    string_id: Optional[str] = None
    timestamp: datetime
    power_kw: float
    p_dc_kw: Optional[float] = None
    voltage_v: Optional[float] = None
    current_a: Optional[float] = None
    irradiance_w_m2: Optional[float] = None
    temperature_c: Optional[float] = None
    module_temperature_c: Optional[float] = None
    wind_speed_m_s: Optional[float] = None
    daily_yield_kwh: Optional[float] = None
    frequency_hz: Optional[float] = None
    gateway_format: str = "generic"
    topic: str
    raw_payload: Dict[str, Any] = Field(default_factory=dict)


class TelemetryPacketParser:
    """Parser capable of decoding Advantech, Teltonika, and Generic IoT payloads."""

    @classmethod
    def parse(cls, topic: str, raw_payload: Union[str, bytes, Dict[str, Any]]) -> ParsedEdgePacket:
        # 1. Topic metadata extraction
        plant_id = 1
        inverter_id: Optional[str] = None
        string_id: Optional[str] = None

        m_inv = TOPIC_INVERTER_REGEX.match(topic)
        if m_inv:
            plant_id = int(m_inv.group("plant_id"))
            inverter_id = m_inv.group("inverter_id")
        else:
            m_str = TOPIC_STRING_REGEX.match(topic)
            if m_str:
                plant_id = int(m_str.group("plant_id"))
                string_id = m_str.group("string_id")
            else:
                m_gen = TOPIC_GENERAL_REGEX.match(topic)
                if m_gen:
                    plant_id = int(m_gen.group("plant_id"))
                    dev_type = m_gen.group("device_type")
                    if dev_type == "inverter":
                        inverter_id = m_gen.group("device_id")
                    else:
                        string_id = m_gen.group("device_id")

        # 2. Parse payload dictionary
        if isinstance(raw_payload, (str, bytes)):
            try:
                data = json.loads(raw_payload)
            except Exception as e:
                raise ValueError(f"Failed to decode JSON payload: {e}") from e
        elif isinstance(raw_payload, dict):
            data = raw_payload
        else:
            raise TypeError(f"Unsupported payload type {type(raw_payload)}")

        # Override plant/device if explicitly supplied in JSON
        if "plant_id" in data:
            try:
                plant_id = int(data["plant_id"])
            except Exception:
                pass
        if "inverter_id" in data and data["inverter_id"] is not None and not inverter_id:
            inv_str = str(data["inverter_id"]).strip()
            if inv_str and inv_str.lower() != "none":
                inverter_id = inv_str
        if "string_id" in data and data["string_id"] is not None and not string_id:
            str_val = str(data["string_id"]).strip()
            if str_val and str_val.lower() != "none":
                string_id = str_val

        # Timestamp parsing
        ts = cls._extract_timestamp(data)

        # Detect gateway format and extract measurements
        gateway_format = "generic"
        if "d" in data and isinstance(data["d"], dict):
            # Advantech WISE-4000 / ECU format: {"d": {...}, "ts": ...}
            gateway_format = "advantech"
            meas = data["d"]
            power_kw = cls._get_float(meas, ["power_kw", "power", "p_ac_kw", "ActivePower", "P", "PWR"], 0.0)
            p_dc_kw = cls._get_float(meas, ["p_dc_kw", "dc_power", "DcPower", "P_DC"], None)
            voltage_v = cls._get_float(meas, ["voltage", "voltage_v", "V", "DcVoltage", "VOLT"], None)
            current_a = cls._get_float(meas, ["current", "current_a", "I", "GridCurrent", "CURR"], None)
            irr = cls._get_float(meas, ["irradiance", "irradiance_w_m2", "ghi", "GHI", "IRR"], None)
            temp = cls._get_float(meas, ["temp", "temperature_c", "t_amb", "TEMP", "InternalTemp"], None)
            mod_temp = cls._get_float(meas, ["mod_temp", "module_temp", "t_mod", "MOD_TEMP"], None)
            wind = cls._get_float(meas, ["wind", "wind_speed", "wind_ms", "WIND"], None)
            yield_kwh = cls._get_float(meas, ["daily_yield", "daily_yield_kwh", "DailyYield", "YIELD"], None)
        elif "data" in data and isinstance(data["data"], dict):
            # Teltonika Modbus-MQTT gateway with nested data dict
            gateway_format = "teltonika"
            meas = data["data"]
            power_kw = cls._get_float(meas, ["ActivePower", "power_kw", "power", "p_ac_kw"], 0.0)
            p_dc_kw = cls._get_float(meas, ["DcPower", "p_dc_kw", "dc_power"], None)
            voltage_v = cls._get_float(meas, ["DcVoltage", "voltage_v", "voltage"], None)
            current_a = cls._get_float(meas, ["GridCurrent", "current_a", "current"], None)
            irr = cls._get_float(meas, ["Irradiance", "irradiance_w_m2", "ghi"], None)
            temp = cls._get_float(meas, ["InternalTemp", "temperature_c", "t_amb"], None)
            mod_temp = cls._get_float(meas, ["ModuleTemp", "module_temperature_c"], None)
            wind = cls._get_float(meas, ["WindSpeed", "wind_speed_m_s"], None)
            yield_kwh = cls._get_float(meas, ["DailyYield", "daily_yield_kwh"], None)
        elif any(k in data for k in ["ActivePower", "DcVoltage", "InternalTemp", "DailyYield"]):
            # Teltonika flat payload
            gateway_format = "teltonika"
            power_kw = cls._get_float(data, ["ActivePower", "power_kw", "power"], 0.0)
            p_dc_kw = cls._get_float(data, ["DcPower", "p_dc_kw"], None)
            voltage_v = cls._get_float(data, ["DcVoltage", "voltage_v", "voltage"], None)
            current_a = cls._get_float(data, ["GridCurrent", "current_a", "current"], None)
            irr = cls._get_float(data, ["Irradiance", "irradiance_w_m2", "ghi"], None)
            temp = cls._get_float(data, ["InternalTemp", "temperature_c", "t_amb"], None)
            mod_temp = cls._get_float(data, ["ModuleTemp", "module_temperature_c"], None)
            wind = cls._get_float(data, ["WindSpeed", "wind_speed_m_s"], None)
            yield_kwh = cls._get_float(data, ["DailyYield", "daily_yield_kwh"], None)
        else:
            # Generic IoT JSON
            gateway_format = "generic"
            power_kw = cls._get_float(data, ["power_kw", "power", "p_ac_kw", "inverter_power_kw"], 0.0)
            p_dc_kw = cls._get_float(data, ["p_dc_kw", "dc_power_kw", "dc_power"], None)
            voltage_v = cls._get_float(data, ["voltage_v", "voltage", "v"], None)
            current_a = cls._get_float(data, ["current_a", "current", "i"], None)
            irr = cls._get_float(data, ["irradiance_w_m2", "irradiance", "ghi_wm2", "ghi"], None)
            temp = cls._get_float(data, ["temperature_c", "t_amb", "temperature"], None)
            mod_temp = cls._get_float(data, ["module_temperature_c", "t_mod", "module_temp"], None)
            wind = cls._get_float(data, ["wind_speed_m_s", "wind_ms", "wind_speed"], None)
            yield_kwh = cls._get_float(data, ["daily_yield_kwh", "daily_yield", "yield_kwh"], None)

        # If current and voltage exist but power_kw is 0 (typical for string sensors)
        if power_kw == 0.0 and voltage_v is not None and current_a is not None and voltage_v > 0 and current_a > 0:
            power_kw = round((voltage_v * current_a) / 1000.0, 3)

        return ParsedEdgePacket(
            plant_id=plant_id,
            inverter_id=inverter_id or ("INV-01" if not string_id else None),
            string_id=string_id,
            timestamp=ts,
            power_kw=max(0.0, round(power_kw, 3)),
            p_dc_kw=round(p_dc_kw, 3) if p_dc_kw is not None else None,
            voltage_v=round(voltage_v, 2) if voltage_v is not None else None,
            current_a=round(current_a, 2) if current_a is not None else None,
            irradiance_w_m2=round(irr, 1) if irr is not None else None,
            temperature_c=round(temp, 1) if temp is not None else None,
            module_temperature_c=round(mod_temp, 1) if mod_temp is not None else None,
            wind_speed_m_s=round(wind, 2) if wind is not None else None,
            daily_yield_kwh=round(yield_kwh, 2) if yield_kwh is not None else None,
            gateway_format=gateway_format,
            topic=topic,
            raw_payload=data,
        )

    @staticmethod
    def _extract_timestamp(data: Dict[str, Any]) -> datetime:
        for key in ["timestamp", "ts", "time", "date"]:
            if key in data:
                val = data[key]
                if isinstance(val, (int, float)):
                    # Unix epoch (seconds or milliseconds)
                    if val > 1e11:
                        val = val / 1000.0
                    return datetime.fromtimestamp(val, tz=timezone.utc)
                if isinstance(val, str):
                    try:
                        return datetime.fromisoformat(val.replace("Z", "+00:00"))
                    except Exception:
                        pass
        return datetime.now(tz=timezone.utc)

    @staticmethod
    def _get_float(data: Dict[str, Any], keys: List[str], default: Optional[float]) -> Optional[float]:
        for k in keys:
            if k in data and data[k] is not None:
                try:
                    return float(data[k])
                except (ValueError, TypeError):
                    pass
        return default


class MQTTListener:
    """Enterprise industrial MQTT listener with offline packet ingestion & testing."""

    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        topic_prefix: str = "solardoctor/edge",
        client_id: str = "solardoctor-edge-daemon",
    ):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.topic_prefix = topic_prefix.rstrip("/")
        self.client_id = client_id

        self.connected = False
        self.packets_received = 0
        self.packets_failed = 0
        self.last_packet_ts: Optional[datetime] = None

        self._callbacks: List[Callable[[ParsedEdgePacket], None]] = []
        self._packet_history: List[ParsedEdgePacket] = []
        self._paho_client = None

    def add_callback(self, callback: Callable[[ParsedEdgePacket], None]) -> None:
        self._callbacks.append(callback)

    def start(self) -> bool:
        """Start listener. Connects to broker if paho is installed, or stays in offline mode."""
        try:
            import paho.mqtt.client as mqtt  # type: ignore

            self._paho_client = mqtt.Client(client_id=self.client_id)
            self._paho_client.on_connect = self._on_paho_connect
            self._paho_client.on_message = self._on_paho_message
            self._paho_client.connect_async(self.broker_host, self.broker_port, 60)
            self._paho_client.loop_start()
            self.connected = True
            logger.info("MQTT listener started on %s:%s", self.broker_host, self.broker_port)
            return True
        except ImportError:
            logger.info("paho-mqtt not installed; running MQTT listener in offline ingestion mode.")
            self.connected = False
            return False
        except Exception as exc:
            logger.warning("Could not connect to MQTT broker %s:%s: %s (offline mode active)", self.broker_host, self.broker_port, exc)
            self.connected = False
            return False

    def stop(self) -> None:
        if self._paho_client is not None:
            try:
                self._paho_client.loop_stop()
                self._paho_client.disconnect()
            except Exception:
                pass
            self._paho_client = None
        self.connected = False

    def _on_paho_connect(self, client: Any, userdata: Any, flags: Any, rc: int) -> None:
        if rc == 0:
            self.connected = True
            # Subscribe to all edge telemetry topics
            topic = f"{self.topic_prefix}/#"
            client.subscribe(topic)
            logger.info("Subscribed to %s", topic)
        else:
            self.connected = False
            logger.warning("MQTT connection refused with code %s", rc)

    def _on_paho_message(self, client: Any, userdata: Any, msg: Any) -> None:
        try:
            self.ingest_packet(msg.topic, msg.payload)
        except Exception as exc:
            self.packets_failed += 1
            logger.error("Error processing MQTT message on %s: %s", msg.topic, exc)

    def ingest_packet(
        self,
        topic: str,
        payload: Union[str, bytes, Dict[str, Any]],
    ) -> ParsedEdgePacket:
        """Ingest and dispatch a packet (works synchronously offline and online)."""
        try:
            parsed = TelemetryPacketParser.parse(topic=topic, raw_payload=payload)
            self.packets_received += 1
            self.last_packet_ts = parsed.timestamp

            # Keep last 100 packets in history
            self._packet_history.append(parsed)
            if len(self._packet_history) > 100:
                self._packet_history.pop(0)

            # Dispatch to subscribers
            for cb in self._callbacks:
                try:
                    cb(parsed)
                except Exception as exc:
                    logger.warning("Error in packet callback: %s", exc)

            return parsed
        except Exception:
            self.packets_failed += 1
            raise

    def get_history(self, limit: int = 50) -> List[ParsedEdgePacket]:
        return list(self._packet_history[-limit:])
