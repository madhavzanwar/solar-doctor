# drone/relay/turn.py
"""Short-lived TURN credentials for coturn `use-auth-secret` mode.

The relay mints time-limited credentials so browsers/agents can use the TURN
relay without coturn needing a user database. STUN is always offered (when a host
is set); TURN is added only when TURN_SECRET is configured. With no TURN_HOST,
public STUN is returned so peers can still gather server-reflexive candidates.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time

PUBLIC_STUN_URL = "stun:stun.l.google.com:19302"


def make_turn_credentials(secret: str, ttl_s: int, name: str) -> tuple[str, str]:
    expiry = int(time.time()) + ttl_s
    username = f"{expiry}:{name}"
    digest = hmac.new(secret.encode(), username.encode(), hashlib.sha1).digest()
    password = base64.b64encode(digest).decode()
    return username, password


def ice_servers(name: str, ttl_s: int = 3600) -> list[dict]:
    host = os.getenv("TURN_HOST", "")
    secret = os.getenv("TURN_SECRET", "")
    if not host:
        # No coturn reachable (e.g. relay hosted on a Hugging Face Space). An empty
        # list would leave WebRTC with host candidates only, so offer public STUN.
        return [{"urls": PUBLIC_STUN_URL}]
    servers: list[dict] = [{"urls": f"stun:{host}:3478"}]
    if secret:
        user, pwd = make_turn_credentials(secret, ttl_s, name)
        servers.append({
            "urls": [f"turn:{host}:3478?transport=udp", f"turn:{host}:3478?transport=tcp"],
            "username": user,
            "credential": pwd,
        })
    return servers
