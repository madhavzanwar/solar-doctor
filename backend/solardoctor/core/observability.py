"""Sentry error monitoring and tracing for the API.

Enabled only when ``SENTRY_DSN`` is set, so local dev and tests send nothing.

Credentials in this system travel in query strings — ``?api_key=`` on <img> and
download URLs, ``?share=`` on share links, ``?token=`` on the drone relay.
Sentry's default scrubber filters dict keys (headers, extras) but leaves the raw
query string and URLs alone, so :func:`scrub_event` masks those values in the
request, breadcrumbs and spans before anything leaves the process.

Environment:
    SENTRY_DSN                  enables Sentry
    SENTRY_ENVIRONMENT          default "production"
    SENTRY_TRACES_SAMPLE_RATE   default 0.1 (1.0 traces every request and burns the free quota)
    SENTRY_PROFILE_SAMPLE_RATE  default 0 (profiling off)
    SENTRY_SEND_PII             default false: no client IPs / request bodies
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_TRACES_SAMPLE_RATE = 0.1
DEFAULT_PROFILE_SAMPLE_RATE = 0.0
FILTERED = "[Filtered]"

SENSITIVE_QUERY_KEYS = frozenset({"api_key", "token", "share", "access_token", "password", "secret"})

_QUERY_PARAM = re.compile(r"(^|[?&;])([^=&;#]+)=([^&;#]*)")


def scrub_query(query: str) -> str:
    """Mask the values of sensitive query parameters, keeping everything else."""
    if not query:
        return query

    def _mask(m: re.Match) -> str:
        sep, key, value = m.group(1), m.group(2), m.group(3)
        return f"{sep}{key}={FILTERED}" if key.lower() in SENSITIVE_QUERY_KEYS else m.group(0)

    return _QUERY_PARAM.sub(_mask, query)


def _scrub_url(url: Any) -> Any:
    if not isinstance(url, str) or "?" not in url:
        return url
    base, _, rest = url.partition("?")
    return f"{base}?{scrub_query(rest)}"


def _scrub_data(data: Any) -> None:
    if not isinstance(data, dict):
        return
    for key in ("url", "http.url", "http.target"):
        if key in data:
            data[key] = _scrub_url(data[key])
    if "http.query" in data and isinstance(data["http.query"], str):
        data["http.query"] = scrub_query(data["http.query"])


# Any "key=value" for a sensitive key inside an arbitrary string (reprs of ASGI
# scopes, log messages, exception text).
_INLINE_PARAM = re.compile(
    r"((?:^|[^A-Za-z0-9_])(?:" + "|".join(sorted(SENSITIVE_QUERY_KEYS)) + r")=)([^&;#\s'\"]+)",
    re.IGNORECASE,
)


def _deep_scrub(value: Any) -> Any:
    """Mask sensitive key=value pairs in every string of the event, recursively."""
    if isinstance(value, str):
        return _INLINE_PARAM.sub(lambda m: m.group(1) + FILTERED, value)
    if isinstance(value, dict):
        return {k: _deep_scrub(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_deep_scrub(v) for v in value]
    return value


def scrub_event(event: dict, _hint: dict | None) -> dict:
    """before_send / before_send_transaction hook: mask query-string credentials."""
    request = event.get("request")
    if isinstance(request, dict):
        if isinstance(request.get("query_string"), str):
            request["query_string"] = scrub_query(request["query_string"])
        request["url"] = _scrub_url(request.get("url"))

    breadcrumbs = event.get("breadcrumbs")
    crumbs = breadcrumbs.get("values", []) if isinstance(breadcrumbs, dict) else breadcrumbs or []
    for crumb in crumbs:
        if isinstance(crumb, dict):
            _scrub_data(crumb.get("data"))

    for span in event.get("spans") or []:
        if isinstance(span, dict):
            _scrub_data(span.get("data"))

    if isinstance(event.get("transaction"), str):
        event["transaction"] = _scrub_url(event["transaction"])
    # Second line of defence for anything the structured passes above don't know
    # about (exception messages, log records, repr'd objects).
    return _deep_scrub(event)


def _rate(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        value = float(raw)
    except ValueError:
        logger.warning("%s=%r is not a number; using %s", name, raw, default)
        return default
    return min(max(value, 0.0), 1.0)


def init_sentry(**overrides: Any) -> bool:
    """Initialise Sentry from the environment. Returns whether it was enabled.

    ``overrides`` are passed to ``sentry_sdk.init`` last (tests use a capturing transport).
    """
    dsn = os.getenv("SENTRY_DSN", "").strip()
    if not dsn:
        return False
    import sentry_sdk

    options: dict[str, Any] = {
        "dsn": dsn,
        "environment": os.getenv("SENTRY_ENVIRONMENT", "production"),
        "send_default_pii": os.getenv("SENTRY_SEND_PII", "").strip().lower() in {"1", "true", "yes"},
        "enable_logs": True,
        # Frame locals hold ASGI scopes (raw query strings with tokens) and DB URLs
        # with passwords; stack traces are enough for this app.
        "include_local_variables": False,
        "traces_sample_rate": _rate("SENTRY_TRACES_SAMPLE_RATE", DEFAULT_TRACES_SAMPLE_RATE),
        "profile_session_sample_rate": _rate("SENTRY_PROFILE_SAMPLE_RATE", DEFAULT_PROFILE_SAMPLE_RATE),
        "profile_lifecycle": "trace",
        "before_send": scrub_event,
        "before_send_transaction": scrub_event,
    }
    options.update(overrides)
    sentry_sdk.init(**options)
    logger.info("Sentry enabled (environment=%s)", options["environment"])
    return True
