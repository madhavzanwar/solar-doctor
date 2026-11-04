"""DB-backed app configuration — currently the /track workspace password.

Keeps secrets out of per-host environment variables: the password hash lives in
the Supabase `app_config` table. An `AXALON_TRACK_PASSWORD` env var, when set,
still wins (operator override / break-glass).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets

from axalon.db.models import AppConfig

TRACK_PASSWORD_KEY = "track_password_hash"
_PBKDF2_ITERATIONS = 200_000
_ALGO = "pbkdf2_sha256"


def hash_password(
    plaintext: str, *, salt: bytes | None = None, iterations: int = _PBKDF2_ITERATIONS,
) -> str:
    """Return a self-describing `pbkdf2_sha256$iters$salt$hash` string.

    The iteration count is embedded, so callers can raise it (user accounts use
    a higher cost) without breaking verification of existing hashes.
    """
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", plaintext.encode(), salt, iterations)
    return f"{_ALGO}${iterations}${salt.hex()}${digest.hex()}"


def verify_hash(plaintext: str, encoded: str) -> bool:
    """Constant-time check of a plaintext against a stored hash string."""
    try:
        algo, iters_s, salt_hex, hash_hex = encoded.split("$")
        if algo != _ALGO:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", plaintext.encode(), bytes.fromhex(salt_hex), int(iters_s)
        )
        return hmac.compare_digest(digest.hex(), hash_hex)
    except (ValueError, AttributeError):
        return False


def get_config(session, key: str) -> str | None:
    row = session.query(AppConfig).filter_by(key=key).first()
    return row.value if row else None


def set_config(session, key: str, value: str) -> None:
    row = session.query(AppConfig).filter_by(key=key).first()
    if row is None:
        session.add(AppConfig(key=key, value=value))
    else:
        row.value = value
    session.commit()


def delete_config(session, key: str) -> bool:
    """Remove a key; returns False when it was not set."""
    row = session.query(AppConfig).filter_by(key=key).first()
    if row is None:
        return False
    session.delete(row)
    session.commit()
    return True


def set_track_password(session, plaintext: str) -> None:
    set_config(session, TRACK_PASSWORD_KEY, hash_password(plaintext))


# Verification outcome — kept as plain strings so the API layer maps them to
# HTTP status codes without importing FastAPI here.
OK = "ok"
WRONG = "wrong"
UNCONFIGURED = "unconfigured"


def verify_track_password(session, supplied: str) -> str:
    """Check `supplied` against the env override first, then the DB hash.

    Returns OK / WRONG / UNCONFIGURED.
    """
    env_pw = os.environ.get("AXALON_TRACK_PASSWORD", "").strip()
    if env_pw:
        return OK if hmac.compare_digest(supplied.encode(), env_pw.encode()) else WRONG

    stored = get_config(session, TRACK_PASSWORD_KEY)
    if not stored:
        return UNCONFIGURED
    return OK if verify_hash(supplied, stored) else WRONG
