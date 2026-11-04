"""FastAPI shell for the Axalon Solar Inspection Platform.

Lifespan, CORS, auth/timeout middleware, router wiring. Endpoints live in
axalon.api.routers.*; shared helpers in axalon.api.deps.
Run: uvicorn axalon.api.app:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from axalon.api.deps import (
    logger, get_session, DbJob, _run_alembic_migrations, _cleanup_old_results,
)
from axalon.api.agents_router import router as agents_router
from axalon.api.routers import (
    alerts, analytics, auth, corrections, diff, faults, health, inspection, inventory,
    map, missions, ortho, ortho_generate, park, park_layout, projects, results,
    settings, share_links, track, users, work_orders,
)
from axalon.api.support.odm_jobs import resume_odm_jobs
from drone.relay.server import create_app as create_relay_app
from axalon.core.observability import init_sentry
from axalon.api.support.principal import (
    ALWAYS_PUBLIC_PATHS, NOT_AUTHENTICATED, SYSTEM_PRINCIPAL, USERS_PUBLIC_PATHS,
    access_policy, apikey_matches, request_token, resolve_users_principal,
)
from axalon.core.auth import MODE_APIKEY, MODE_USERS, auth_mode, ensure_bootstrap_admin
from axalon.db.models import ROLE_ADMIN, ROLE_OPERATOR


@asynccontextmanager
async def lifespan(_app: FastAPI):
    _run_alembic_migrations()
    _requeue_stale_jobs()
    _bootstrap_admin()
    try:
        resume_odm_jobs()
    except Exception:
        logger.exception("Startup: could not resume orthomosaic generation jobs")
    try:
        _cleanup_old_results()
    except Exception:
        # Same reasoning as _requeue_stale_jobs: housekeeping must never be the
        # reason the API refuses to start.
        logger.exception("Startup: results cleanup failed")
    yield


def _bootstrap_admin() -> None:
    """Create the first admin from env in users mode. Never raises, for the same
    reason as _requeue_stale_jobs: a DB hiccup must not stop the API booting."""
    if auth_mode() != MODE_USERS:
        return
    try:
        session = get_session()
    except Exception:
        logger.exception("Startup: database unreachable — bootstrap admin skipped")
        return
    try:
        ensure_bootstrap_admin(session)
    except Exception:
        session.rollback()
        logger.exception("Startup: bootstrap admin failed")
    finally:
        session.close()


def _requeue_stale_jobs() -> None:
    """Re-queue jobs left 'running' by a previous process.

    Never raises. An unreachable database used to propagate out of lifespan and
    abort startup, so a single stale connection string took the whole API down
    and every request returned 503 with no way to see why. Logging and carrying
    on keeps the app serving, and /health reports db:"error" so the cause is
    visible instead of opaque.
    """
    try:
        session = get_session()
    except Exception:
        logger.exception("Startup: database unreachable — continuing without re-queue")
        return
    try:
        stale = session.query(DbJob).filter(DbJob.state == "running").all()
        for job in stale:
            job.state = "queued"
            job.message = "Re-queued after API restart"
        session.commit()
        if stale:
            logger.info("Re-queued %s interrupted job(s)", len(stale))
    except Exception:
        session.rollback()
        logger.exception("Startup: could not re-queue interrupted jobs")
    finally:
        session.close()


# Before FastAPI() so the SDK's FastAPI/Starlette integrations hook in. No-op
# without SENTRY_DSN (local dev, tests).
init_sentry()

app = FastAPI(
    title="Axalon Solar Inspection API",
    version="1.0.0",
    lifespan=lifespan,
    description=(
        "Solar anomaly detection and panel localization for drone-captured "
        "thermal IR + RGB imagery. Model: ml/checkpoints/best.pt (GET /health "
        "reports its architecture)."
    ),
)

# ── CORS ──────────────────────────────────────────────────────────────────────
_DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001",
    "http://127.0.0.1:3001", "http://localhost:8501", "http://127.0.0.1:8501",
    "https://axalonsystems.com", "https://www.axalonsystems.com",
]
_CORS_ORIGINS = [
    o.strip() for o in os.getenv("AXALON_CORS_ORIGINS", "").split(",") if o.strip()
] or _DEFAULT_CORS_ORIGINS

# Any loopback port counts as a dev origin. Without this, running the Next.js dev
# server on anything but :3000/:3001 (port already taken, parallel worktree, a
# second UI) fails every request with an opaque CORS error instead of a 4xx.
# Safe: allow_credentials is False and auth is a Bearer header, never a cookie,
# so a cross-origin page gains nothing it could not already request directly.
_CORS_ORIGIN_REGEX = r"https?://(localhost|127\.0\.0\.1)(:\d+)?"

# Agents spawn local processes — admin-only whenever accounts are enabled.
app.include_router(
    agents_router,
    dependencies=[Depends(access_policy(allow_share=False, read_role=ROLE_ADMIN, write_role=ROLE_ADMIN))],
)
app.add_middleware(
    CORSMiddleware, allow_origins=_CORS_ORIGINS,
    allow_origin_regex=_CORS_ORIGIN_REGEX, allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"], allow_headers=["*"],
)

_REQUEST_TIMEOUT_S = 120


@app.middleware("http")
async def auth_middleware(request, call_next):
    """Authenticate per AXALON_AUTH_MODE and attach `request.state.principal`.

    off    → everyone is SYSTEM_PRINCIPAL (keyless, today's production).
    apikey → the shared AXALON_API_KEY, as before; SYSTEM_PRINCIPAL once matched.
    users  → session token (header or ?api_key=) or ?share= link; role and
             project scope are then enforced by router policies and scope.py.
    """
    if request.method == "OPTIONS":
        return await call_next(request)
    path = request.url.path
    if path == RELAY_PREFIX or path.startswith(RELAY_PREFIX + "/"):
        # The mounted drone relay authenticates drones and operators with its own
        # tokens (DRONE_TOKENS / OPS_TOKEN); API keys and user sessions don't apply.
        return await call_next(request)
    mode = auth_mode()

    if mode == MODE_USERS:
        principal = await run_in_threadpool(
            resolve_users_principal,
            request_token(request),
            request.query_params.get("share", "").strip(),
        )
        if principal is None and path not in USERS_PUBLIC_PATHS:
            return JSONResponse({"detail": NOT_AUTHENTICATED}, status_code=401)
        request.state.principal = principal
        return await call_next(request)

    request.state.principal = SYSTEM_PRINCIPAL
    if mode == MODE_APIKEY and path not in ALWAYS_PUBLIC_PATHS and not apikey_matches(request):
        return JSONResponse({"detail": "Invalid or missing API key"}, status_code=401)
    return await call_next(request)


@app.middleware("http")
async def timeout_middleware(request, call_next):
    """Return 504 if a request exceeds _REQUEST_TIMEOUT_S (after auth → outermost layer)."""
    import asyncio
    try:
        return await asyncio.wait_for(call_next(request), timeout=_REQUEST_TIMEOUT_S)
    except asyncio.TimeoutError:
        return JSONResponse({"detail": "Request timeout"}, status_code=504)


# ── Domain routers ──────────────────────────────────────────────────────────────
# Role policy lives here, once per router (reads: viewer+, writes: operator+ unless
# stated). Policies are no-ops in off/apikey modes. `allow_share` admits read-only
# share-link visitors, and only routers serving project-scoped data do.
_PROJECT_DATA = access_policy(allow_share=True)
_INTERNAL = access_policy(allow_share=False)
_ADMIN_ONLY = access_policy(allow_share=False, read_role=ROLE_ADMIN, write_role=ROLE_ADMIN)

_ROUTER_POLICIES = (   # original registration order preserved
    (analytics, _PROJECT_DATA),
    (corrections, _PROJECT_DATA),
    (diff, _PROJECT_DATA),
    (faults, _PROJECT_DATA),
    (health, None),
    (inspection, _PROJECT_DATA),
    (inventory, _INTERNAL),
    (map, _PROJECT_DATA),
    (missions, _PROJECT_DATA),
    (ortho, _PROJECT_DATA),
    (park, _PROJECT_DATA),
    (projects, access_policy(allow_share=True, write_role=ROLE_ADMIN)),
    (results, _PROJECT_DATA),
    (settings, access_policy(allow_share=False, write_role=ROLE_ADMIN)),
    (track, _INTERNAL),
    (auth, None),                     # each endpoint handles its own access
    (share_links, access_policy(allow_share=False, read_role=ROLE_OPERATOR)),
    (users, _ADMIN_ONLY),
    # Added after the auth work. None admit share-link visitors; the park-data ones
    # also scope each endpoint to parks the caller can see.
    (alerts, access_policy(allow_share=False, write_role=ROLE_ADMIN)),
    (work_orders, _INTERNAL),
    (ortho_generate, _INTERNAL),
    (park_layout, _INTERNAL),
)
for _module, _policy in _ROUTER_POLICIES:
    app.include_router(_module.router, dependencies=[Depends(_policy)] if _policy else [])

# ── Drone relay ──────────────────────────────────────────────────────────────
# Served from this app because new Hugging Face Docker Spaces need a paid plan:
# the relay rides the API Space's container and TLS at wss://<api host>/relay/ws/…
# Relay state (connections, control lock) is in-process, so this assumes one
# worker, which the Space runs.
RELAY_PREFIX = "/relay"
app.mount(RELAY_PREFIX, create_relay_app(cors=False))
