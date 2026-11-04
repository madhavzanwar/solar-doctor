# Inventory & Prototype Tracking — Design

**Date:** 2026-06-12
**Status:** Approved (user request: track current inventory, prototypes, which drone contains which components, and plan future component orders)

## Problem

Hardware inventory (motors, ESCs, flight controllers, cameras, batteries, …) and
prototype drone builds are tracked nowhere. We need a single `/platform` page that
answers: what do we have in stock, which build is each part installed in, and what
do we need to order next.

## Entities (new tables, migration `0005`)

### `inventory_components`
One row per part type. `qty_total` is everything owned; availability is derived:
`qty_available = qty_total − Σ assignment.qty`.

| column | type | notes |
|---|---|---|
| id | int PK | |
| name | str NOT NULL | e.g. "T-Motor F90 1300KV" |
| category | str | flight-controller, motor, esc, battery, propeller, frame, camera, sensor, companion-computer, radio, gps, wiring, other |
| part_number | str null | |
| vendor | str null | |
| link | str null | product URL |
| unit_cost | float null | |
| currency | str | default "INR" |
| qty_total | int | default 0, ≥ 0 |
| specs | Text null | free JSON/text |
| notes | Text null | |
| created_at / updated_at | DateTime | |

### `prototypes`
A drone build (or any hardware prototype).

| column | type | notes |
|---|---|---|
| id | int PK | |
| name | str NOT NULL | e.g. "Axalon Mk1 — thermal quad" |
| status | str | planning, building, active, retired (default planning) |
| description / notes | Text null | |
| created_at / updated_at | DateTime | |

### `component_assignments`
Which components live in which prototype (the BOM).

| column | type | notes |
|---|---|---|
| id | int PK | |
| component_id | FK inventory_components NOT NULL, indexed | |
| prototype_id | FK prototypes NOT NULL, indexed | |
| qty | int | default 1, ≥ 1, ≤ component availability |
| notes | Text null | |
| created_at | DateTime | |

### `component_orders`
Future purchases — planning queue.

| column | type | notes |
|---|---|---|
| id | int PK | |
| component_id | FK null | link to an existing part, or null for a brand-new item |
| name | str NOT NULL | item name (defaults from component when linked) |
| qty | int | default 1, ≥ 1 |
| est_unit_cost | float null | |
| vendor / link | str null | |
| status | str | planned, ordered, received, cancelled (default planned) |
| needed_by | str null | ISO date string |
| notes | Text null | |
| created_at / updated_at | DateTime | |

**Rule:** transition to `received` on an order linked to a component increments
that component's `qty_total` by the order qty (stock-in), exactly once.

## API (in `platform/api/app.py`, same auth middleware)

- `GET  /inventory/summary` — counts, stock value, low-stock (< 1 available), open orders
- `GET  /inventory/components` / `POST` / `PATCH /{id}` / `DELETE /{id}`
  - serialized rows carry derived `qty_assigned` + `qty_available`
  - DELETE returns **409** while assignments exist
- `GET  /inventory/prototypes` (embeds assignments with component name/category) / `POST` / `PATCH /{id}` / `DELETE /{id}` (cascades its assignments → frees stock)
- `POST /inventory/assignments` / `PATCH /{id}` / `DELETE /{id}`
  - 400 when qty exceeds availability (PATCH excludes its own current qty)
- `GET  /inventory/orders` / `POST` / `PATCH /{id}` / `DELETE /{id}`

Validation: names non-empty (≤200 chars), quantities/integers ≥ bounds above,
404 on missing FKs, JSON error envelope via HTTPException like the rest of app.py.

## Frontend

- New rail tab **Inventory** (`Boxes` icon) in `app/platform/page.tsx`
- `components/Platform/InventoryTab.tsx` — three sections:
  1. **Components** — table grouped/filterable by category, stock badges (available/assigned), add/edit/delete
  2. **Prototypes** — card per build with status pill + its BOM (assign parts from stock, unassign)
  3. **Order planning** — planned purchases with status flow planned → ordered → received, estimated cost totals
- `lib/api.ts` — types + `api.inventory*` methods
- `lib/inventory.ts` — pure helpers (stock value, low-stock filter, order cost totals) — vitest covered

## Tests

- `tests/backend/test_inventory.py` — model persistence, CRUD, availability enforcement,
  delete-while-assigned 409, order receive stock-in (idempotent w.r.t. repeated PATCH), summary
- `tests/unit/inventory.test.ts` — pure helper coverage

## Out of scope (later)

- Photos/attachments per component, barcode/QR, multi-currency conversion,
  supplier lead-time tracking, auto-reorder thresholds per component.
