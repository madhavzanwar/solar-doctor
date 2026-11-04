# drone/relay/auth.py
"""Authentication for the relay's two client kinds.

Phase 1 uses simple shared secrets from env:
- drones authenticate with a per-drone token (DRONE_TOKENS)
- operators authenticate with one shared OPS_TOKEN (replaced by the platform
  session/JWT in a later phase)

Uses hmac.compare_digest to avoid timing leaks.
"""
from __future__ import annotations

import hmac

from drone.relay import config


class AuthError(Exception):
    pass


def verify_drone_token(drone_id: str, token: str) -> str:
    expected = config.drone_tokens().get(drone_id)
    if expected is None or not hmac.compare_digest(expected, token):
        raise AuthError("invalid drone credentials")
    return drone_id


def verify_operator_token(token: str) -> bool:
    expected = config.ops_token()
    if not expected or not hmac.compare_digest(expected, token):
        raise AuthError("invalid operator credentials")
    return True
