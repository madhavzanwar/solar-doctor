"""Edge Telemetry router: Modbus polling, industrial MQTT ingest, and string status.

Provides:
- GET /api/v1/edge/profiles: Supported inverter register maps (SunSpec, Sungrow, Huawei, SMA).
- POST /api/v1/edge/poll: Trigger on-demand Modbus poll for a plant/inverter.
- POST /api/v1/edge/simulate-packet: Ingest high-frequency synthetic edge packet for testing & demos.
- GET /api/v1/edge/status: Ingestion status, metrics, and active devices.
- GET /api/v1/edge/{plant_id}/strings: String-level health records for GIS drone mapping.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from solardoctor.edge.manager import get_edge_manager
from solardoctor.edge.modbus_client import SUPPORTED_PROFILES, StringTelemetryStatus
from solardoctor.physics import scada_service
from solardoctor.physics.deps import get_db

router = APIRouter(prefix="/edge", tags=["Edge & IoT Telemetry"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class EdgePollRequest(BaseModel):
    plant_id: int
    inverter_id: Optional[str] = "INV-01"
    host: Optional[str] = "127.0.0.1"
    port: Optional[int] = 502
    unit_id: Optional[int] = 1
    profile: Optional[str] = "sunspec"
    simulate: Optional[bool] = False
    anomaly_pattern: Optional[str] = "normal"
    irradiance_w_m2: Optional[float] = None
    ambient_temp_c: Optional[float] = 28.0


class EdgePollResponse(BaseModel):
    success: bool
    plant_id: int
    inverter_id: str
    timestamp: str
    telemetry: Dict[str, Any]
    string_statuses: List[StringTelemetryStatus]


class SimulatePacketRequest(BaseModel):
    plant_id: int
    inverter_id: Optional[str] = "INV-01"
    string_id: Optional[str] = None
    gateway_format: Optional[str] = "generic"  # "generic" | "advantech" | "teltonika"
    power_kw: Optional[float] = None
    voltage_v: Optional[float] = None
    current_a: Optional[float] = None
    irradiance_w_m2: Optional[float] = 850.0
    temperature_c: Optional[float] = 30.0
    wind_speed_m_s: Optional[float] = 2.5
    anomaly_pattern: Optional[str] = "normal"  # "normal" | "derated" | "blown_fuse" | "soiling"
    custom_payload: Optional[Dict[str, Any]] = None


class SimulatePacketResponse(BaseModel):
    success: bool
    reading_id: int
    plant_id: int
    inverter_id: str
    timestamp: str
    telemetry: Dict[str, Any]
    string_statuses: List[StringTelemetryStatus]


class EdgeStatusResponse(BaseModel):
    status: str
    mqtt: Dict[str, Any]
    metrics: Dict[str, Any]
    supported_inverter_profiles: List[str]


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/profiles", summary="List supported inverter Modbus profiles & register maps")
def get_profiles() -> Dict[str, Any]:
    """Return supported OEM and open inverter register profiles."""
    return {
        "profiles": SUPPORTED_PROFILES,
        "count": len(SUPPORTED_PROFILES),
    }


@router.post("/poll", response_model=EdgePollResponse, summary="Trigger on-demand Modbus poll")
def poll_device(req: EdgePollRequest, db: Session = Depends(get_db)):
    """Trigger Modbus poll across SunSpec, Sungrow, Huawei, or SMA profile."""
    # Verify plant exists
    scada_service.assert_plant_exists(db, req.plant_id)

    manager = get_edge_manager()
    try:
        inv_telemetry, string_statuses = manager.poll_modbus_device(
            plant_id=req.plant_id,
            inverter_id=req.inverter_id or "INV-01",
            host=req.host or "127.0.0.1",
            port=req.port or 502,
            unit_id=req.unit_id or 1,
            profile=req.profile or "sunspec",
            simulate=bool(req.simulate),
            anomaly_pattern=req.anomaly_pattern or "normal",
            irradiance_w_m2=req.irradiance_w_m2,
            ambient_temp_c=req.ambient_temp_c or 28.0,
            db=db,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Modbus poll failed: {exc}",
        )

    return EdgePollResponse(
        success=True,
        plant_id=req.plant_id,
        inverter_id=inv_telemetry.inverter_id,
        timestamp=inv_telemetry.timestamp.isoformat(),
        telemetry=inv_telemetry.model_dump(),
        string_statuses=string_statuses,
    )


@router.post("/simulate-packet", response_model=SimulatePacketResponse, summary="Ingest synthetic edge packet")
def simulate_edge_packet(req: SimulatePacketRequest, db: Session = Depends(get_db)):
    """Simulate arrival of an industrial edge packet (Advantech, Teltonika, or Generic)."""
    # Verify plant exists
    scada_service.assert_plant_exists(db, req.plant_id)

    manager = get_edge_manager()
    inv_id = req.inverter_id or "INV-01"
    now_ts = datetime.now(tz=timezone.utc).isoformat()

    # Determine topic
    if req.string_id:
        topic = f"solardoctor/edge/{req.plant_id}/string/{req.string_id}/telemetry"
    else:
        topic = f"solardoctor/edge/{req.plant_id}/inverter/{inv_id}/telemetry"

    # Construct format-specific payload if not provided
    if req.custom_payload:
        payload = req.custom_payload
    else:
        # Default power calculation
        nominal_kw = round((req.irradiance_w_m2 or 800.0) / 10.0, 2)
        power_kw = req.power_kw if req.power_kw is not None else nominal_kw
        voltage = req.voltage_v or 700.0
        current = req.current_a or (round((power_kw * 1000.0) / voltage, 2) if voltage > 0 else 0.0)

        # Apply anomaly pattern if requested
        if req.anomaly_pattern == "derated":
            power_kw = round(power_kw * 0.65, 2)
            current = round(current * 0.65, 2)
        elif req.anomaly_pattern == "blown_fuse":
            power_kw = 0.0
            current = 0.0
        elif req.anomaly_pattern == "soiling":
            power_kw = round(power_kw * 0.82, 2)
            current = round(current * 0.82, 2)

        fmt = (req.gateway_format or "generic").lower()
        if fmt == "advantech":
            payload = {
                "sStatus": 1,
                "d": {
                    "power_kw": power_kw,
                    "voltage": voltage,
                    "current": current,
                    "irradiance": req.irradiance_w_m2,
                    "temp": req.temperature_c,
                    "wind": req.wind_speed_m_s,
                },
                "ts": now_ts,
                "inverter_id": inv_id,
                "string_id": req.string_id,
            }
        elif fmt == "teltonika":
            payload = {
                "ts": int(datetime.now(tz=timezone.utc).timestamp()),
                "data": {
                    "ActivePower": power_kw,
                    "DcVoltage": voltage,
                    "GridCurrent": current,
                    "Irradiance": req.irradiance_w_m2,
                    "InternalTemp": req.temperature_c,
                    "DailyYield": round(power_kw * 4.2, 1),
                },
                "inverter_id": inv_id,
                "string_id": req.string_id,
            }
        else:  # generic
            payload = {
                "plant_id": req.plant_id,
                "inverter_id": inv_id,
                "string_id": req.string_id,
                "power_kw": power_kw,
                "voltage_v": voltage,
                "current_a": current,
                "irradiance_w_m2": req.irradiance_w_m2,
                "temperature_c": req.temperature_c,
                "wind_speed_m_s": req.wind_speed_m_s,
                "daily_yield_kwh": round(power_kw * 4.2, 1),
                "timestamp": now_ts,
            }

    try:
        telemetry_row, string_statuses = manager.ingest_edge_packet(
            topic=topic,
            payload=payload,
            db=db,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to ingest edge packet: {exc}",
        )

    return SimulatePacketResponse(
        success=True,
        reading_id=telemetry_row.id,
        plant_id=telemetry_row.plant_id,
        inverter_id=inv_id,
        timestamp=telemetry_row.ts.isoformat(),
        telemetry={
            "id": telemetry_row.id,
            "plant_id": telemetry_row.plant_id,
            "power_kw": telemetry_row.p_ac_kw,
            "irradiance_w_m2": telemetry_row.ghi_wm2,
            "temperature_c": telemetry_row.t_amb,
            "source": telemetry_row.source,
        },
        string_statuses=string_statuses,
    )


@router.get("/status", response_model=EdgeStatusResponse, summary="Get edge telemetry ingestion status")
def get_edge_status():
    """Return health metrics and connection state of the edge subsystem."""
    manager = get_edge_manager()
    return manager.get_status_summary()


@router.get("/{plant_id}/strings", response_model=List[StringTelemetryStatus], summary="Get string health records")
def get_plant_string_statuses(
    plant_id: int,
    inverter_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
):
    """Return live string telemetry statuses for GIS drone orthomosaic rendering."""
    scada_service.assert_plant_exists(db, plant_id)
    manager = get_edge_manager()
    statuses = manager.get_string_statuses(plant_id, inverter_id=inverter_id)
    if not statuses:
        # If no active cache exists yet, generate initial nominal statuses for 8 strings
        statuses = manager.poll_modbus_device(
            plant_id=plant_id,
            inverter_id=inverter_id or "INV-01",
            simulate=True,
            db=db,
        )[1]
    return statuses
