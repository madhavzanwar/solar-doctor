# Plan 02 — Pydantic Request/Response Schemas
**Priority:** P0 | **Effort:** Medium
**Goal:** Replace all `dict` payloads with typed Pydantic models for validation, documentation, and safety.

---

## Why

Every mutating endpoint currently accepts a raw `dict` payload (e.g., `payload: dict`). This means:
- No automatic validation — bad data reaches the DB
- No OpenAPI documentation for request bodies
- No IDE autocomplete or type checking

---

## Target Structure

```
platform/api/
└── schemas/
    ├── __init__.py
    ├── inspection.py   ← InspectRequest, BatchRequest, JobStatus, InspectionResult
    ├── park.py         ← ParkUpdate, ParkSummary, GridResponse, TrendResponse
    ├── corrections.py  ← CorrectionCreate, CorrectionUpdate, CorrectionOut
    ├── missions.py     ← MissionCreate, MissionUpdate, MissionOut
    ├── inventory.py    ← ComponentCreate, ComponentUpdate, PrototypeCreate, OrderCreate, etc.
    ├── projects.py     ← ProjectCreate, ProjectUpdate, ProjectOut, SiteOut
    ├── analytics.py    ← OverviewResponse
    └── track.py        ← NoteCreate, NoteUpdate, NoteOut, FileOut
```

---

## Pydantic Model Patterns

Use `model_config = ConfigDict(extra="forbid")` to block unknown fields.

```python
# platform/api/schemas/inventory.py
from pydantic import BaseModel, ConfigDict, Field
from typing import Literal

COMPONENT_CATEGORIES = ("frame", "cell", "inverter", "cable", "connector", "other")

class ComponentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=200)
    category: Literal["frame", "cell", "inverter", "cable", "connector", "other"]
    quantity: int = Field(0, ge=0)
    unit: str = Field("pcs", max_length=20)
    notes: str | None = None

class ComponentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(None, min_length=1, max_length=200)
    category: Literal["frame", "cell", "inverter", "cable", "connector", "other"] | None = None
    quantity: int | None = Field(None, ge=0)
    unit: str | None = Field(None, max_length=20)
    notes: str | None = None

class ComponentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    category: str
    quantity: int
    unit: str
    notes: str | None
    assigned: int
```

---

## Steps

### Step 1 — Create `platform/api/schemas/` package

Create `__init__.py` (empty) and one schema file per domain.

### Step 2 — Write schemas for each domain

Work through each endpoint group. For each `payload: dict` endpoint, create:
- A `*Create` schema for POST body
- A `*Update` schema for PATCH body (all fields optional)
- A `*Out` schema for the response

Key schemas to create first (most impactful):

**Inventory (app.py:2041–2424):**
```
ComponentCreate, ComponentUpdate, ComponentOut
PrototypeCreate, PrototypeUpdate, PrototypeOut
AssignmentCreate, AssignmentUpdate, AssignmentOut
OrderCreate, OrderUpdate, OrderOut
```

**Projects (app.py:2459–2556):**
```
ProjectCreate, ProjectUpdate, ProjectOut
```

**Track (app.py:2695–2903):**
```
NoteCreate, NoteUpdate, NoteOut
LoginRequest, PasswordSetRequest
```

**Park (app.py:2558–2590):**
```
ParkUpdate
```

### Step 3 — Update routers to use schemas

Replace `payload: dict` with the typed schema:

```python
# Before
@router.post("/inventory/components", status_code=201)
def create_inventory_component(payload: dict):
    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(422, "name required")
    ...

# After
@router.post("/inventory/components", status_code=201, response_model=ComponentOut)
def create_inventory_component(payload: ComponentCreate):
    # payload.name is already validated, stripped by Pydantic
    ...
```

### Step 4 — Remove manual validation helpers

After schemas are in place, these helpers in app.py become redundant and should be deleted:
- `_clean_name()` (app.py:2023)
- `_non_negative_int()` (app.py:2030)
- Manual `if not name: raise HTTPException(422)` checks

### Step 5 — Add `response_model=` to all GET endpoints

```python
@router.get("/inventory/components", response_model=list[ComponentOut])
def list_inventory_components():
    ...
```

---

## Done When

- [ ] No endpoint accepts `payload: dict` (except file upload endpoints which use `Form`)
- [ ] All POST/PATCH endpoints have a typed request schema
- [ ] All GET endpoints have `response_model=` set
- [ ] `python3 -m pytest tests/backend/ -ra` still passes
- [ ] `GET /openapi.json` shows request body schemas (not empty)
