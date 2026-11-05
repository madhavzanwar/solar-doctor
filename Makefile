# SolarDoctor — developer commands. Python 3.11+, Node 20+.
PY      ?= python3
VENV    ?= .venv
PIP     := $(VENV)/bin/pip
PYBIN   := $(VENV)/bin/python
export PYTHONSAFEPATH := 1

.PHONY: setup dev api web test test-backend test-frontend lint seed seed-pvdaq weights openapi clean

setup:            ## create venv, install backend (+ frontend if present)
	$(PY) -m venv $(VENV)
	$(PIP) install -q --upgrade pip
	$(PIP) install -q -r requirements_platform.txt -r ml/thermal/requirements.txt -r requirements-dev.txt -e .
	@if [ -f frontend/package.json ]; then cd frontend && npm ci; fi
	@[ -f .env ] || cp .env.example .env

api:              ## API on :8000
	cd /tmp && $(CURDIR)/$(PYBIN) -m uvicorn solardoctor.api.app:app --host 0.0.0.0 --port 8000 --reload --reload-dir $(CURDIR)/backend

web:              ## frontend on :3000
	cd frontend && npm run dev

dev:              ## API :8000 + frontend :3000
	@$(MAKE) -j2 api web

test: test-backend test-frontend

test-backend:
	$(PYBIN) -m pytest -q -p no:cacheprovider

test-frontend:
	@if [ -f frontend/package.json ]; then cd frontend && npm run lint && npx tsc --noEmit && npm test --if-present; fi

lint:
	$(PYBIN) -m ruff check backend tests scripts
	@if [ -f frontend/package.json ]; then cd frontend && npm run lint; fi

seed:             ## demo plants + 30 d simulated telemetry (labelled SIMULATED); idempotent
	$(PYBIN) scripts/seed.py

seed-pvdaq:       ## import real PVDAQ system 9068 as a 4th plant (source=PVDAQ; needs network)
	$(PYBIN) scripts/import_pvdaq.py --system-id 9068 --start 2024-06-01 --end 2024-06-30

weights:          ## download thermal weights from Hugging Face
	$(PYBIN) scripts/fetch_weights.py

openapi:          ## dump OpenAPI schema for the typed frontend client
	cd /tmp && $(CURDIR)/$(PYBIN) -c "import json;from solardoctor.api.app import app;print(json.dumps(app.openapi()))" > $(CURDIR)/frontend/openapi.json

clean:
	rm -rf $(VENV) .pytest_cache frontend/.next
