# SolarDoctor — developer commands. Python 3.11+, Node 20+.
PY      ?= python3
VENV    ?= .venv
PIP     := $(VENV)/bin/pip
PYBIN   := $(VENV)/bin/python
API_PORT ?= 8000
WEB_PORT ?= 3000
SEED_ARGS ?=
export PYTHONSAFEPATH := 1
# Load .env into the recipe's environment (the app itself does not read .env).
LOADENV := if [ -f .env ]; then set -a; . ./.env; set +a; fi;

.PHONY: setup dev api web test test-backend test-frontend lint seed seed-pvdaq weights openapi clean

setup:            ## create venv, install backend (+ frontend if present)
	$(PY) -m venv $(VENV)
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -r requirements_platform.txt -r ml/thermal/requirements.txt -r requirements-dev.txt -e .
	@if [ -f frontend/package.json ]; then cd frontend && npm ci; fi
	@[ -f .env ] || cp .env.example .env

api:              ## API on :8000 (API_PORT=...)
	@$(LOADENV) cd /tmp && $(CURDIR)/$(PYBIN) -m uvicorn solardoctor.api.app:app --host 0.0.0.0 --port $(API_PORT) --reload --reload-dir $(CURDIR)/backend

web:              ## frontend on :3000 (WEB_PORT=..., API_PORT=...)
	@$(LOADENV) cd frontend && NEXT_PUBLIC_API_URL=$${NEXT_PUBLIC_API_URL:-http://localhost:$(API_PORT)} npm run dev -- -p $(WEB_PORT)

dev:              ## API :8000 + frontend :3000, stopped together on Ctrl-C (make dev API_PORT=8010 WEB_PORT=3010)
	@API_PORT=$(API_PORT) WEB_PORT=$(WEB_PORT) PYBIN=$(CURDIR)/$(PYBIN) bash scripts/dev.sh

test: test-backend test-frontend

test-backend:
	$(PYBIN) -m pytest -q -p no:cacheprovider $$(bash scripts/pytest_deselect_args.sh)

test-frontend:
	@if [ -f frontend/package.json ]; then cd frontend && npm run lint && npx tsc --noEmit && npm test --if-present; fi

lint:
	$(PYBIN) -m ruff check backend tests scripts drone ml
	@if [ -f frontend/package.json ]; then cd frontend && npm run lint; fi

seed:             ## demo plants + 30 d simulated telemetry (labelled SIMULATED); idempotent; no network: make seed SEED_ARGS=--offline
	@# migrate first: seeding into an un-migrated DB makes the API's startup `alembic upgrade` fail ("duplicate column")
	@$(LOADENV) $(VENV)/bin/alembic upgrade head
	@$(LOADENV) $(PYBIN) scripts/seed.py $(SEED_ARGS)

seed-pvdaq:       ## import real PVDAQ system 9068 as a 4th plant (source=PVDAQ; needs network)
	@$(LOADENV) $(PYBIN) scripts/import_pvdaq.py --system-id 9068 --start 2024-06-01 --end 2024-06-30

weights:          ## download thermal weights from Hugging Face
	@$(LOADENV) $(PYBIN) scripts/fetch_weights.py

openapi:          ## dump OpenAPI schema for the typed frontend client
	cd /tmp && $(CURDIR)/$(PYBIN) -c "import json;from solardoctor.api.app import app;print(json.dumps(app.openapi()))" > $(CURDIR)/frontend/openapi.json

clean:
	rm -rf $(VENV) .pytest_cache frontend/.next
