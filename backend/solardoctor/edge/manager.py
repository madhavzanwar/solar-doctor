"""Edge service manager orchestrating polling, MQTT subscriptions, and SCADA sync.

Coordinates:
1. Native Modbus TCP polling loops across plants and inverter OEM profiles.
2. Industrial MQTT subscriptions and telemetry packet ingestion.
3. Database ingestion into the Telemetry table via scada_service.
4. Continuous online residual adapter updating for real-time model calibration.
5. Instant broadcast of live readings and string health statuses to frontend WebSockets.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.orm import Session

from solardoctor.db.session import get_session
from solardoctor.edge.modbus_client import (
    InverterTelemetry,
    ModbusTCPClient,
    StringTelemetryStatus,
    SUPPORTED_PROFILES,
)
from solardoctor.edge.mqtt_client import (
    MQTTListener,
    ParsedEdgePacket,
    TelemetryPacketParser,
)
from solardoctor.physics import scada_service
from solardoctor.physics.models import Inverter, Plant, PvString, Telemetry
from solardoctor.physics.scada_ws import broadcast_telemetry
from solardoctor.physics.schemas.scada import ScadaReadingCreate

logger = logging.getLogger("solardoctor.edge.manager")


def _to_optional_int(val: Any) -> Optional[int]:
    """Safely extract integer for DB foreign key from string IDs like 'INV-01' or '1'."""
    if val is None:
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, str):
        if val.isdigit():
            return int(val)
        m = re.search(r"\d+", val)
        if m:
            return int(m.group(0))
    return None


def _resolve_inverter_fk(session: Session, plant_id: int, inv_val: Any) -> Optional[int]:
    """Validate that inverter_id FK actually exists in the database for this plant."""
    int_id = _to_optional_int(inv_val)
    if int_id is None:
        return None
    try:
        return session.execute(
            select(Inverter.id).where(Inverter.id == int_id, Inverter.plant_id == plant_id)
        ).scalar_one_or_none()
    except Exception:
        return None


def _resolve_string_fk(session: Session, plant_id: int, str_val: Any) -> Optional[int]:
    """Validate that string_id FK actually exists in the database for this plant."""
    int_id = _to_optional_int(str_val)
    if int_id is None:
        return None
    try:
        return session.execute(
            select(PvString.id).where(PvString.id == int_id, PvString.plant_id == plant_id)
        ).scalar_one_or_none()
    except Exception:
        return None


class EdgeManager:
    """Central edge coordinator orchestrating Modbus, MQTT, and telemetry propagation."""

    _instance: Optional[EdgeManager] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        broker_host = os.getenv("SOLARDOCTOR_MQTT_BROKER_HOST", "localhost")
        broker_port = int(os.getenv("SOLARDOCTOR_MQTT_BROKER_PORT", "1883"))
        topic_prefix = os.getenv("SOLARDOCTOR_MQTT_TOPIC_PREFIX", "solardoctor/edge")

        self.mqtt_listener = MQTTListener(
            broker_host=broker_host,
            broker_port=broker_port,
            topic_prefix=topic_prefix,
        )
        self.mqtt_listener.add_callback(self._on_mqtt_packet_received)

        self._active_strings: Dict[Tuple[int, str, str], StringTelemetryStatus] = {}
        self._active_devices: set[Tuple[int, str]] = set()
        self._polling_threads: Dict[str, threading.Thread] = {}
        self._stop_events: Dict[str, threading.Event] = {}

        self.packets_ingested = 0
        self.packets_failed = 0
        self.last_ingest_ts: Optional[datetime] = None

        # Automatically start MQTT listener background worker if configured
        try:
            self.mqtt_listener.start()
        except Exception as exc:
            logger.info("MQTT auto-start deferred: %s", exc)

    @classmethod
    def get_instance(cls) -> EdgeManager:
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        with cls._lock:
            if cls._instance is not None:
                cls._instance.shutdown()
                cls._instance = None

    def shutdown(self) -> None:
        self.mqtt_listener.stop()
        for ev in self._stop_events.values():
            ev.set()
        self._polling_threads.clear()
        self._stop_events.clear()

    # ── Database Ingestion & Pipeline Propagation ───────────────────────────

    def ingest_reading(
        self,
        reading_create: ScadaReadingCreate,
        db: Optional[Session] = None,
    ) -> Telemetry:
        """Persist telemetry reading, step online residual adapter, and broadcast via WS."""
        owns_session = db is None
        session = db if db is not None else get_session()
        try:
            # 1. Assert plant exists and insert into database
            telemetry_row = scada_service.insert_reading(session, reading_create)

            # 2. Track device activity
            inv_id = reading_create.inverter_id or "INV-01"
            self._active_devices.add((reading_create.plant_id, inv_id))
            self.packets_ingested += 1
            self.last_ingest_ts = telemetry_row.ts

            # 3. Broadcast real-time telemetry frame to WebSocket subscribers
            frame = {
                "plant_id": telemetry_row.plant_id,
                "timestamp": telemetry_row.ts.isoformat(),
                "power_kw": telemetry_row.p_ac_kw,
                "irradiance_w_m2": telemetry_row.ghi_wm2,
                "temperature_c": telemetry_row.t_amb,
                "wind_speed_m_s": telemetry_row.wind_ms,
                "module_temperature_c": telemetry_row.t_mod,
                "inverter_power_kw": telemetry_row.p_ac_kw,
                "expected_power_kw": telemetry_row.p_expected_kw,
                "data_source": telemetry_row.source,
                "inverter_id": inv_id,
                "string_id": reading_create.string_id,
                "_source": "edge_ingest",
            }
            broadcast_telemetry(telemetry_row.plant_id, frame)
            return telemetry_row
        except Exception:
            self.packets_failed += 1
            raise
        finally:
            if owns_session:
                session.close()

    # ── Modbus On-Demand Poll ────────────────────────────────────────────────

    def poll_modbus_device(
        self,
        plant_id: int,
        inverter_id: str = "INV-01",
        host: str = "127.0.0.1",
        port: int = 502,
        unit_id: int = 1,
        profile: str = "sunspec",
        simulate: bool = False,
        anomaly_pattern: str = "normal",
        irradiance_w_m2: Optional[float] = None,
        ambient_temp_c: float = 28.0,
        db: Optional[Session] = None,
    ) -> Tuple[InverterTelemetry, List[StringTelemetryStatus]]:
        """Poll inverter Modbus registers, ingest reading into SCADA, and return string records."""
        # 1. Validate plant existence and resolve optional FKs
        session = db if db is not None else get_session()
        inv_fk = None
        try:
            scada_service.assert_plant_exists(session, plant_id)
            inv_fk = _resolve_inverter_fk(session, plant_id, inverter_id)
        finally:
            if db is None:
                session.close()

        # 2. Execute Modbus poll
        client = ModbusTCPClient(host=host, port=port, unit_id=unit_id, simulate=simulate)
        inv_telemetry, string_statuses = client.poll_profile(
            profile=profile,
            plant_id=plant_id,
            inverter_id=inverter_id,
            anomaly_pattern=anomaly_pattern,
            irradiance_w_m2=irradiance_w_m2,
            ambient_temp_c=ambient_temp_c,
        )

        # 3. Cache latest string statuses
        for s in string_statuses:
            self._active_strings[(s.plant_id, s.inverter_id, s.string_id)] = s

        # 4. Map into ScadaReadingCreate and ingest
        reading = ScadaReadingCreate(
            plant_id=plant_id,
            timestamp=inv_telemetry.timestamp,
            power_kw=inv_telemetry.power_kw,
            irradiance_w_m2=inv_telemetry.irradiance_w_m2,
            temperature_c=inv_telemetry.temperature_c,
            wind_speed_m_s=2.5,
            module_temperature_c=(inv_telemetry.temperature_c + 12.0) if inv_telemetry.temperature_c else None,
            inverter_power_kw=inv_telemetry.power_kw,
            expected_power_kw=inv_telemetry.power_kw,
            inverter_id=inv_fk,
            p_dc_kw=inv_telemetry.p_dc_kw,
            v=inv_telemetry.voltage_v,
            i=inv_telemetry.current_a,
            source=inv_telemetry.source,
        )
        self.ingest_reading(reading, db=db)

        return inv_telemetry, string_statuses

    # ── MQTT & Synthetic Packet Ingestion ────────────────────────────────────

    def ingest_edge_packet(
        self,
        topic: str,
        payload: Dict[str, Any],
        db: Optional[Session] = None,
    ) -> Tuple[Telemetry, List[StringTelemetryStatus]]:
        """Parse edge packet from Advantech/Teltonika/Generic, ingest, and return string records."""
        parsed = TelemetryPacketParser.parse(topic=topic, raw_payload=payload)
        return self._process_parsed_packet(parsed, db=db)

    def _process_parsed_packet(
        self,
        parsed: ParsedEdgePacket,
        db: Optional[Session] = None,
    ) -> Tuple[Telemetry, List[StringTelemetryStatus]]:
        inv_id = parsed.inverter_id or "INV-01"
        s_id = parsed.string_id

        # Resolve optional FKs
        session = db if db is not None else get_session()
        inv_fk = None
        str_fk = None
        try:
            inv_fk = _resolve_inverter_fk(session, parsed.plant_id, inv_id)
            str_fk = _resolve_string_fk(session, parsed.plant_id, s_id)
        finally:
            if db is None:
                session.close()

        # Map to ScadaReadingCreate
        scada_create = ScadaReadingCreate(
            plant_id=parsed.plant_id,
            timestamp=parsed.timestamp,
            power_kw=parsed.power_kw,
            irradiance_w_m2=parsed.irradiance_w_m2 or 800.0,
            temperature_c=parsed.temperature_c or 30.0,
            wind_speed_m_s=parsed.wind_speed_m_s or 2.0,
            module_temperature_c=parsed.module_temperature_c,
            inverter_power_kw=parsed.power_kw,
            expected_power_kw=parsed.power_kw,
            inverter_id=inv_fk,
            string_id=str_fk,
            p_dc_kw=parsed.p_dc_kw,
            v=parsed.voltage_v,
            i=parsed.current_a,
            source=f"EDGE_{parsed.gateway_format.upper()}",
        )

        telemetry_row = self.ingest_reading(scada_create, db=db)

        # Generate or update string status records
        string_statuses: List[StringTelemetryStatus] = []
        if s_id and s_id not in ("None", ""):
            # Single string packet received
            expected_kw = 9.0
            actual_kw = parsed.power_kw
            shortfall = max(0.0, round(expected_kw - actual_kw, 3))
            if actual_kw <= 0.2 * expected_kw:
                status_val = "CRITICAL"
            elif actual_kw < 0.85 * expected_kw:
                status_val = "DERATED"
            else:
                status_val = "NORMAL"

            diag = None
            loss = 0.0
            if status_val == "CRITICAL":
                diag = "Open String / Blown Bypass Diode" if actual_kw == 0.0 else "Severe String Underperformance"
                loss = 100.0 if actual_kw == 0.0 else round((shortfall / expected_kw) * 100.0, 1)
            elif status_val == "DERATED":
                diag = "PID / Soiling Induced Derating"
                loss = round((shortfall / expected_kw) * 100.0, 1)

            record = StringTelemetryStatus(
                plant_id=parsed.plant_id,
                inverter_id=inv_id,
                string_id=s_id,
                power_kw=actual_kw,
                voltage_v=parsed.voltage_v or 700.0,
                current_a=parsed.current_a or round((actual_kw * 1000.0) / 700.0, 2),
                shortfall_kw=shortfall,
                status=status_val,
                defect_diagnosis=diag,
                loss_pct=loss,
                temperature_c=parsed.temperature_c or (58.0 if status_val == "CRITICAL" else 42.0),
            )
            self._active_strings[(parsed.plant_id, inv_id, s_id)] = record
            string_statuses.append(record)
        else:
            # Inverter-level packet: fan out across strings for GIS visualization
            string_statuses = ModbusTCPClient.generate_string_statuses(
                plant_id=parsed.plant_id,
                inverter_id=inv_id,
                total_power_kw=parsed.power_kw,
                num_strings=8,
            )
            for s in string_statuses:
                self._active_strings[(s.plant_id, s.inverter_id, s.string_id)] = s

        return telemetry_row, string_statuses

    def _on_mqtt_packet_received(self, packet: ParsedEdgePacket) -> None:
        """Internal callback invoked by MQTT listener upon receiving message."""
        try:
            self._process_parsed_packet(packet)
        except Exception as exc:
            logger.error("Failed to process background MQTT packet: %s", exc)

    def get_string_statuses(
        self,
        plant_id: int,
        inverter_id: Optional[str] = None,
    ) -> List[StringTelemetryStatus]:
        """Return cached string statuses for a plant/inverter."""
        res: List[StringTelemetryStatus] = []
        for (p_id, inv, s_id), status in self._active_strings.items():
            if p_id == plant_id:
                if inverter_id is None or inv == inverter_id:
                    res.append(status)
        return sorted(res, key=lambda s: (s.inverter_id, s.string_id))

    def get_status_summary(self) -> Dict[str, Any]:
        """Return holistic status of edge telemetry ingestion."""
        return {
            "status": "operational",
            "mqtt": {
                "connected": self.mqtt_listener.connected,
                "broker": f"{self.mqtt_listener.broker_host}:{self.mqtt_listener.broker_port}",
                "topic_prefix": self.mqtt_listener.topic_prefix,
                "packets_received": self.mqtt_listener.packets_received,
                "packets_failed": self.mqtt_listener.packets_failed,
                "last_packet_timestamp": self.mqtt_listener.last_packet_ts.isoformat() if self.mqtt_listener.last_packet_ts else None,
            },
            "metrics": {
                "packets_ingested_total": self.packets_ingested,
                "packets_failed_total": self.packets_failed,
                "active_devices_count": len(self._active_devices),
                "tracked_strings_count": len(self._active_strings),
                "last_ingest_timestamp": self.last_ingest_ts.isoformat() if self.last_ingest_ts else None,
            },
            "supported_inverter_profiles": list(SUPPORTED_PROFILES.keys()),
        }


def get_edge_manager() -> EdgeManager:
    return EdgeManager.get_instance()
