"""inventory router — extracted from app.py (Plan 01)."""
from __future__ import annotations

from fastapi import APIRouter
from axalon.api.deps import *  # noqa: F401,F403
from axalon.api.schemas.responses import ComponentOut, InventorySummaryOut, OrderOut, PrototypeOut
from axalon.api.schemas import AssignmentBody, ComponentBody, OrderBody, PrototypeBody

router = APIRouter(tags=["inventory"])

@router.get("/inventory/components", response_model=list[ComponentOut])
def list_inventory_components():
    """List all components with derived assigned/available quantities."""
    session = get_session()
    try:
        components = (
            session.query(InventoryComponent)
            .order_by(InventoryComponent.category.asc(), InventoryComponent.name.asc())
            .all()
        )
        return [_serialize_component(c, _assigned_qty(session, c.id)) for c in components]
    finally:
        session.close()


@router.post("/inventory/components", status_code=201)
def create_inventory_component(payload: ComponentBody):
    payload = payload.model_dump(exclude_unset=True)
    name = _clean_name(payload)
    category = str(payload.get("category") or "other")
    if category not in COMPONENT_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"category must be one of {COMPONENT_CATEGORIES}")
    qty_total = _non_negative_int(payload, "qty_total", 0)
    session = get_session()
    try:
        c = InventoryComponent(
            name=name,
            category=category,
            part_number=payload.get("part_number"),
            vendor=payload.get("vendor"),
            link=payload.get("link"),
            unit_cost=payload.get("unit_cost"),
            currency=str(payload.get("currency") or "INR"),
            qty_total=qty_total,
            specs=payload.get("specs"),
            notes=payload.get("notes"),
        )
        session.add(c)
        session.commit()
        session.refresh(c)
        return JSONResponse(content=_serialize_component(c, 0), status_code=201)
    finally:
        session.close()


@router.patch("/inventory/components/{component_id}")
def update_inventory_component(component_id: int, payload: ComponentBody):
    payload = payload.model_dump(exclude_unset=True)
    session = get_session()
    try:
        c = session.query(InventoryComponent).filter_by(id=component_id).first()
        if c is None:
            raise HTTPException(status_code=404, detail="Component not found")
        if "name" in payload:
            c.name = _clean_name(payload)
        if "category" in payload:
            category = str(payload.get("category") or "other")
            if category not in COMPONENT_CATEGORIES:
                raise HTTPException(status_code=400, detail=f"category must be one of {COMPONENT_CATEGORIES}")
            c.category = category
        if "qty_total" in payload:
            c.qty_total = _non_negative_int(payload, "qty_total", 0)
        for field in ("part_number", "vendor", "link", "unit_cost", "currency", "specs", "notes"):
            if field in payload:
                setattr(c, field, payload[field])
        session.commit()
        session.refresh(c)
        return _serialize_component(c, _assigned_qty(session, c.id))
    finally:
        session.close()


@router.delete("/inventory/components/{component_id}", status_code=204)
def delete_inventory_component(component_id: int):
    session = get_session()
    try:
        c = session.query(InventoryComponent).filter_by(id=component_id).first()
        if c is None:
            raise HTTPException(status_code=404, detail="Component not found")
        in_use = (
            session.query(ComponentAssignment)
            .filter(ComponentAssignment.component_id == component_id)
            .count()
        )
        if in_use:
            raise HTTPException(
                status_code=409,
                detail="Component is assigned to a prototype — unassign it first",
            )
        session.delete(c)
        session.commit()
        return Response(status_code=204)
    finally:
        session.close()


@router.get("/inventory/prototypes", response_model=list[PrototypeOut])
def list_prototypes():
    """List prototypes, each embedding its BOM (assignments + component names)."""
    session = get_session()
    try:
        protos = session.query(Prototype).order_by(Prototype.created_at.desc()).all()
        out = []
        for p in protos:
            rows = (
                session.query(ComponentAssignment, InventoryComponent)
                .join(InventoryComponent, ComponentAssignment.component_id == InventoryComponent.id)
                .filter(ComponentAssignment.prototype_id == p.id)
                .order_by(ComponentAssignment.created_at.asc())
                .all()
            )
            out.append(_serialize_prototype(p, [_serialize_assignment(a, c) for a, c in rows]))
        return out
    finally:
        session.close()


@router.post("/inventory/prototypes", status_code=201)
def create_prototype(payload: PrototypeBody):
    payload = payload.model_dump(exclude_unset=True)
    name = _clean_name(payload)
    status = str(payload.get("status") or "planning")
    if status not in PROTOTYPE_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {PROTOTYPE_STATUSES}")
    session = get_session()
    try:
        p = Prototype(
            name=name,
            status=status,
            description=payload.get("description"),
            notes=payload.get("notes"),
        )
        session.add(p)
        session.commit()
        session.refresh(p)
        return JSONResponse(content=_serialize_prototype(p, []), status_code=201)
    finally:
        session.close()


@router.patch("/inventory/prototypes/{prototype_id}")
def update_prototype(prototype_id: int, payload: PrototypeBody):
    payload = payload.model_dump(exclude_unset=True)
    session = get_session()
    try:
        p = session.query(Prototype).filter_by(id=prototype_id).first()
        if p is None:
            raise HTTPException(status_code=404, detail="Prototype not found")
        if "name" in payload:
            p.name = _clean_name(payload)
        if "status" in payload:
            status = str(payload.get("status") or "")
            if status not in PROTOTYPE_STATUSES:
                raise HTTPException(status_code=400, detail=f"status must be one of {PROTOTYPE_STATUSES}")
            p.status = status
        for field in ("description", "notes"):
            if field in payload:
                setattr(p, field, payload[field])
        session.commit()
        session.refresh(p)
        rows = (
            session.query(ComponentAssignment, InventoryComponent)
            .join(InventoryComponent, ComponentAssignment.component_id == InventoryComponent.id)
            .filter(ComponentAssignment.prototype_id == p.id)
            .all()
        )
        return _serialize_prototype(p, [_serialize_assignment(a, c) for a, c in rows])
    finally:
        session.close()


@router.delete("/inventory/prototypes/{prototype_id}", status_code=204)
def delete_prototype(prototype_id: int):
    """Delete a prototype and its assignments (frees the assigned stock)."""
    session = get_session()
    try:
        p = session.query(Prototype).filter_by(id=prototype_id).first()
        if p is None:
            raise HTTPException(status_code=404, detail="Prototype not found")
        session.query(ComponentAssignment).filter(
            ComponentAssignment.prototype_id == prototype_id
        ).delete(synchronize_session=False)
        session.delete(p)
        session.commit()
        return Response(status_code=204)
    finally:
        session.close()


@router.post("/inventory/assignments", status_code=201)
def create_assignment(payload: AssignmentBody):
    """Install qty units of a component into a prototype — bounded by availability."""
    payload = payload.model_dump(exclude_unset=True)
    component_id = _non_negative_int(payload, "component_id", 0, minimum=1)
    prototype_id = _non_negative_int(payload, "prototype_id", 0, minimum=1)
    qty = _non_negative_int(payload, "qty", 1, minimum=1)
    session = get_session()
    try:
        c = session.query(InventoryComponent).filter_by(id=component_id).first()
        if c is None:
            raise HTTPException(status_code=404, detail="Component not found")
        p = session.query(Prototype).filter_by(id=prototype_id).first()
        if p is None:
            raise HTTPException(status_code=404, detail="Prototype not found")
        available = (c.qty_total or 0) - _assigned_qty(session, component_id)
        if qty > available:
            raise HTTPException(
                status_code=400,
                detail=f"Only {available} unit(s) of '{c.name}' available",
            )
        a = ComponentAssignment(
            component_id=component_id,
            prototype_id=prototype_id,
            qty=qty,
            notes=payload.get("notes"),
        )
        session.add(a)
        session.commit()
        session.refresh(a)
        return JSONResponse(content=_serialize_assignment(a, c), status_code=201)
    finally:
        session.close()


@router.patch("/inventory/assignments/{assignment_id}")
def update_assignment(assignment_id: int, payload: AssignmentBody):
    payload = payload.model_dump(exclude_unset=True)
    session = get_session()
    try:
        a = session.query(ComponentAssignment).filter_by(id=assignment_id).first()
        if a is None:
            raise HTTPException(status_code=404, detail="Assignment not found")
        c = session.query(InventoryComponent).filter_by(id=a.component_id).first()
        if "qty" in payload:
            qty = _non_negative_int(payload, "qty", 1, minimum=1)
            available = (c.qty_total or 0) - _assigned_qty(
                session, a.component_id, exclude_assignment_id=a.id
            )
            if qty > available:
                raise HTTPException(
                    status_code=400,
                    detail=f"Only {available} unit(s) of '{c.name}' available",
                )
            a.qty = qty
        if "notes" in payload:
            a.notes = payload["notes"]
        session.commit()
        session.refresh(a)
        return _serialize_assignment(a, c)
    finally:
        session.close()


@router.delete("/inventory/assignments/{assignment_id}", status_code=204)
def delete_assignment(assignment_id: int):
    session = get_session()
    try:
        a = session.query(ComponentAssignment).filter_by(id=assignment_id).first()
        if a is None:
            raise HTTPException(status_code=404, detail="Assignment not found")
        session.delete(a)
        session.commit()
        return Response(status_code=204)
    finally:
        session.close()


@router.get("/inventory/orders", response_model=list[OrderOut])
def list_orders():
    session = get_session()
    try:
        orders = session.query(ComponentOrder).order_by(ComponentOrder.created_at.desc()).all()
        return [_serialize_order(o) for o in orders]
    finally:
        session.close()


@router.post("/inventory/orders", status_code=201)
def create_order(payload: OrderBody):
    payload = payload.model_dump(exclude_unset=True)
    status = str(payload.get("status") or "planned")
    if status not in ORDER_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {ORDER_STATUSES}")
    qty = _non_negative_int(payload, "qty", 1, minimum=1)
    session = get_session()
    try:
        component_id = payload.get("component_id")
        name = _clean_name(payload, required=False)
        if component_id is not None:
            c = session.query(InventoryComponent).filter_by(id=int(component_id)).first()
            if c is None:
                raise HTTPException(status_code=404, detail="Component not found")
            name = name or c.name
        if not name:
            raise HTTPException(status_code=400, detail="name or component_id is required")
        o = ComponentOrder(
            component_id=component_id,
            name=name,
            qty=qty,
            est_unit_cost=payload.get("est_unit_cost"),
            vendor=payload.get("vendor"),
            link=payload.get("link"),
            status=status,
            needed_by=payload.get("needed_by"),
            notes=payload.get("notes"),
        )
        session.add(o)
        session.commit()
        session.refresh(o)
        return JSONResponse(content=_serialize_order(o), status_code=201)
    finally:
        session.close()


@router.patch("/inventory/orders/{order_id}")
def update_order(order_id: int, payload: OrderBody):
    """Update an order. Transitioning to 'received' on a linked order stocks-in qty."""
    payload = payload.model_dump(exclude_unset=True)
    session = get_session()
    try:
        o = session.query(ComponentOrder).filter_by(id=order_id).first()
        if o is None:
            raise HTTPException(status_code=404, detail="Order not found")
        if "status" in payload:
            status = str(payload.get("status") or "")
            if status not in ORDER_STATUSES:
                raise HTTPException(status_code=400, detail=f"status must be one of {ORDER_STATUSES}")
            if status == "received" and o.status != "received" and o.component_id:
                c = session.query(InventoryComponent).filter_by(id=o.component_id).first()
                if c is not None:
                    c.qty_total = (c.qty_total or 0) + (o.qty or 0)
            o.status = status
        if "name" in payload:
            o.name = _clean_name(payload)
        if "qty" in payload:
            o.qty = _non_negative_int(payload, "qty", 1, minimum=1)
        for field in ("est_unit_cost", "vendor", "link", "needed_by", "notes"):
            if field in payload:
                setattr(o, field, payload[field])
        session.commit()
        session.refresh(o)
        return _serialize_order(o)
    finally:
        session.close()


@router.delete("/inventory/orders/{order_id}", status_code=204)
def delete_order(order_id: int):
    session = get_session()
    try:
        o = session.query(ComponentOrder).filter_by(id=order_id).first()
        if o is None:
            raise HTTPException(status_code=404, detail="Order not found")
        session.delete(o)
        session.commit()
        return Response(status_code=204)
    finally:
        session.close()


@router.get("/inventory/summary", response_model=InventorySummaryOut)
def inventory_summary():
    """Headline numbers for the Inventory tab."""
    session = get_session()
    try:
        components = session.query(InventoryComponent).all()
        low_stock = []
        stock_value = 0.0
        for c in components:
            assigned = _assigned_qty(session, c.id)
            available = (c.qty_total or 0) - assigned
            stock_value += (c.unit_cost or 0.0) * (c.qty_total or 0)
            if available < 1:
                low_stock.append(_serialize_component(c, assigned))
        open_orders = (
            session.query(ComponentOrder)
            .filter(ComponentOrder.status.in_(("planned", "ordered")))
            .count()
        )
        return {
            "component_count": len(components),
            "prototype_count": session.query(Prototype).count(),
            "open_order_count": open_orders,
            "stock_value": stock_value,
            "low_stock": low_stock,
        }
    finally:
        session.close()
