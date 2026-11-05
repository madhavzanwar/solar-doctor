"""auth router — mode discovery, login, logout, current principal (users mode)."""
from __future__ import annotations

from datetime import datetime
from urllib.parse import parse_qs

from fastapi import APIRouter
from starlette.concurrency import run_in_threadpool
from solardoctor.api.deps import *  # noqa: F401,F403
from solardoctor.api.schemas import LogoutRequest, RefreshRequest, UserLogin, UserRegister
from solardoctor.api.serializers import _serialize_user
from solardoctor.api.support.principal import KIND_USER, request_token
from solardoctor.core.auth import (
    MODE_USERS, AuthValidationError, TokenPair, auth_mode, authenticate, create_token_pair,
    login_limiter, normalize_email, project_ids_for, register_limiter, register_user,
    registration_enabled, revoke_refresh_token, revoke_session, rotate_refresh_token,
)
from solardoctor.db.models import User

router = APIRouter(tags=["auth"])

# One message for unknown email, wrong password and disabled account alike.
_BAD_CREDENTIALS = "Invalid email or password"


@router.get("/auth/mode")
def get_auth_mode():
    """Public: tells the console which login UI to render."""
    return {"mode": auth_mode()}


def _require_users_mode() -> None:
    if auth_mode() != MODE_USERS:
        raise HTTPException(status_code=404, detail="User accounts are not enabled")


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _token_body(session, user: User, pair: TokenPair) -> dict:
    """Login/refresh response. `token` + `expires_at` + `user` are the original
    Axalon keys; `access_token`/`refresh_token`/`token_type` are the SolarPulse ones."""
    return {
        "token": pair.access_token,
        "access_token": pair.access_token,
        "refresh_token": pair.refresh_token,
        "token_type": "bearer",
        "expires_at": pair.expires_at.isoformat(),
        "expires_in": max(0, int((pair.expires_at - datetime.utcnow()).total_seconds())),
        "refresh_expires_at": pair.refresh_expires_at.isoformat(),
        "user": _serialize_user(user, project_ids_for(session, user.id)),
    }


def _do_login(email_raw, password, client_ip: str) -> dict:
    email = normalize_email(email_raw)
    wait = login_limiter.retry_after(email, client_ip)
    if wait:
        raise HTTPException(
            status_code=429,
            detail="Too many login attempts. Try again later.",
            headers={"Retry-After": str(wait)},
        )
    session = get_session()
    try:
        user = authenticate(session, email, password)
        if user is None:
            login_limiter.record_failure(email, client_ip)
            logger.info("Failed login attempt from %s", client_ip)
            raise HTTPException(status_code=401, detail=_BAD_CREDENTIALS)
        login_limiter.record_success(email)
        return _token_body(session, user, create_token_pair(session, user))
    finally:
        session.close()


@router.post("/auth/login")
def login(payload: UserLogin, request: Request):
    """Exchange email + password (JSON) for an access + refresh token pair."""
    _require_users_mode()
    data = payload.model_dump(exclude_unset=True)
    return _do_login(data.get("email"), data.get("password"), _client_ip(request))


@router.post("/auth/token")
async def login_form(request: Request):
    """OAuth2-password-style login the SolarPulse frontend uses:
    `application/x-www-form-urlencoded` with `username` (the email) and `password`."""
    _require_users_mode()
    form = parse_qs((await request.body()).decode("utf-8", "replace"))
    username = (form.get("username") or [""])[0]
    password = (form.get("password") or [""])[0]
    return await run_in_threadpool(_do_login, username, password, _client_ip(request))


@router.post("/auth/register", status_code=201)
def register(payload: UserRegister, request: Request):
    """Self-service signup. Always a `viewer` with no project access; an admin
    promotes/assigns later. Disable with SOLARDOCTOR_ALLOW_REGISTRATION=0."""
    _require_users_mode()
    if not registration_enabled():
        raise HTTPException(status_code=403, detail="Self-service registration is disabled")
    ip = _client_ip(request)
    wait = register_limiter.retry_after(ip)
    if wait:
        raise HTTPException(
            status_code=429, detail="Too many registration attempts. Try again later.",
            headers={"Retry-After": str(wait)},
        )
    register_limiter.record_failure(ip)  # counts every attempt
    data = payload.model_dump(exclude_unset=True)
    session = get_session()
    try:
        try:
            user = register_user(session, email=data.get("email"), password=data.get("password"))
        except AuthValidationError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except LookupError as exc:
            raise HTTPException(status_code=409, detail=str(exc))
        return _serialize_user(user, project_ids_for(session, user.id))
    finally:
        session.close()


@router.post("/auth/refresh")
def refresh(payload: RefreshRequest):
    """Rotate: a live refresh token is consumed and a new access + refresh pair returned."""
    _require_users_mode()
    token = payload.refresh_token if isinstance(payload.refresh_token, str) else ""
    session = get_session()
    try:
        result = rotate_refresh_token(session, token)
        if result is None:
            raise HTTPException(status_code=401, detail="Invalid or expired refresh token")
        user, pair = result
        return _token_body(session, user, pair)
    finally:
        session.close()


@router.post("/auth/logout", status_code=204)
def logout(request: Request, payload: LogoutRequest | None = None):
    """Revoke the bearer session and, if supplied, the refresh token. Idempotent:
    public in users mode so a client holding only a refresh token can sign out."""
    token = request_token(request)
    refresh_token = payload.refresh_token if payload and isinstance(payload.refresh_token, str) else ""
    if auth_mode() == MODE_USERS and (token or refresh_token):
        session = get_session()
        try:
            if token:
                revoke_session(session, token)
            revoke_refresh_token(session, refresh_token)
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
