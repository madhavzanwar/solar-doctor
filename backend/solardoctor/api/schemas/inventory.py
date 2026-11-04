"""Inventory request schemas (components, prototypes, assignments, orders)."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class ComponentBody(BaseModel):
    name: str | None = None
    category: str | None = None
    qty_total: int | None = None
    part_number: str | None = None
    vendor: str | None = None
    link: str | None = None
    unit_cost: float | None = None
    currency: str | None = None
    specs: Any | None = None
    notes: str | None = None


class PrototypeBody(BaseModel):
    name: str | None = None
    status: str | None = None
    description: str | None = None
    notes: str | None = None


class AssignmentBody(BaseModel):
    component_id: int | None = None
    prototype_id: int | None = None
    qty: int | None = None
    notes: str | None = None


class OrderBody(BaseModel):
    component_id: int | None = None
    name: str | None = None
    qty: int | None = None
    status: str | None = None
    est_unit_cost: float | None = None
    vendor: str | None = None
    link: str | None = None
    needed_by: str | None = None
    notes: str | None = None
