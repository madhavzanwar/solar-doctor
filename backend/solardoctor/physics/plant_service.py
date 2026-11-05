# Adapted from SolarPulseAI app/services/plant_service.py
# (https://github.com/anugrahpatil-creator/SolarPulseAI), MIT License,
# Copyright (c) 2026 anugrahpatil-creator. See THIRD_PARTY_NOTICES.md.
# Modified for SolarDoctor: sync SQLAlchemy 2.0; PlantConfig folded into the plants table; Park link.
"""Plant management (sync). SolarPulse field names are mapped onto the ``plants`` columns:

capacity_kw -> dc_kw, inverter_capacity_kw -> ac_kw, latitude/longitude -> lat/lon, timezone -> tz.
"""
from __future__ import annotations

import logging
from typing import List

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from solardoctor.db.models import Park
from solardoctor.physics.models import Plant
from solardoctor.physics.schemas.plant import (
    PlantConfigCreate, PlantConfigResponse, PlantConfigUpdate, PlantCreate, PlantUpdate,
)

logger = logging.getLogger("solardoctor.physics.plants")

_FIELD_MAP = {
    "latitude": "lat", "longitude": "lon", "timezone": "tz",
    "capacity_kw": "dc_kw", "inverter_capacity_kw": "ac_kw",
}
_CONFIG_FIELDS = (
    "tilt", "azimuth", "efficiency", "soiling_threshold", "clipping_threshold",
    "forecast_horizon_minutes",
)


def _map(data: dict) -> dict:
    return {_FIELD_MAP.get(k, k): v for k, v in data.items()}


def _check_park(db: Session, park_id: str | None, plant_id: int | None = None) -> None:
    if park_id is None:
        return
    if db.get(Park, park_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Park {park_id} not found")
    other = db.execute(select(Plant).where(Plant.park_id == park_id)).scalar_one_or_none()
    if other is not None and other.id != plant_id:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Park {park_id} is already linked to plant {other.id}")


def create_plant(db: Session, data: PlantCreate) -> Plant:
    fields = _map(data.model_dump())
    _check_park(db, fields.get("park_id"))
    plant = Plant(**fields)
    db.add(plant)
    db.commit()
    db.refresh(plant)
    logger.info("Created plant id=%s name=%s", plant.id, plant.name)
    return plant


def get_plant(db: Session, plant_id: int) -> Plant:
    plant = db.get(Plant, plant_id)
    if plant is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Plant {plant_id} not found")
    return plant


def list_plants(db: Session, skip: int = 0, limit: int = 100, active_only: bool = True) -> List[Plant]:
    q = select(Plant)
    if active_only:
        q = q.where(Plant.is_active.is_(True))
    return list(db.execute(q.order_by(Plant.id).offset(skip).limit(limit)).scalars().all())


def update_plant(db: Session, plant_id: int, data: PlantUpdate) -> Plant:
    plant = get_plant(db, plant_id)
    fields = _map(data.model_dump(exclude_unset=True))
    if "park_id" in fields:
        _check_park(db, fields["park_id"], plant_id)
    for k, v in fields.items():
        setattr(plant, k, v)
    db.commit()
    db.refresh(plant)
    return plant


def delete_plant(db: Session, plant_id: int) -> dict:
    """Soft delete (is_active = False), like SolarPulse."""
    plant = get_plant(db, plant_id)
    plant.is_active = False
    db.commit()
    return {"detail": "Plant deactivated"}


def config_response(plant: Plant) -> PlantConfigResponse:
    return PlantConfigResponse(
        id=plant.id, plant_id=plant.id,
        created_at=plant.created_at, updated_at=plant.updated_at,
        **{f: getattr(plant, f) for f in _CONFIG_FIELDS},
    )


def get_plant_config(db: Session, plant_id: int) -> PlantConfigResponse:
    return config_response(get_plant(db, plant_id))


def update_plant_config(db: Session, plant_id: int, data: PlantConfigUpdate) -> PlantConfigResponse:
    plant = get_plant(db, plant_id)
    for k, v in data.model_dump(exclude_unset=True).items():
        setattr(plant, k, v)
    db.commit()
    db.refresh(plant)
    return config_response(plant)


def create_plant_config(db: Session, plant_id: int, data: PlantConfigCreate) -> PlantConfigResponse:
    plant = get_plant(db, plant_id)
    for k, v in data.model_dump().items():
        setattr(plant, k, v)
    db.commit()
    db.refresh(plant)
    return config_response(plant)
