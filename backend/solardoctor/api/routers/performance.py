"""Physics deficit engine API: plant performance (expected vs actual), scans, PI thresholds, string peers.

Reads viewer+, writes operator+ (router policy in api/app.py). Tracker plants get the shared 422
``baseline_unsupported_for_trackers``. See docs/solardoctor/interfaces/physics-deficit.md.
"""
from __future__ import annotations

import math
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from solardoctor.physics import deficit, irradiance, soiling_analytics
from solardoctor.physics import weather_service as ws
from solardoctor.physics.baseline import Baseline
from solardoctor.physics.deps import get_db
from solardoctor.physics.models import Plant, PlantAlert, PvString
from solardoctor.physics.schemas.alert import AlertResponse
from solardoctor.physics.schemas.performance import (
    DeficitEventOut, HourlyPoint, PeersResponse, PeerValue, PerformanceResponse, ScanResponse,
    ThresholdsRequest, ThresholdsResponse,
)
from solardoctor.physics.tracker import require_fixed_tilt_baseline

router = APIRouter(tags=["Performance"])

DEFAULT_WINDOW = timedelta(days=7)
MAX_WINDOW = timedelta(days=92)


def _providers() -> dict:  # looked up per call so tests can patch the network functions
    return {"nasa_fetch": ws.fetch_nasa_power_hourly, "openmeteo_fetch": irradiance.fetch_openmeteo_hourly}


def _plant(db: Session, plant_id: int) -> Plant:
    plant = db.get(Plant, plant_id)
    if plant is None:
        raise HTTPException(404, f"Plant {plant_id} not found")
    require_fixed_tilt_baseline(plant)
    return plant


def _window(start: Optional[datetime], end: Optional[datetime]) -> tuple[datetime, datetime]:
    def utc(d: datetime) -> datetime:
        return d.replace(tzinfo=timezone.utc) if d.tzinfo is None else d.astimezone(timezone.utc)
    end = utc(end) if end else datetime.now(timezone.utc)
    start = utc(start) if start else end - DEFAULT_WINDOW
    if start >= end:
        raise HTTPException(422, "start must be before end")
    if end - start > MAX_WINDOW:
        raise HTTPException(422, f"window of {(end - start).days} days exceeds the {MAX_WINDOW.days}-day maximum")
    return start, end


def _num(x) -> Optional[float]:
    return None if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)


def _events(events) -> list[DeficitEventOut]:
    return [DeficitEventOut.model_validate(e, from_attributes=True) for e in events]


@router.get("/performance/{plant_id}", response_model=PerformanceResponse,
            summary="Expected vs actual power, deficit events, open deficit alerts and latest soiling/degradation")
def get_performance(plant_id: int, start: Optional[datetime] = Query(default=None),
                    end: Optional[datetime] = Query(default=None), baseline: Baseline = Query(default="pvwatts"),
                    db: Session = Depends(get_db)):
    plant = _plant(db, plant_id)
    start, end = _window(start, end)
    open_alerts = [AlertResponse.model_validate(a) for a in db.execute(select(PlantAlert).where(
        PlantAlert.plant_id == plant_id, PlantAlert.alert_type == deficit.ALERT_TYPE,
        PlantAlert.is_resolved.is_(False)).order_by(PlantAlert.timestamp.desc())).scalars()]
    out = dict(plant_id=plant_id, baseline=baseline, start=start, end=end, open_alerts=open_alerts,
               soiling=soiling_analytics.latest(db, plant_id, "soiling"),
               degradation=soiling_analytics.latest(db, plant_id, "degradation"))
    inputs = deficit.load_inputs(db, plant, start, end, **_providers())
    if inputs is None:
        return PerformanceResponse(status="no_telemetry", **out)
    tel, weather, strings, inverters = inputs
    perf = deficit.performance(plant, tel, weather, baseline, strings, inverters)
    series = [HourlyPoint(ts=ts, expected_kw=_num(r.expected_kw), actual_kw=_num(r.actual_kw), pi=_num(r.pi),
                          clear=bool(r.clear), usable=bool(r.usable), source=str(r.source))
              for ts, r in deficit.plant_hourly(perf).iterrows()]
    return PerformanceResponse(status="ok", data_source=perf.data_source, series=series,
                               events=_events(deficit.detect(perf, plant)), qc=perf.qc, provenance=perf.provenance, **out)


@router.post("/performance/{plant_id}/scan", response_model=ScanResponse,
             summary="Run the deficit detector now and persist/update its alerts")
def scan_plant(plant_id: int, start: Optional[datetime] = Query(default=None),
               end: Optional[datetime] = Query(default=None), baseline: Baseline = Query(default="pvwatts"),
               db: Session = Depends(get_db)):
    _plant(db, plant_id)
    start, end = _window(start, end)
    res = deficit.scan_and_persist(db, plant_id, start, end, baseline, **_providers())
    return ScanResponse(status=res["status"], qc_status=res.get("qc_status"),
                        clock_offset_min=res.get("clock_offset_min"), baseline=res.get("baseline"), data_source=res.get("data_source"),
                        events=_events(res["events"]), alert_ids=res["alerts"], qc=res["qc"],
                        provenance=res["provenance"])


@router.put("/performance/{plant_id}/thresholds", response_model=ThresholdsResponse,
            summary="Set the plant's PI warning/critical thresholds and clear hours needed to alert")
def set_thresholds(plant_id: int, body: ThresholdsRequest, db: Session = Depends(get_db)):
    plant = _plant(db, plant_id)
    plant.pi_warning, plant.pi_critical = body.pi_warning, body.pi_critical
    plant.deficit_min_clear_hours = body.deficit_min_clear_hours
    db.commit()
    return ThresholdsResponse(plant_id=plant_id, **body.model_dump())


@router.get("/strings/{string_id}/peers", response_model=PeersResponse,
            summary="A string's normalised yield against its peer strings")
def string_peers(string_id: int, start: Optional[datetime] = Query(default=None),
                 end: Optional[datetime] = Query(default=None), db: Session = Depends(get_db)):
    string = db.get(PvString, string_id)
    if string is None:
        raise HTTPException(404, f"String {string_id} not found")
    plant = _plant(db, string.plant_id)
    start, end = _window(start, end)
    base = dict(string_id=string_id, plant_id=plant.id, start=start, end=end)
    inputs = deficit.load_inputs(db, plant, start, end, **_providers())
    if inputs is None:
        return PeersResponse(status="no_telemetry", **base)
    tel, weather, strings, inverters = inputs
    perf = deficit.performance(plant, tel, weather, "pvwatts", strings, inverters)
    med, z = deficit.peer_z(perf, plant.deficit_min_clear_hours)
    hours = {k[1]: len(h) for k, h in perf.hourly.items() if k[0] == "string"}
    peers = [PeerValue(string_id=int(i), name=perf.names[("string", int(i))], normalised_yield=round(float(v), 4),
                       peer_z=None if int(i) not in z else round(z[int(i)], 2), clear_hours=hours[int(i)])
             for i, v in med.items()]
    if not hours.get(string_id):
        return PeersResponse(status="no_clear_hours_for_string", peers=peers, **base)
    own = round(float(perf.hourly[("string", string_id)]["pi"].median()), 4)
    return PeersResponse(status="ok", normalised_yield=own, peer_z=None if string_id not in z else round(z[string_id], 2),
                         plant_median=None if med.empty else round(float(med.median()), 4), peers=peers, **base)
