---
name: platform-api
description: Use when adding or modifying FastAPI endpoints in platform/api/app.py — request/response shapes, Bearer auth, CORS, error handling, and the platform/ module-shadow gotcha. Read before changing the backend surface.
---

# Platform API (FastAPI)

The backend lives in `platform/api/app.py` (package name `axalon`, so the import path is `axalon.api.app:app`). It serves the `/platform` UI and is deployed to a Hugging Face Space (see `cloud-deployment`).

## Run locally
```bash
# platform/ shadows the stdlib `platform` module — ALWAYS use PYTHONSAFEPATH=1,
# ideally with cwd /tmp, or SQLAlchemy/uvicorn crash on import.
PYTHONSAFEPATH=1 uvicorn axalon.api.app:app --host 0.0.0.0 --port 8000
# or ./run.sh all  (API + Next.js platform UI)
```

## Auth — `AXALON_AUTH_MODE` (off | apikey | users)
- `auth_middleware` (app.py) resolves a `Principal` per request: `off`/`apikey` → unrestricted
  `SYSTEM_PRINCIPAL`; `users` → session token (Bearer or `?api_key=`) or `?share=` link.
- Role policy is applied **per router** in `app.py` (`_ROUTER_POLICIES`, `access_policy(...)`):
  reads viewer+, writes operator+; users/agents admin-only; projects & settings writes admin.
  Don't re-check roles inside endpoints.
- Endpoints returning project data take `principal: Principal = Depends(current_principal)` and
  scope with `axalon.api.support.scope` (`scope_parks`, `ensure_park_visible`, `ensure_job_visible`, …).
  Out-of-scope → 404, never 403. Helpers are no-ops for unrestricted principals.
- New router? Add it to `_ROUTER_POLICIES` with the right policy; `allow_share=True` only if it
  serves project-scoped data and every endpoint scopes its queries.
- Accounts/sessions/share links live in `axalon.core.auth`; frontend `AuthGate.tsx` asks
  `GET /auth/mode` and shows email/password login in users mode (token stored like the key).

## Endpoint groups (current)
- `GET /health` — model + db status (public).
- Jobs / inference, parks, inspections, diff.
- Missions: `POST/GET/DELETE /missions` (drone plans — see `mission-planner`).
- Reports: `GET /report/{jobId}?format=…` (see `reporting`).

## Adding an endpoint
1. Use the response envelope conventions already in `app.py`; raise `HTTPException` for errors (never swallow).
2. Validate input at the boundary (Pydantic / explicit checks).
3. Register the router in `_ROUTER_POLICIES` and scope project data (see Auth).
4. DB access via `get_session()` (see `database` skill) — always `session.close()` in `finally`.
5. Add a test under `tests/`; run `PYTHONSAFEPATH=1 python -m pytest`.

## Gotchas
- CORS already allows `axalonsystems.com` — extend the list in `app.py` if adding origins.
- `NEXT_PUBLIC_AXALON_API_URL` (Vercel) must point at the live backend; it's baked at build time.
- Don't cross-import website code. Detection logic comes from `platform/core` + `ml.src.utils`.
