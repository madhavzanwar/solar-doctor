"""plants router: SolarPulse /plants endpoints (sync, Axalon session pattern)."""
from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from solardoctor.physics import plant_service
from solardoctor.physics.deps import get_db
from solardoctor.physics.schemas.plant import (
    PlantConfigResponse, PlantConfigUpdate, PlantCreate, PlantResponse, PlantUpdate,
)

router = APIRouter(prefix="/plants", tags=["Plants"])


@router.post("", response_model=PlantResponse, status_code=status.HTTP_201_CREATED,
             summary="Create a new solar plant")
def create_plant(data: PlantCreate, db: Session = Depends(get_db)):
    return plant_service.create_plant(db, data)


@router.get("", response_model=List[PlantResponse], summary="List all active plants")
def list_plants(skip: int = Query(default=0, ge=0), limit: int = Query(default=100, ge=1, le=500), db: Session = Depends(get_db)):
    return plant_service.list_plants(db, skip=skip, limit=limit)


@router.get("/{plant_id}", response_model=PlantResponse, summary="Get a plant by ID")
def get_plant(plant_id: int, db: Session = Depends(get_db)):
    return plant_service.get_plant(db, plant_id)


@router.put("/{plant_id}", response_model=PlantResponse, summary="Update a plant")
def update_plant(plant_id: int, data: PlantUpdate, db: Session = Depends(get_db)):
    return plant_service.update_plant(db, plant_id, data)


@router.delete("/{plant_id}", summary="Deactivate a plant (soft delete)")
def delete_plant(plant_id: int, db: Session = Depends(get_db)) -> dict:
    return plant_service.delete_plant(db, plant_id)


@router.get("/{plant_id}/config", response_model=PlantConfigResponse, summary="Get plant configuration")
def get_plant_config(plant_id: int, db: Session = Depends(get_db)):
    return plant_service.get_plant_config(db, plant_id)


@router.put("/{plant_id}/config", response_model=PlantConfigResponse, summary="Update plant configuration")
def update_plant_config(plant_id: int, data: PlantConfigUpdate, db: Session = Depends(get_db)):
    return plant_service.update_plant_config(db, plant_id, data)
