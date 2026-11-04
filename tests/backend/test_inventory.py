"""Tests for the inventory / prototype tracking API (spec: 2026-06-12-inventory-page-design)."""
from axalon.db.models import ComponentAssignment, InventoryComponent, Prototype


# ── helpers ───────────────────────────────────────────────────────────────────

def _make_component(client, **overrides) -> dict:
    payload = {
        "name": "T-Motor F90 1300KV",
        "category": "motor",
        "qty_total": 8,
        "unit_cost": 2400.0,
        "vendor": "T-Motor",
    }
    payload.update(overrides)
    resp = client.post("/inventory/components", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _make_prototype(client, **overrides) -> dict:
    payload = {"name": "Axalon Mk1", "status": "building"}
    payload.update(overrides)
    resp = client.post("/inventory/prototypes", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def _assign(client, component_id: int, prototype_id: int, qty: int = 1):
    return client.post(
        "/inventory/assignments",
        json={"component_id": component_id, "prototype_id": prototype_id, "qty": qty},
    )


# ── models ────────────────────────────────────────────────────────────────────

def test_inventory_models_persist(db_session):
    comp = InventoryComponent(name="Pixhawk 6C", category="flight-controller", qty_total=2)
    proto = Prototype(name="Bench rig", status="planning")
    db_session.add_all([comp, proto])
    db_session.commit()
    db_session.add(ComponentAssignment(component_id=comp.id, prototype_id=proto.id, qty=1))
    db_session.commit()

    fetched = db_session.query(InventoryComponent).filter_by(name="Pixhawk 6C").one()
    assert fetched.category == "flight-controller"
    assert fetched.qty_total == 2
    assert db_session.query(ComponentAssignment).count() == 1


# ── components CRUD ───────────────────────────────────────────────────────────

def test_create_and_list_components(client):
    created = _make_component(client)
    assert created["name"] == "T-Motor F90 1300KV"
    assert created["qty_total"] == 8
    assert created["qty_assigned"] == 0
    assert created["qty_available"] == 8

    listed = client.get("/inventory/components").json()
    assert len(listed) == 1
    assert listed[0]["id"] == created["id"]


def test_create_component_requires_name(client):
    resp = client.post("/inventory/components", json={"name": "  ", "qty_total": 1})
    assert resp.status_code == 400


def test_create_component_rejects_negative_qty(client):
    resp = client.post("/inventory/components", json={"name": "ESC", "qty_total": -1})
    assert resp.status_code == 400


def test_patch_component(client):
    created = _make_component(client)
    resp = client.patch(
        f"/inventory/components/{created['id']}",
        json={"qty_total": 10, "notes": "two spares added"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["qty_total"] == 10
    assert body["notes"] == "two spares added"


def test_patch_component_404(client):
    assert client.patch("/inventory/components/999", json={"qty_total": 1}).status_code == 404


def test_delete_component(client):
    created = _make_component(client)
    assert client.delete(f"/inventory/components/{created['id']}").status_code == 204
    assert client.get("/inventory/components").json() == []


def test_delete_component_blocked_while_assigned(client):
    comp = _make_component(client)
    proto = _make_prototype(client)
    assert _assign(client, comp["id"], proto["id"], qty=2).status_code == 201
    assert client.delete(f"/inventory/components/{comp['id']}").status_code == 409


# ── prototypes + assignments ──────────────────────────────────────────────────

def test_prototype_crud_and_embedded_bom(client):
    comp = _make_component(client)
    proto = _make_prototype(client)
    assert proto["status"] == "building"

    assert _assign(client, comp["id"], proto["id"], qty=4).status_code == 201

    protos = client.get("/inventory/prototypes").json()
    assert len(protos) == 1
    bom = protos[0]["assignments"]
    assert len(bom) == 1
    assert bom[0]["component_id"] == comp["id"]
    assert bom[0]["component_name"] == comp["name"]
    assert bom[0]["qty"] == 4

    # availability reflects the assignment
    comp_now = client.get("/inventory/components").json()[0]
    assert comp_now["qty_assigned"] == 4
    assert comp_now["qty_available"] == 4

    resp = client.patch(f"/inventory/prototypes/{proto['id']}", json={"status": "active"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


def test_prototype_requires_name(client):
    assert client.post("/inventory/prototypes", json={"name": ""}).status_code == 400


def test_prototype_rejects_bad_status(client):
    assert client.post("/inventory/prototypes", json={"name": "X", "status": "flying"}).status_code == 400


def test_assignment_cannot_exceed_availability(client):
    comp = _make_component(client, qty_total=2)
    proto = _make_prototype(client)
    assert _assign(client, comp["id"], proto["id"], qty=3).status_code == 400
    assert _assign(client, comp["id"], proto["id"], qty=2).status_code == 201
    # nothing left
    assert _assign(client, comp["id"], proto["id"], qty=1).status_code == 400


def test_assignment_404_on_missing_refs(client):
    comp = _make_component(client)
    assert _assign(client, comp["id"], 999).status_code == 404
    proto = _make_prototype(client)
    assert _assign(client, 999, proto["id"]).status_code == 404


def test_patch_assignment_qty_excludes_self(client):
    comp = _make_component(client, qty_total=4)
    proto = _make_prototype(client)
    a = _assign(client, comp["id"], proto["id"], qty=3).json()
    # raising 3 -> 4 is fine (3 is its own), 3 -> 5 is not
    assert client.patch(f"/inventory/assignments/{a['id']}", json={"qty": 4}).status_code == 200
    assert client.patch(f"/inventory/assignments/{a['id']}", json={"qty": 5}).status_code == 400


def test_delete_assignment_frees_stock(client):
    comp = _make_component(client, qty_total=2)
    proto = _make_prototype(client)
    a = _assign(client, comp["id"], proto["id"], qty=2).json()
    assert client.delete(f"/inventory/assignments/{a['id']}").status_code == 204
    comp_now = client.get("/inventory/components").json()[0]
    assert comp_now["qty_available"] == 2


def test_delete_prototype_cascades_assignments(client):
    comp = _make_component(client, qty_total=2)
    proto = _make_prototype(client)
    _assign(client, comp["id"], proto["id"], qty=2)
    assert client.delete(f"/inventory/prototypes/{proto['id']}").status_code == 204
    comp_now = client.get("/inventory/components").json()[0]
    assert comp_now["qty_assigned"] == 0
    assert comp_now["qty_available"] == 2


# ── orders ────────────────────────────────────────────────────────────────────

def test_order_crud_and_defaults(client):
    resp = client.post(
        "/inventory/orders",
        json={"name": "iTL612R Pro lens 25mm", "qty": 1, "est_unit_cost": 92000},
    )
    assert resp.status_code == 201, resp.text
    order = resp.json()
    assert order["status"] == "planned"

    listed = client.get("/inventory/orders").json()
    assert len(listed) == 1

    resp = client.patch(f"/inventory/orders/{order['id']}", json={"status": "ordered"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ordered"

    assert client.delete(f"/inventory/orders/{order['id']}").status_code == 204
    assert client.get("/inventory/orders").json() == []


def test_order_linked_name_defaults_from_component(client):
    comp = _make_component(client)
    resp = client.post("/inventory/orders", json={"component_id": comp["id"], "qty": 2})
    assert resp.status_code == 201
    assert resp.json()["name"] == comp["name"]


def test_order_requires_name_or_component(client):
    assert client.post("/inventory/orders", json={"qty": 1}).status_code == 400


def test_order_rejects_bad_status(client):
    resp = client.post("/inventory/orders", json={"name": "X", "status": "shipped"})
    assert resp.status_code == 400


def test_order_received_increments_stock_once(client):
    comp = _make_component(client, qty_total=8)
    order = client.post(
        "/inventory/orders", json={"component_id": comp["id"], "qty": 4}
    ).json()

    resp = client.patch(f"/inventory/orders/{order['id']}", json={"status": "received"})
    assert resp.status_code == 200
    assert client.get("/inventory/components").json()[0]["qty_total"] == 12

    # repeating the PATCH must not double-count
    resp = client.patch(f"/inventory/orders/{order['id']}", json={"status": "received"})
    assert resp.status_code == 200
    assert client.get("/inventory/components").json()[0]["qty_total"] == 12


# ── summary ───────────────────────────────────────────────────────────────────

def test_inventory_summary(client):
    comp = _make_component(client, qty_total=2, unit_cost=100.0)   # value 200
    depleted = _make_component(client, name="Spare ESC", qty_total=1, unit_cost=50.0)
    proto = _make_prototype(client)
    _assign(client, depleted["id"], proto["id"], qty=1)            # depleted -> low stock
    client.post("/inventory/orders", json={"name": "Props", "qty": 10})

    summary = client.get("/inventory/summary").json()
    assert summary["component_count"] == 2
    assert summary["prototype_count"] == 1
    assert summary["open_order_count"] == 1
    assert summary["stock_value"] == 250.0
    assert [c["id"] for c in summary["low_stock"]] == [depleted["id"]]
    assert comp["id"] not in [c["id"] for c in summary["low_stock"]]
