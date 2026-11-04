"""Fault alerts: notify operators when an inspection finds serious faults.

Two optional channels, each active only when its environment is configured:

    Webhook  AXALON_ALERT_WEBHOOK_URL — POST JSON (Slack-compatible `text` field)
    Email    AXALON_SMTP_HOST/PORT/USER/PASSWORD/STARTTLS,
             AXALON_ALERT_EMAIL_FROM, AXALON_ALERT_EMAIL_TO (comma-separated)

AXALON_ALERT_MIN_SEVERITY (default CRITICAL) sets the lowest severity that
triggers an alert; AXALON_PUBLIC_BASE_URL, when set, adds a console link.

Delivery is best-effort by design: every public entry point returns a
per-channel outcome dict and never raises, and every network call carries a
bounded timeout, so a dead webhook or SMTP server can never fail an inspection.
"""
from __future__ import annotations

import json
import logging
import os
import smtplib
import time
from dataclasses import dataclass, field
from email.message import EmailMessage
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from ml.src.utils import SEVERITY_COLOR_BGR

logger = logging.getLogger("axalon.alerts")

# Worst → least severe. SEVERITY_COLOR_BGR is keyed by the canonical severity
# levels in that order; deriving from it keeps the vocabulary in ml.src.utils.
SEVERITY_LEVELS: tuple[str, ...] = tuple(SEVERITY_COLOR_BGR)
_RANK = {sev: i for i, sev in enumerate(SEVERITY_LEVELS)}  # lower = worse
DEFAULT_MIN_SEVERITY = SEVERITY_LEVELS[0]

WEBHOOK_TIMEOUT_S = 8
WEBHOOK_RETRY_DELAY_S = 1.0
SMTP_TIMEOUT_S = 10
DEFAULT_SMTP_PORT = 587
DEFAULT_TOP_N = 5

SENT = "sent"
FAILED = "failed"
SKIPPED = "skipped"
NOT_CONFIGURED = "not_configured"


def _outcome(status: str, detail: str = "") -> dict:
    return {"status": status, "detail": detail}


def _env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


def _env_bool(name: str, default: bool) -> bool:
    value = _env(name)
    if value is None:
        return default
    return value.lower() not in ("0", "false", "no", "off")


def _parse_min_severity(raw: str | None) -> str:
    if not raw:
        return DEFAULT_MIN_SEVERITY
    sev = raw.strip().upper()
    if sev not in _RANK:
        logger.warning(
            "AXALON_ALERT_MIN_SEVERITY=%r is not one of %s; using %s",
            raw, "|".join(SEVERITY_LEVELS), DEFAULT_MIN_SEVERITY,
        )
        return DEFAULT_MIN_SEVERITY
    return sev


@dataclass(frozen=True)
class AlertConfig:
    webhook_url: str | None = None
    smtp_host: str | None = None
    smtp_port: int = DEFAULT_SMTP_PORT
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_starttls: bool = True
    email_from: str | None = None
    email_to: list[str] = field(default_factory=list)
    min_severity: str = DEFAULT_MIN_SEVERITY
    public_base_url: str | None = None

    @property
    def email_enabled(self) -> bool:
        return bool(self.smtp_host and self.email_from and self.email_to)

    @property
    def any_enabled(self) -> bool:
        return bool(self.webhook_url) or self.email_enabled

    @classmethod
    def from_env(cls) -> "AlertConfig":
        port_raw = _env("AXALON_SMTP_PORT")
        try:
            port = int(port_raw) if port_raw else DEFAULT_SMTP_PORT
        except ValueError:
            logger.warning("AXALON_SMTP_PORT=%r is not an integer; using %s", port_raw, DEFAULT_SMTP_PORT)
            port = DEFAULT_SMTP_PORT
        recipients = [
            addr.strip() for addr in (_env("AXALON_ALERT_EMAIL_TO") or "").split(",") if addr.strip()
        ]
        return cls(
            webhook_url=_env("AXALON_ALERT_WEBHOOK_URL"),
            smtp_host=_env("AXALON_SMTP_HOST"),
            smtp_port=port,
            smtp_user=_env("AXALON_SMTP_USER"),
            smtp_password=_env("AXALON_SMTP_PASSWORD"),
            smtp_starttls=_env_bool("AXALON_SMTP_STARTTLS", True),
            email_from=_env("AXALON_ALERT_EMAIL_FROM"),
            email_to=recipients,
            min_severity=_parse_min_severity(_env("AXALON_ALERT_MIN_SEVERITY")),
            public_base_url=_env("AXALON_PUBLIC_BASE_URL"),
        )


# ── Payload ──────────────────────────────────────────────────────────────────

def faults_at_or_above(detections: list[dict], min_severity: str) -> list[dict]:
    """Detections whose severity is at least `min_severity`, worst and most
    confident first. Unknown severities never qualify."""
    limit = _RANK.get(min_severity, 0)
    hits = [d for d in detections if _RANK.get(d.get("severity"), len(_RANK)) <= limit]
    return sorted(hits, key=lambda d: (_RANK[d["severity"]], -float(d.get("confidence") or 0.0)))


def _all_detections(result: dict) -> list[dict]:
    dets: list[dict] = []
    for item in result.get("results") or []:
        if isinstance(item, dict):
            dets.extend(d for d in item.get("detections") or [] if isinstance(d, dict))
    return dets


def _unique_faults(faults: list[dict]) -> list[dict]:
    """One entry per (panel, class): overlapping frames see the same fault."""
    seen: set[tuple] = set()
    out = []
    for det in faults:
        key = (det.get("panel_id"), det.get("class"))
        if key in seen:
            continue
        seen.add(key)
        out.append(det)
    return out


def _counts(result: dict, detections: list[dict]) -> dict[str, int]:
    summary = result.get("summary")
    counts = {sev: 0 for sev in SEVERITY_LEVELS}
    if isinstance(summary, dict):
        for sev in SEVERITY_LEVELS:
            try:
                counts[sev] = int(summary.get(sev) or 0)
            except (TypeError, ValueError):
                counts[sev] = 0
        return counts
    for det in detections:
        if det.get("severity") in counts:
            counts[det["severity"]] += 1
    return counts


def _link(public_base_url: str | None, job_id: str) -> str | None:
    if not public_base_url:
        return None
    return f"{public_base_url.rstrip('/')}/platform?job={job_id}"


def _headline(park_id: str, counts: dict[str, int], min_severity: str) -> str:
    parts = [f"{counts[sev]} {sev}" for sev in SEVERITY_LEVELS
             if _RANK[sev] <= _RANK[min_severity] and counts[sev]]
    return f"Axalon: {', '.join(parts) or 'no'} fault(s) at park {park_id}"


def _fault_line(fault: dict) -> str:
    gps = fault.get("gps")
    where = ""
    if isinstance(gps, dict) and all(isinstance(gps.get(k), (int, float)) for k in ("lat", "lon")):
        where = f" @ {gps['lat']:.6f},{gps['lon']:.6f}"
    conf = fault.get("confidence")
    conf_s = f" ({float(conf):.0%})" if isinstance(conf, (int, float)) else ""
    return f"• {fault.get('severity')} {fault.get('class')} on panel {fault.get('panel_id')}{conf_s}{where}"


def build_alert_payload(
    job_id: str,
    result: dict,
    *,
    min_severity: str = DEFAULT_MIN_SEVERITY,
    public_base_url: str | None = None,
    top_n: int = DEFAULT_TOP_N,
) -> dict | None:
    """Alert body for a completed inspection, or None when nothing meets the
    threshold. Counts come from the deduplicated summary; `top_faults` from
    the per-image detections."""
    detections = _all_detections(result)
    counts = _counts(result, detections)
    alerting = sum(n for sev, n in counts.items() if _RANK[sev] <= _RANK[min_severity])
    faults = _unique_faults(faults_at_or_above(detections, min_severity))
    if alerting == 0 and not faults:
        return None
    alerting = alerting or len(faults)

    park_id = str(result.get("park_id") or "unknown")
    top = [
        {
            "class": f.get("class"),
            "severity": f.get("severity"),
            "panel_id": f.get("panel_id"),
            "confidence": f.get("confidence"),
            "gps": f.get("gps"),
        }
        for f in faults[:top_n]
    ]
    link = _link(public_base_url, job_id)
    subject = _headline(park_id, counts, min_severity)
    lines = [f"*{subject}*", f"Job {job_id} · inspection {result.get('batch_id') or '—'}"]
    lines += [_fault_line(f) for f in top]
    if len(faults) > len(top):
        lines.append(f"…and {len(faults) - len(top)} more")
    if link:
        lines.append(link)

    return {
        "text": "\n".join(lines),
        "subject": subject,
        "event": "inspection.faults",
        "test": False,
        "park_id": park_id,
        "job_id": job_id,
        "inspection_id": result.get("batch_id"),
        "min_severity": min_severity,
        "counts": counts,
        "alerting_faults": alerting,
        "top_faults": top,
        "link": link,
    }


def build_test_payload(config: AlertConfig) -> dict:
    link = _link(config.public_base_url, "test")
    text = (
        "*Axalon test alert*\n"
        f"Alert delivery is working. Real alerts fire for faults at or above "
        f"{config.min_severity}."
    )
    return {
        "text": text + (f"\n{link}" if link else ""),
        "subject": "Axalon: test alert",
        "event": "alerts.test",
        "test": True,
        "park_id": None,
        "job_id": None,
        "inspection_id": None,
        "min_severity": config.min_severity,
        "counts": {sev: 0 for sev in SEVERITY_LEVELS},
        "alerting_faults": 0,
        "top_faults": [],
        "link": link,
    }


# ── Channels ─────────────────────────────────────────────────────────────────

def _describe_error(exc: BaseException) -> str:
    # Never echo the URL (Slack/Teams webhook URLs embed the secret token).
    if isinstance(exc, HTTPError):
        return f"HTTP {exc.code}"
    if isinstance(exc, URLError):
        return f"connection error: {exc.reason}"
    return type(exc).__name__


def send_webhook(
    url: str, payload: dict, *, timeout: float = WEBHOOK_TIMEOUT_S, retries: int = 1,
) -> dict:
    """POST `payload` as JSON; retry `retries` times on failure. Never raises."""
    if urlparse(url).scheme not in ("http", "https"):
        return _outcome(FAILED, "webhook URL must be http(s)")
    body = json.dumps(payload, default=str).encode("utf-8")
    last_error = "unknown error"
    for attempt in range(retries + 1):
        if attempt:
            time.sleep(WEBHOOK_RETRY_DELAY_S)
        try:
            req = Request(url, data=body, method="POST",
                          headers={"Content-Type": "application/json"})
            with urlopen(req, timeout=timeout) as resp:
                return _outcome(SENT, f"HTTP {getattr(resp, 'status', 200)}")
        except Exception as exc:  # noqa: BLE001 — delivery must never raise
            last_error = _describe_error(exc)
            logger.warning("Alert webhook attempt %d failed: %s", attempt + 1, last_error)
    return _outcome(FAILED, last_error)


def _email_body(payload: dict) -> str:
    body = payload.get("text") or ""
    return body.replace("*", "")


def send_email(config: AlertConfig, payload: dict) -> dict:
    """Send `payload` as a plain-text email via SMTP. Never raises."""
    try:
        msg = EmailMessage()
        msg["Subject"] = payload.get("subject") or "Axalon alert"
        msg["From"] = config.email_from
        msg["To"] = ", ".join(config.email_to)
        lines = [_email_body(payload)]
        if payload.get("job_id"):
            lines.append(f"\nJob ID: {payload['job_id']}")
        msg.set_content("\n".join(lines))

        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=SMTP_TIMEOUT_S) as server:
            if config.smtp_starttls:
                server.starttls()
            if config.smtp_user:
                server.login(config.smtp_user, config.smtp_password or "")
            server.send_message(msg)
        return _outcome(SENT, f"{len(config.email_to)} recipient(s)")
    except Exception as exc:  # noqa: BLE001 — delivery must never raise
        # Class name only: SMTP auth errors can echo credentials back.
        detail = _describe_error(exc)
        logger.warning("Alert email failed: %s", detail)
        return _outcome(FAILED, detail)


def dispatch(config: AlertConfig, payload: dict | None, *, webhook_retries: int = 1) -> dict:
    """Deliver `payload` on every configured channel. `None` → skipped."""
    outcomes = {}
    for name, enabled, send in (
        ("webhook", bool(config.webhook_url),
         lambda: send_webhook(config.webhook_url, payload, retries=webhook_retries)),
        ("email", config.email_enabled, lambda: send_email(config, payload)),
    ):
        if not enabled:
            outcomes[name] = _outcome(NOT_CONFIGURED)
        elif payload is None:
            outcomes[name] = _outcome(SKIPPED, f"no faults at or above {config.min_severity}")
        else:
            outcomes[name] = send()
    return outcomes


def notify_inspection_complete(
    job_id: str, result: dict, config: AlertConfig | None = None,
) -> dict:
    """Alert on a finished inspection if it meets the threshold. Never raises;
    returns and logs the per-channel outcome."""
    try:
        config = config or AlertConfig.from_env()
    except Exception:  # noqa: BLE001
        logger.exception("Alert config could not be loaded for job %s", job_id)
        return {"webhook": _outcome(FAILED, "config error"), "email": _outcome(FAILED, "config error")}

    if not config.any_enabled:
        return dispatch(config, None)
    try:
        payload = build_alert_payload(
            job_id, result if isinstance(result, dict) else {},
            min_severity=config.min_severity, public_base_url=config.public_base_url,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Could not build alert payload for job %s", job_id)
        return {
            name: _outcome(FAILED, "payload error") if enabled else _outcome(NOT_CONFIGURED)
            for name, enabled in (("webhook", bool(config.webhook_url)), ("email", config.email_enabled))
        }
    outcomes = dispatch(config, payload)
    logger.info(
        "Alerts for job %s: %s", job_id,
        ", ".join(f"{name}={o['status']}" for name, o in outcomes.items()),
    )
    return outcomes


def send_test_alert(config: AlertConfig | None = None) -> dict:
    """Send a test message on every configured channel and report each result.

    No webhook retry here: an operator is waiting on the button, and the
    webhook + SMTP timeouts must together stay under the console's 20 s
    request timeout.
    """
    config = config or AlertConfig.from_env()
    return {
        "configured": config.any_enabled,
        "min_severity": config.min_severity,
        "channels": dispatch(config, build_test_payload(config), webhook_retries=0),
    }
