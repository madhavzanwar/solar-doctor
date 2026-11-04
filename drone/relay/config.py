# drone/relay/config.py
"""Env-driven relay configuration. No secrets in code (project security rule)."""
from __future__ import annotations

import os


def drone_tokens() -> dict[str, str]:
    """Parse DRONE_TOKENS='id1:tok1,id2:tok2' into {id: tok}."""
    raw = os.getenv("DRONE_TOKENS", "").strip()
    out: dict[str, str] = {}
    for pair in filter(None, (p.strip() for p in raw.split(","))):
        drone_id, _, token = pair.partition(":")
        if drone_id and token:
            out[drone_id] = token
    return out


def ops_token() -> str:
    return os.getenv("OPS_TOKEN", "")


def turn_host() -> str:
    return os.getenv("TURN_HOST", "")


def turn_secret() -> str:
    return os.getenv("TURN_SECRET", "")


DEFAULT_CORS_ORIGINS = ("https://axalonsystems.com", "https://www.axalonsystems.com")
# Proxies in front of the relay (HF Spaces, Cloudflare, Fly) drop connections that
# carry no data for ~60 s; keep the application-level ping comfortably below that.
DEFAULT_PING_INTERVAL_S = 25.0


def cors_origins() -> list[str]:
    """RELAY_CORS_ORIGINS='https://a.com,https://b.com'; defaults to the production site."""
    raw = os.getenv("RELAY_CORS_ORIGINS", "").strip()
    if not raw:
        return list(DEFAULT_CORS_ORIGINS)
    return [o.strip().rstrip("/") for o in raw.split(",") if o.strip()]


def ping_interval_s() -> float:
    """Seconds between relay->operator ping frames. <= 0 disables them."""
    raw = os.getenv("RELAY_PING_INTERVAL_S", "").strip()
    if not raw:
        return DEFAULT_PING_INTERVAL_S
    try:
        return float(raw)
    except ValueError:
        return DEFAULT_PING_INTERVAL_S
