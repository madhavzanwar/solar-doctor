"""auth router — mode discovery, login, logout, current principal (users mode)."""
from __future__ import annotations

from fastapi import APIRouter
from axalon.api.deps import *  # noqa: F401,F403
from axalon.api.schemas import UserLogin
from axalon.api.serializers import _serialize_user
from axalon.api.support.principal import KIND_USER, request_token
from axalon.core.auth import (
    MODE_USERS, auth_mode, authenticate, create_session, login_limiter,
    normalize_email, project_ids_for, revoke_session,
)
from axalon.db.models import User

router = APIRouter(tags=["auth"])

# One message for unknown email, wrong password and disabled account alike.
_BAD_CREDENTIALS = "Invalid email or password"


@router.get("/auth/mode")
def get_auth_mode():
    """Public: tells the console which login UI to render."""
    return {"mode": auth_mode()}


@router.post("/auth/login")
def login(payload: UserLogin, request: Request):
    """Exchange email + password for an opaque session token."""
    if auth_mode() != MODE_USERS:
        raise HTTPException(status_code=404, detail="User accounts are not enabled")
    data = payload.model_dump(exclude_unset=True)
    email = normalize_email(data.get("email"))
    client_ip = request.client.host if request.client else "unknown"

    wait = login_limiter.retry_after(email, client_ip)
    if wait:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Try again later.",
            headers={"Retry-After": str(wait)},
        )

    session = get_session()
    try:
        user = authenticate(session, email, data.get("password"))
        if user is None:
            login_limiter.record_failure(email, client_ip)
            logger.info("Failed login attempt from %s", client_ip)
            raise HTTPException(status_code=401, detail=_BAD_CREDENTIALS)
        login_limiter.record_success(email)
        token, expires_at = create_session(session, user)
        return {
            "token": token,
            "expires_at": expires_at.isoformat(),
            "user": _serialize_user(user, project_ids_for(session, user.id)),
        }
    finally:
        session.close()


@router.post("/auth/logout", status_code=204)
def logout(request: Request, principal: Principal = Depends(current_principal)):
    """Revoke the caller's session. Share links and keyless modes have none."""
    if principal.kind == KIND_USER:
        session = get_session()
        try:
            revoke_session(session, request_token(request))
        finally:
            session.close()
    return Response(status_code=204)


@router.get("/auth/me")
def me(principal: Principal = Depends(current_principal)):
    """The caller as the console needs it: role, scope, and account if any."""
    body = {
        "mode": auth_mode(),
        "kind": principal.kind,
        "role": principal.role,
        "project_ids": sorted(principal.project_ids) if principal.is_restricted else None,
        "user": None,
    }
    if principal.kind == KIND_USER:
        session = get_session()
        try:
            user = session.query(User).filter(User.id == principal.user_id).first()
            if user is None:
                raise HTTPException(status_code=401, detail="Not authenticated")
            body["user"] = _serialize_user(user, project_ids_for(session, user.id))
        finally:
            session.close()
    return body
