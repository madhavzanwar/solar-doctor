"""Physics background jobs: hourly deficit scan, daily rescan + soiling + degradation.

    python -m solardoctor.physics.jobs hourly|daily

There is no generic scheduler in the repo (Axalon's jobs are FastAPI BackgroundTasks for inspections), so
``scheduler()`` is a small asyncio loop started from the API lifespan only when SOLARDOCTOR_PHYSICS_JOBS=1.
Both jobs are idempotent (alerts and plant_analytics are upserts) and a failing plant never stops the others.
Tracker plants are skipped: they have no baseline (see physics.tracker).
"""
from __future__ import annotations

import asyncio
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from solardoctor.db.session import get_session
from solardoctor.physics import deficit, irradiance, soiling_analytics as sa
from solardoctor.physics import weather_service as ws
from solardoctor.physics.models import Plant
from solardoctor.physics.tracker import is_tracker_plant

logger = logging.getLogger("solardoctor.physics.jobs")

HOURLY_WINDOW = timedelta(hours=24)
DAILY_RESCAN = timedelta(days=7)
ANALYTICS_LOOKBACK = timedelta(days=800)  # a little over the 2 years year-on-year degradation needs
MIN_HOURS_PER_DAY = 4                     # clear usable hours for a day to enter the daily series
DAILY_RUN_HOUR_UTC = 2


def _plants(db: Session) -> list[Plant]:
    return [p for p in db.execute(select(Plant).where(Plant.is_active.is_(True)).order_by(Plant.id)).scalars()
            if not is_tracker_plant(p)]


def daily_series(perf: deficit.Performance, weather: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    """Plant-scope daily ``actual_kwh``/``expected_kwh``/``insolation`` (clear usable hours only) and hourly rain (mm)."""
    rain = weather["precip_mm"].resample("1h").mean()
    h = perf.hourly.get(("plant", None))
    if h is None or h.empty:
        return pd.DataFrame(columns=["actual_kwh", "expected_kwh", "insolation"]), rain
    hours = pd.DataFrame({"actual_kwh": h["actual_kw"], "expected_kwh": h["expected_kw"],  # kW x 1 h
                          "insolation": weather["ghi"].resample("1h").mean().reindex(h.index) / 1000.0, "n": 1})
    day = hours.groupby(hours.index.floor("D")).sum()
    return day[day["n"] >= MIN_HOURS_PER_DAY].drop(columns="n"), rain


def _analytics(db: Session, plant: Plant, now: datetime, nasa_fetch: Callable, openmeteo_fetch: Callable) -> dict:
    inputs = deficit.load_inputs(db, plant, now - ANALYTICS_LOOKBACK, now, now, nasa_fetch, openmeteo_fetch)
    if inputs is None:
        return {"soiling": "no_telemetry", "degradation": "no_telemetry"}
    tel, weather, strings, inverters = inputs
    perf = deficit.performance(plant, tel, weather, "pvwatts", strings, inverters)
    daily, rain = daily_series(perf, weather)
    out = {}
    for kind, result in (("soiling", sa.soiling_analysis(plant, daily, rain)), ("degradation", sa.degradation_analysis(plant, daily))):
        sa.save(db, plant.id, kind, now.date(), result, now)
        out[kind] = result["status"]
    return out


def _for_each_plant(db: Session, job: str, fn: Callable[[Plant], object]) -> dict[int, object]:
    results: dict[int, object] = {}
    for plant in _plants(db):
        try:
            results[plant.id] = fn(plant)
        except Exception:
            db.rollback()
            logger.exception("physics %s job failed for plant %s", job, plant.id)
            results[plant.id] = "error"
    return results


def run_hourly(db: Session, now: Optional[datetime] = None, nasa_fetch: Callable = ws.fetch_nasa_power_hourly,
               openmeteo_fetch: Callable = irradiance.fetch_openmeteo_hourly) -> dict[int, object]:
    """Deficit scan over the last 24 h for every active non-tracker plant; returns {plant_id: scan status | 'error'}."""
    now = now or datetime.now(timezone.utc)
    return _for_each_plant(db, "hourly", lambda p: deficit.scan_and_persist(
        db, p.id, now - HOURLY_WINDOW, now, now=now, nasa_fetch=nasa_fetch, openmeteo_fetch=openmeteo_fetch)["status"])


def run_daily(db: Session, now: Optional[datetime] = None, nasa_fetch: Callable = ws.fetch_nasa_power_hourly,
              openmeteo_fetch: Callable = irradiance.fetch_openmeteo_hourly) -> dict[int, object]:
    """Rescan the last 7 days, then soiling + degradation (persisted to plant_analytics) per plant."""
    now = now or datetime.now(timezone.utc)

    def one(plant: Plant) -> dict:
        scan = deficit.scan_and_persist(db, plant.id, now - DAILY_RESCAN, now, now=now, nasa_fetch=nasa_fetch,
                                        openmeteo_fetch=openmeteo_fetch)["status"]
        return {"scan": scan, **_analytics(db, plant, now, nasa_fetch, openmeteo_fetch)}
    return _for_each_plant(db, "daily", one)


JOBS = {"hourly": run_hourly, "daily": run_daily}


def _run_in_new_session(job: str) -> dict:
    db = get_session()
    try:
        return JOBS[job](db)
    finally:
        db.close()


async def scheduler() -> None:
    """Hourly job at each top of the hour, daily job in the DAILY_RUN_HOUR_UTC hour. Never raises (except cancel)."""
    while True:
        now = datetime.now(timezone.utc)
        await asyncio.sleep((now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1) - now).total_seconds())
        for job in ("hourly", "daily") if datetime.now(timezone.utc).hour == DAILY_RUN_HOUR_UTC else ("hourly",):
            try:
                logger.info("physics %s job: %s", job, await asyncio.to_thread(_run_in_new_session, job))
            except Exception:
                logger.exception("physics %s job crashed", job)


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in JOBS:
        sys.exit("usage: python -m solardoctor.physics.jobs hourly|daily")
    print(json.dumps(_run_in_new_session(sys.argv[1]), indent=2))
