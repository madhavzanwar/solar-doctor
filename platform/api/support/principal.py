"""Who is calling, and may they use this router?

`auth_middleware` (app.py) attaches a `Principal` to every request. Routers get
their role policy from `access_policy(...)`, applied once at `include_router`
time, so endpoint bodies never repeat role checks. Endpoints that return
project data ask for the principal via `Depends(current_principal)` and scope
their queries with `axalon.api.support.scope`.

In `off` and `apikey` modes every request carries SYSTEM_PRINCIPAL — admin,
unrestricted — so all policy and scoping code is a no-op there.
"""
from __future__ import annotations

import hmac
import os
from dataclasses import dataclass
from typing import Callable

from fastapi import HTTPException, Request

from axalon.core.auth import (
    MODE_APIKEY, MODE_USERS, auth_mode, project_ids_for, resolve_session, resolve_share_link,
)
from axalon.db.models import ROLE_ADMIN, ROLE_OPERATOR, ROLE_VIEWER
from axalon.db.session import get_session

KIND_SYSTEM = "system"
KIND_USER = "user"
KIND_SHARE = "share"

# Reachable without credentials. /auth/mode is public in every mode because the
# console must learn which login UI to show before it has any credentials.
ALWAYS_PUBLIC_PATHS = frozenset({"/health", "/track/login", "/auth/mode"})
USERS_PUBLIC_PATHS = ALWAYS_PUBLIC_PATHS | {"/auth/login"}

_ROLE_RANK = {ROLE_VIEWER: 0, ROLE_OPERATOR: 1, ROLE_ADMIN: 2}
_READ_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

NOT_AUTHENTICATED = "Not authenticated"
FORBIDDEN = "Insufficient permissions"


@dataclass(frozen=True)
class Principal:
    kind: str
    role: str
    # None = unrestricted (admins, off/apikey modes); otherwise visible project ids.
    project_ids: frozenset[int] | None = None
    user_id: int | None = None
    email: str | None = None
    share_link_id: int | None = None

    @property
    def is_restricted(self) -> bool:
        return self.project_ids is not None

    def can_see_project(self, project_id: int | None) -> bool:
        if self.project_ids is None:
            return True
        return project_id is not None and project_id in self.project_ids

    def has_role(self, role: str) -> bool:
        return _ROLE_RANK.get(self.role, -1) >= _ROLE_RANK[role]


SYSTEM_PRINCIPAL = Principal(kind=KIND_SYSTEM, role=ROLE_ADMIN)


# ── resolution (middleware) ──────────────────────────────────────────────────

def bearer_token(request: Request) -> str:
    scheme, _, credential = request.headers.get("authorization", "").partition(" ")
    return credential.strip() if scheme.lower() == "bearer" else ""


def request_token(request: Request) -> str:
    """Session token from the Authorization header, or `?api_key=` for URLs the
    browser loads itself (<img>, downloads) where headers cannot be set."""
    return bearer_token(request) or request.query_params.get("api_key", "").strip()


def apikey_matches(request: Request) -> bool:
    expected = os.environ.get("AXALON_API_KEY", "").strip()
    if not expected:
        return False
    supplied = request.query_params.get("api_key", "")
    header_ok = hmac.compare_digest(
        request.headers.get("authorization", "").encode(), f"Bearer {expected}".encode()
    )
    return header_ok or hmac.compare_digest(supplied.encode(), expected.encode())


def resolve_users_principal(token: str, share_token: str) -> Principal | None:
    """Look up a session token, then a share token. Blocking DB I/O."""
    session = get_session()
    try:
        user = resolve_session(session, token) if token else None
        if user is not None:
            project_ids = None if user.role == ROLE_ADMIN else frozenset(project_ids_for(session, user.id))
            return Principal(
                kind=KIND_USER, role=user.role, project_ids=project_ids,
                user_id=user.id, email=user.email,
            )
        link = resolve_share_link(session, share_token) if share_token else None
        if link is not None:
            return Principal(
                kind=KIND_SHARE, role=ROLE_VIEWER,
                project_ids=frozenset({link.project_id}), share_link_id=link.id,
            )
        return None
    finally:
        session.close()


# ── dependencies (routers) ───────────────────────────────────────────────────

def current_principal(request: Request) -> Principal:
    """The caller. Fails closed: users mode with no resolved principal is 401."""
    principal = getattr(request.state, "principal", None)
    if principal is not None:
        return principal
    if auth_mode() == MODE_USERS:
        raise HTTPException(status_code=401, detail=NOT_AUTHENTICATED)
    return SYSTEM_PRINCIPAL


def access_policy(
    *, allow_share: bool, read_role: str = ROLE_VIEWER, write_role: str = ROLE_OPERATOR,
) -> Callable[[Request], None]:
    """Router-level guard: reads need `read_role`, anything else `write_role`.

    Share-link principals are only admitted to routers that serve project data.
    """
    def _guard(request: Request) -> None:
        if request.url.path in USERS_PUBLIC_PATHS:
            return
        principal = current_principal(request)
        if principal.kind == KIND_SYSTEM:
            return
        if principal.kind == KIND_SHARE and not allow_share:
            raise HTTPException(status_code=403, detail=FORBIDDEN)
        needed = read_role if request.method in _READ_METHODS else write_role
        if not principal.has_role(needed):
            raise HTTPException(status_code=403, detail=FORBIDDEN)

    return _guard


__all__ = [
    "ALWAYS_PUBLIC_PATHS", "FORBIDDEN", "KIND_SHARE", "KIND_SYSTEM", "KIND_USER",
    "MODE_APIKEY", "MODE_USERS", "NOT_AUTHENTICATED", "Principal", "SYSTEM_PRINCIPAL",
    "USERS_PUBLIC_PATHS", "access_policy", "apikey_matches", "bearer_token",
    "current_principal", "request_token", "resolve_users_principal",
]
