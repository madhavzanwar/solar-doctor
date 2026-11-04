"""User accounts, sessions and share links — the domain half of AXALON_AUTH_MODE.

FastAPI-free on purpose: the API layer maps outcomes to HTTP, tests and the
bootstrap path call these directly.

Session design: an opaque random token (256 bits) handed to the client, with
only its SHA-256 stored server-side next to an expiry. Chosen over a signed
token (AXALON_AUTH_SECRET) because every request already reads the user row for
role/disabled/memberships, so revocation — logout, disabling a user, changing a
password — takes effect immediately, and there is no signing secret to
provision, rotate, or leak on the Hugging Face Space. SHA-256 (not a KDF) is
correct for tokens: they are high-entropy, so there is nothing to brute-force.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
from datetime import datetime, timedelta

from axalon.core.app_config import hash_password, verify_hash
from axalon.core.rate_limit import LoginRateLimiter, LoginThrottle
from axalon.db.models import (
    ROLE_ADMIN, USER_ROLES, ProjectMember, Project, ShareLink, User, UserSession,
)

logger = logging.getLogger("axalon.auth")

MODE_OFF = "off"
MODE_APIKEY = "apikey"
MODE_USERS = "users"
AUTH_MODES = (MODE_OFF, MODE_APIKEY, MODE_USERS)

# OWASP (2023) guidance for PBKDF2-HMAC-SHA256. The /track password keeps its
# own lower historical cost; verification reads the count from each hash.
USER_PBKDF2_ITERATIONS = 600_000

MIN_PASSWORD_LEN = 10
MAX_PASSWORD_LEN = 256          # bounds the KDF cost an attacker can request
SESSION_TTL_HOURS_DEFAULT = 12
SHARE_LINK_MAX_DAYS = 365

LOGIN_MAX_FAILURES_PER_EMAIL = 5
LOGIN_MAX_FAILURES_PER_IP = 20
LOGIN_WINDOW_S = 15 * 60

login_limiter = LoginThrottle(
    per_email=LoginRateLimiter(LOGIN_MAX_FAILURES_PER_EMAIL, LOGIN_WINDOW_S),
    per_ip=LoginRateLimiter(LOGIN_MAX_FAILURES_PER_IP, LOGIN_WINDOW_S),
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class AuthValidationError(ValueError):
    """Bad user-supplied account data; the message is safe to show."""


# ── mode ──────────────────────────────────────────────────────────────────────

def auth_mode() -> str:
    """Resolve AXALON_AUTH_MODE, read per call so tests and restarts see changes.

    Unset → legacy behaviour: `apikey` when AXALON_API_KEY is set, else `off`.
    An unrecognised value fails closed to `users` rather than silently opening
    the API because of a typo.
    """
    raw = os.environ.get("AXALON_AUTH_MODE", "").strip().lower()
    if not raw:
        return MODE_APIKEY if os.environ.get("AXALON_API_KEY", "").strip() else MODE_OFF
    if raw in AUTH_MODES:
        return raw
    logger.error("Unknown AXALON_AUTH_MODE=%r — failing closed to 'users'", raw)
    return MODE_USERS


# ── validation & hashing ─────────────────────────────────────────────────────

def normalize_email(raw: object) -> str:
    return str(raw or "").strip().lower()


def validate_email(raw: object) -> str:
    email = normalize_email(raw)
    if len(email) > 254 or not _EMAIL_RE.match(email):
        raise AuthValidationError("A valid email address is required")
    return email


def validate_password(raw: object) -> str:
    password = raw if isinstance(raw, str) else ""
    if not (MIN_PASSWORD_LEN <= len(password) <= MAX_PASSWORD_LEN):
        raise AuthValidationError(
            f"Password must be {MIN_PASSWORD_LEN}–{MAX_PASSWORD_LEN} characters"
        )
    return password


def validate_role(raw: object) -> str:
    role = str(raw or "").strip().lower()
    if role not in USER_ROLES:
        raise AuthValidationError(f"role must be one of {', '.join(USER_ROLES)}")
    return role


def hash_user_password(password: str) -> str:
    return hash_password(password, iterations=USER_PBKDF2_ITERATIONS)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _new_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, _token_hash(token)


# ── users ─────────────────────────────────────────────────────────────────────

def set_user_projects(session, user_id: int, project_ids) -> list[int]:
    """Replace a user's project memberships; unknown project ids are rejected."""
    wanted = sorted({int(pid) for pid in (project_ids or [])})
    if wanted:
        found = {pid for (pid,) in session.query(Project.id).filter(Project.id.in_(wanted))}
        missing = [pid for pid in wanted if pid not in found]
        if missing:
            raise AuthValidationError(f"Unknown project id(s): {missing}")
    session.query(ProjectMember).filter(ProjectMember.user_id == user_id).delete(
        synchronize_session=False
    )
    session.add_all(ProjectMember(user_id=user_id, project_id=pid) for pid in wanted)
    return wanted


def project_ids_for(session, user_id: int) -> list[int]:
    rows = session.query(ProjectMember.project_id).filter(ProjectMember.user_id == user_id)
    return sorted(pid for (pid,) in rows)


def create_user(session, *, email, password, role, project_ids=()) -> User:
    """Validate and insert a user. Raises AuthValidationError; LookupError on duplicate."""
    email = validate_email(email)
    password = validate_password(password)
    role = validate_role(role)
    if session.query(User.id).filter(User.email == email).first() is not None:
        raise LookupError("A user with that email already exists")
    user = User(email=email, password_hash=hash_user_password(password), role=role, disabled=False)
    session.add(user)
    session.flush()
    try:
        set_user_projects(session, user.id, project_ids)
    except AuthValidationError:
        session.rollback()
        raise
    session.commit()
    return user


def count_active_admins(session, exclude_user_id: int | None = None) -> int:
    q = session.query(User).filter(User.role == ROLE_ADMIN, User.disabled.is_(False))
    if exclude_user_id is not None:
        q = q.filter(User.id != exclude_user_id)
    return q.count()


def authenticate(session, email: object, password: object) -> User | None:
    """Return the enabled user for valid credentials, else None.

    Always runs one KDF verification — against a throwaway hash when the email
    is unknown — so response time does not reveal which accounts exist.
    """
    email = normalize_email(email)
    supplied = password if isinstance(password, str) else ""
    if len(supplied) > MAX_PASSWORD_LEN:
        supplied = ""
    user = session.query(User).filter(User.email == email).first() if email else None
    stored = user.password_hash if user is not None else _dummy_hash()
    ok = verify_hash(supplied, stored)
    if user is None or user.disabled or not ok:
        return None
    return user


_DUMMY_HASHES: dict[int, str] = {}


def _dummy_hash() -> str:
    iterations = USER_PBKDF2_ITERATIONS
    if iterations not in _DUMMY_HASHES:
        _DUMMY_HASHES[iterations] = hash_password(secrets.token_hex(16), iterations=iterations)
    return _DUMMY_HASHES[iterations]


# ── sessions ─────────────────────────────────────────────────────────────────

def _session_ttl() -> timedelta:
    try:
        hours = float(os.environ.get("AXALON_SESSION_TTL_HOURS", SESSION_TTL_HOURS_DEFAULT))
    except ValueError:
        hours = SESSION_TTL_HOURS_DEFAULT
    return timedelta(hours=min(max(hours, 0.25), 24 * 30))


def create_session(session, user: User) -> tuple[str, datetime]:
    token, digest = _new_token()
    expires_at = datetime.utcnow() + _session_ttl()
    session.add(UserSession(user_id=user.id, token_hash=digest, expires_at=expires_at))
    session.commit()
    return token, expires_at


def resolve_session(session, token: str) -> User | None:
    """Return the enabled user behind a live session token, else None."""
    if not token:
        return None
    # Lookup is by SHA-256 of the token, so index timing reveals nothing usable
    # about the token itself — no separate constant-time compare is needed.
    row = session.query(UserSession).filter(UserSession.token_hash == _token_hash(token)).first()
    if row is None:
        return None
    if row.expires_at <= datetime.utcnow():
        session.delete(row)
        session.commit()
        return None
    user = session.query(User).filter(User.id == row.user_id).first()
    if user is None or user.disabled:
        return None
    return user


def revoke_session(session, token: str) -> None:
    session.query(UserSession).filter(UserSession.token_hash == _token_hash(token)).delete(
        synchronize_session=False
    )
    session.commit()


def revoke_user_sessions(session, user_id: int) -> None:
    session.query(UserSession).filter(UserSession.user_id == user_id).delete(
        synchronize_session=False
    )


# ── share links ──────────────────────────────────────────────────────────────

def create_share_link(
    session, *, project_id: int, created_by: int | None, expires_in_days, label=None,
) -> tuple[ShareLink, str]:
    try:
        days = int(expires_in_days)
    except (TypeError, ValueError):
        raise AuthValidationError("expires_in_days must be a whole number")
    if not (1 <= days <= SHARE_LINK_MAX_DAYS):
        raise AuthValidationError(f"expires_in_days must be between 1 and {SHARE_LINK_MAX_DAYS}")
    token, digest = _new_token()
    link = ShareLink(
        token_hash=digest,
        project_id=project_id,
        label=(str(label).strip()[:200] or None) if label else None,
        created_by=created_by,
        expires_at=datetime.utcnow() + timedelta(days=days),
    )
    session.add(link)
    session.commit()
    return link, token


def resolve_share_link(session, token: str) -> ShareLink | None:
    """Return a live (unexpired, unrevoked) share link for `token`, else None."""
    if not token:
        return None
    link = session.query(ShareLink).filter(ShareLink.token_hash == _token_hash(token)).first()
    if link is None or link.revoked_at is not None or link.expires_at <= datetime.utcnow():
        return None
    return link


# ── bootstrap ────────────────────────────────────────────────────────────────

def ensure_bootstrap_admin(session) -> User | None:
    """Create the first admin from env vars when the users table is empty."""
    if session.query(User.id).first() is not None:
        return None
    email = os.environ.get("AXALON_BOOTSTRAP_ADMIN_EMAIL", "")
    password = os.environ.get("AXALON_BOOTSTRAP_ADMIN_PASSWORD", "")
    if not email or not password:
        logger.warning(
            "AXALON_AUTH_MODE=users but no users exist — set AXALON_BOOTSTRAP_ADMIN_EMAIL "
            "and AXALON_BOOTSTRAP_ADMIN_PASSWORD to create the first admin"
        )
        return None
    try:
        user = create_user(session, email=email, password=password, role=ROLE_ADMIN)
    except (AuthValidationError, LookupError) as exc:
        logger.error("Bootstrap admin not created: %s", exc)
        return None
    logger.info("Bootstrap admin created for %s", user.email)
    return user
