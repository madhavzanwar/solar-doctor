"""Idempotent DB seeding for the three SIMULATED demo plants, users, faults and alerts."""
from __future__ import annotations

import json
import logging
import os
import secrets
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

import pandas as pd
from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from solardoctor.core.auth import create_user
from solardoctor.db.models import PanelFault, Park, Project, ProjectMember, User
from solardoctor.physics.models import (
    Forecast, Inverter, PlantAlert, PvString, Telemetry, WeatherCache, Plant,
)
from solardoctor.seed import alerts as seed_alerts
from solardoctor.seed import irradiance as irr_mod
from solardoctor.seed import simulate
from solardoctor.seed.specs import (
    CLOUDY_SPELL_DAYS, CLOUDY_SPELL_K_FACTOR, FAULTS, PLANTS, PROJECT_NAME, SOURCE, PlantSpec,
)

log = logging.getLogger("solardoctor.seed")

DEFAULT_ADMIN_EMAIL = "admin@solardoctor.example"
DEFAULT_TECH_EMAIL = "technician@solardoctor.example"
FORECAST_HINDCAST_DAYS = 2
META_KIND = "seed_meta"


@dataclass
class SeedReport:
    window_start: Optional[pd.Timestamp] = None
    window_note: str = ""
    created_users: dict = field(default_factory=dict)   # email -> (role, password or None if pre-existing)
    plants: dict = field(default_factory=dict)          # name -> dict(id, status, irradiance_source, telemetry_rows, alerts)
    manifest: dict = field(default_factory=dict)


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


# ---------------------------------------------------------------- users
def _ensure_user(db: Session, email: str, role: str, password: Optional[str], project_ids, report: SeedReport) -> None:
    existing = db.query(User).filter(User.email == email.strip().lower()).first()
    if existing is not None:
        report.created_users[email] = (existing.role, None)
        return
    generated = password is None
    password = password or secrets.token_urlsafe(15)
    create_user(db, email=email, password=password, role=role, project_ids=project_ids)
    # Printed once by the CLI; never stored anywhere but the hash.
    report.created_users[email] = (role, password if generated else "(from environment)")


# ---------------------------------------------------------------- reset
def reset_simulated(db: Session) -> None:
    """Drop SIMULATED plants (and their dependants) and the seed parks/faults; never touches users or PVDAQ plants."""
    ids = [p.id for p in db.query(Plant).filter(Plant.source == SOURCE).all()]
    if ids:
        db.execute(delete(Telemetry).where(Telemetry.plant_id.in_(ids)))
        db.execute(delete(Forecast).where(Forecast.plant_id.in_(ids)))
        db.execute(delete(PlantAlert).where(PlantAlert.plant_id.in_(ids)))
        db.execute(delete(PvString).where(PvString.plant_id.in_(ids)))
        db.execute(delete(Inverter).where(Inverter.plant_id.in_(ids)))
        db.execute(delete(Plant).where(Plant.id.in_(ids)))
    park_ids = [s.park_id for s in PLANTS]
    db.execute(delete(PanelFault).where(PanelFault.park_id.in_(park_ids), PanelFault.notes.like("SIMULATED%")))
    db.execute(delete(WeatherCache).where(WeatherCache.kind == META_KIND))
    db.commit()


# ---------------------------------------------------------------- plants
def _ensure_project_and_parks(db: Session) -> Project:
    proj = db.query(Project).filter(Project.name == PROJECT_NAME).first()
    if proj is None:
        proj = Project(name=PROJECT_NAME, client="Photosphere demo", status="active",
                       description="SIMULATED demo portfolio created by scripts/seed.py")
        db.add(proj)
        db.commit()
    for s in PLANTS:
        park = db.get(Park, s.park_id)
        if park is None:
            db.add(Park(id=s.park_id, name=s.name, mode="auto", total_panels=s.module_count, project_id=proj.id))
    db.commit()
    return proj


def _plant_has_telemetry(db: Session, plant_id: int) -> bool:
    return db.scalar(select(func.count()).select_from(Telemetry).where(Telemetry.plant_id == plant_id)) > 0


def _bulk_insert(db: Session, rows: list[dict], chunk: int = 5000) -> None:
    for i in range(0, len(rows), chunk):
        db.execute(insert(Telemetry), rows[i:i + chunk])
    db.commit()


def _seed_plant(db: Session, spec: PlantSpec, times: pd.DatetimeIndex, window_start: pd.Timestamp, seed: int,
                fetcher, cache_dir: Path, allow_network: bool, report: SeedReport) -> None:
    existing = db.query(Plant).filter(Plant.name == spec.name).first()
    if existing is not None:
        if existing.source != SOURCE:
            report.plants[spec.name] = dict(id=existing.id, status="skipped (name used by a non-SIMULATED plant)")
            return
        if _plant_has_telemetry(db, existing.id):
            report.plants[spec.name] = dict(id=existing.id, status="exists")
            return
        # half-finished earlier run: rebuild cleanly
        for model in (Telemetry, Forecast, PlantAlert, PvString, Inverter):
            db.execute(delete(model).where(model.plant_id == existing.id))
        db.delete(existing)
        db.commit()

    irr = irr_mod.get_irradiance(spec.lat, spec.lon, spec.altitude_m, spec.key, times, seed, fetcher, cache_dir,
                                 allow_network)
    frame = irr_mod.apply_cloudy_spell(irr.frame, window_start, CLOUDY_SPELL_DAYS, CLOUDY_SPELL_K_FACTOR)
    plant_seed = seed + sum(map(ord, spec.key))
    sim = simulate.simulate_plant(spec, times, frame, plant_seed)

    plant = simulate.transient_plant(spec)
    plant.park_id = spec.park_id
    db.add(plant)
    db.flush()
    inverter_ids: dict[int, int] = {}
    per_inv_ac = spec.ac_kw / spec.inverters
    for i in range(spec.inverters):
        inv = Inverter(plant_id=plant.id, name=f"INV-{i + 1:02d}", ac_kw=per_inv_ac, vendor="SIMULATED")
        db.add(inv)
        db.flush()
        inverter_ids[i] = inv.id
    string_ids: dict[str, int] = {}
    for st in spec.strings:
        row = PvString(plant_id=plant.id, inverter_id=inverter_ids[st.inverter], name=st.name,
                       module_count=st.modules)
        db.add(row)
        db.flush()
        string_ids[st.name] = row.id
    db.commit()

    rows = simulate.telemetry_rows(sim, plant.id, inverter_ids, string_ids)
    _bulk_insert(db, rows)

    alerts = seed_alerts.generate_alerts(db, plant.id, sim, plant.soiling_threshold)

    # Hindcast "forecast" rows so /forecast/{id}/summary has data: physics baseline vs simulated actual.
    n = FORECAST_HINDCAST_DAYS * 96
    idx = range(len(times) - n, len(times))
    exp_ac, dc_clean = sim.clean["p_ac_kw"].to_numpy(), sim.clean["p_dc_kw"].to_numpy()
    gen = _utcnow()
    db.add_all(Forecast(
        plant_id=plant.id, forecast_time=times[i].to_pydatetime(), generated_at=gen,
        predicted_power_kw=round(float(exp_ac[i]), 4), actual_power_kw=round(float(sim.plant_ac_kw[i]), 4),
        confidence_lower=round(float(exp_ac[i]) * 0.9, 4), confidence_upper=round(min(spec.ac_kw, float(exp_ac[i]) * 1.1), 4),
        model_name="seed_physics_hindcast_SIMULATED", model_version="seed-1",
        physics_power_kw=round(float(dc_clean[i]), 4), ml_power_kw=None) for i in idx)
    db.add(WeatherCache(
        lat_key=round(spec.lat, 1), lon_key=round(spec.lon, 1), kind=META_KIND, source=SOURCE,
        payload_json=json.dumps(dict(
            plant=spec.name, source=SOURCE, irradiance_source=irr.source, irradiance_note=irr.note,
            window_start=str(times[0]), window_end=str(times[-1]), cadence_min=simulate.STEP_MIN,
            seed=seed, cloudy_spell_days=list(CLOUDY_SPELL_DAYS), cloudy_spell_k_factor=CLOUDY_SPELL_K_FACTOR)),
        fetched_at=_utcnow(), expires_at=_utcnow() + timedelta(days=36500)))
    db.commit()

    report.plants[spec.name] = dict(
        id=plant.id, status="created", irradiance_source=irr.source, telemetry_rows=len(rows),
        alerts=[dict(id=a.id, type=a.alert_type, severity=a.severity, ts=a.timestamp.isoformat(),
                     deviation=a.deviation_percent, resolved=a.is_resolved) for a in alerts])


# ---------------------------------------------------------------- faults
def _ensure_faults(db: Session, tech_email: str) -> None:
    keys = {s.key: s for s in PLANTS}
    today = date.today()
    for f in FAULTS:
        spec = keys[f["plant"]]
        exists = db.query(PanelFault).filter(PanelFault.park_id == spec.park_id, PanelFault.panel_id == f["panel_id"],
                                             PanelFault.class_ == f["class_"]).first()
        if exists is not None:
            continue
        from ml.thermal.src.utils import CLASS2ID, SEVERITY_MAP
        db.add(PanelFault(
            park_id=spec.park_id, panel_id=f["panel_id"], class_=f["class_"], class_id=CLASS2ID.get(f["class_"]),
            severity=SEVERITY_MAP.get(f["class_"]), status=f["status"], max_confidence=f["confidence"],
            first_seen_date=today.isoformat(), last_seen_date=today.isoformat(), notes=f["note"],
            assignee=tech_email if f["assign"] else None,
            due_date=(today + timedelta(days=f["due_days"])) if f["due_days"] else None))
    db.commit()


# ---------------------------------------------------------------- entry point
def run_seed(db: Session, *, days: int = 30, seed: int = 42, fetcher: Callable = irr_mod.fetch_nasa_power,
             cache_dir: Path, allow_network: bool = True, reset: bool = False,
             window_end: Optional[str] = None, manifest_path: Optional[Path] = None,
             env: Optional[dict] = None) -> SeedReport:
    env = os.environ if env is None else env
    report = SeedReport()
    if reset:
        reset_simulated(db)

    proj = _ensure_project_and_parks(db)
    admin_email = env.get("SOLARDOCTOR_SEED_ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL)
    tech_email = env.get("SOLARDOCTOR_SEED_TECH_EMAIL", DEFAULT_TECH_EMAIL)
    _ensure_user(db, admin_email, "admin", env.get("SOLARDOCTOR_SEED_ADMIN_PASSWORD"), (), report)
    _ensure_user(db, tech_email, "technician", env.get("SOLARDOCTOR_SEED_TECH_PASSWORD"), (proj.id,), report)

    if window_end:
        end_day = pd.Timestamp(window_end, tz="UTC").normalize()
        start, note = end_day - pd.Timedelta(days=days - 1), f"window ends {window_end} (--end)"
    elif allow_network:
        probe = PLANTS[0]
        start, note = irr_mod.discover_window(fetcher, cache_dir, probe.lat, probe.lon, days)
    else:
        start = pd.Timestamp.now(tz="UTC").normalize() - pd.Timedelta(days=days)
        note = "offline: window ends yesterday"
    times = simulate.window_index(start, days)
    report.window_start, report.window_note = times[0], note

    for spec in PLANTS:
        _seed_plant(db, spec, times, times[0], seed, fetcher, cache_dir, allow_network, report)
    _ensure_faults(db, tech_email.strip().lower())

    report.manifest = dict(
        source=SOURCE, window_start=str(times[0]), window_end=str(times[-1]), cadence_min=simulate.STEP_MIN,
        window_note=note, seed=seed, cloudy_spell_days=list(CLOUDY_SPELL_DAYS),
        injected=dict(
            soiling={s.name: dict(start_pct=s.soiling_start_pct, rate_pct_per_day=s.soiling_rate_pct_day,
                                  cleaning_days=list(s.cleaning_days)) for s in PLANTS},
            string_faults=[dict(plant=s.name, string=st.name, loss_fraction=st.fault_loss, start_day=st.fault_start_day)
                           for s in PLANTS for st in s.strings if st.fault_loss]),
        plants=report.plants)
    if manifest_path is not None:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_path.write_text(json.dumps(report.manifest, indent=2, default=str))
    return report
