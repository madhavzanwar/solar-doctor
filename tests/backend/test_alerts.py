"""Tests for inspection fault alerts (axalon.core.alerts) and their wiring.

No network: webhook delivery goes through a patched `urlopen`, email through a
patched `smtplib.SMTP`.
"""
from __future__ import annotations

import json
import urllib.error
import zipfile
from unittest.mock import MagicMock

import pytest

from axalon.core import alerts
from ml.src.utils import SEVERITY_MAP


_ALERT_ENV = (
    "AXALON_ALERT_WEBHOOK_URL", "AXALON_SMTP_HOST", "AXALON_SMTP_PORT",
    "AXALON_SMTP_USER", "AXALON_SMTP_PASSWORD", "AXALON_SMTP_STARTTLS",
    "AXALON_ALERT_EMAIL_FROM", "AXALON_ALERT_EMAIL_TO",
    "AXALON_ALERT_MIN_SEVERITY", "AXALON_PUBLIC_BASE_URL",
)


@pytest.fixture(autouse=True)
def _clean_alert_env(monkeypatch):
    for name in _ALERT_ENV:
        monkeypatch.delenv(name, raising=False)


def _cls_for(severity: str) -> str:
    return next(c for c, s in SEVERITY_MAP.items() if s == severity)


def _det(severity: str, panel: str, conf: float = 0.9, gps=None) -> dict:
    return {
        "class": _cls_for(severity),
        "severity": severity,
        "confidence": conf,
        "panel_id": panel,
        "gps": gps,
    }


def _result(dets: list[dict]) -> dict:
    summary = {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for d in dets:
        summary[d["severity"]] += 1
    return {
        "batch_id": "BATCH-P1-20260913-120000",
        "park_id": "P1",
        "total_images": 3,
        "summary": summary,
        "results": [{"detections": dets}],
    }


def _ok_response():
    resp = MagicMock()
    resp.status = 200
    resp.__enter__.return_value = resp
    resp.__exit__.return_value = False
    return resp


# ── config ──────────────────────────────────────────────────────────────────

def test_config_unconfigured_by_default():
    cfg = alerts.AlertConfig.from_env()
    assert cfg.webhook_url is None
    assert not cfg.email_enabled
    assert cfg.min_severity == "CRITICAL"


def test_config_invalid_min_severity_falls_back_to_critical(monkeypatch):
    monkeypatch.setenv("AXALON_ALERT_MIN_SEVERITY", "apocalyptic")
    assert alerts.AlertConfig.from_env().min_severity == "CRITICAL"


def test_config_parses_email_recipients(monkeypatch):
    monkeypatch.setenv("AXALON_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("AXALON_ALERT_EMAIL_FROM", "alerts@example.com")
    monkeypatch.setenv("AXALON_ALERT_EMAIL_TO", " a@x.com, ,b@x.com ")
    monkeypatch.setenv("AXALON_ALERT_MIN_SEVERITY", "high")
    cfg = alerts.AlertConfig.from_env()
    assert cfg.email_to == ["a@x.com", "b@x.com"]
    assert cfg.email_enabled
    assert cfg.smtp_port == 587
    assert cfg.smtp_starttls is True
    assert cfg.min_severity == "HIGH"


# ── threshold filtering ─────────────────────────────────────────────────────

def test_faults_at_or_above_filters_by_rank_and_sorts_worst_first():
    dets = [
        _det("LOW", "R1-C1"), _det("HIGH", "R1-C2", 0.5),
        _det("CRITICAL", "R1-C3", 0.4), _det("MEDIUM", "R1-C4"),
        _det("HIGH", "R1-C5", 0.8),
    ]
    got = alerts.faults_at_or_above(dets, "HIGH")
    assert [d["panel_id"] for d in got] == ["R1-C3", "R1-C5", "R1-C2"]
    assert alerts.faults_at_or_above(dets, "CRITICAL") == [dets[2]]
    assert len(alerts.faults_at_or_above(dets, "LOW")) == 5


def test_build_payload_returns_none_below_threshold():
    result = _result([_det("HIGH", "R1-C1"), _det("LOW", "R2-C2")])
    assert alerts.build_alert_payload("job-1", result, min_severity="CRITICAL") is None


# ── payload contents ────────────────────────────────────────────────────────

def test_build_payload_contents():
    gps = {"lat": 26.9, "lon": 75.8}
    dets = [_det("CRITICAL", f"R1-C{i}", 0.5 + i / 100, gps) for i in range(7)]
    dets.append(_det("MEDIUM", "R9-C9"))
    payload = alerts.build_alert_payload(
        "job-1", _result(dets), min_severity="CRITICAL",
        public_base_url="https://axalon.example/", top_n=5,
    )
    assert payload["park_id"] == "P1"
    assert payload["job_id"] == "job-1"
    assert payload["inspection_id"] == "BATCH-P1-20260913-120000"
    assert payload["min_severity"] == "CRITICAL"
    assert payload["counts"] == {"CRITICAL": 7, "HIGH": 0, "MEDIUM": 1, "LOW": 0}
    assert payload["alerting_faults"] == 7
    assert len(payload["top_faults"]) == 5
    top = payload["top_faults"][0]
    assert top["panel_id"] == "R1-C6"  # highest confidence first
    assert top["severity"] == "CRITICAL"
    assert top["class"] == _cls_for("CRITICAL")
    assert top["gps"] == gps
    assert payload["link"] == "https://axalon.example/platform?job=job-1"
    # Slack incoming-webhook compatibility
    assert isinstance(payload["text"], str)
    assert "7 CRITICAL" in payload["text"] and "P1" in payload["text"]
    assert "https://axalon.example/platform?job=job-1" in payload["text"]
    json.dumps(payload)  # must be serialisable


def test_build_payload_without_base_url_has_no_link():
    payload = alerts.build_alert_payload(
        "job-1", _result([_det("CRITICAL", "R1-C1")]), min_severity="CRITICAL",
    )
    assert payload["link"] is None


# ── webhook ─────────────────────────────────────────────────────────────────

def test_webhook_posts_json(monkeypatch):
    opener = MagicMock(return_value=_ok_response())
    monkeypatch.setattr(alerts, "urlopen", opener)
    out = alerts.send_webhook("https://hooks.example/abc", {"text": "hi"}, timeout=3)
    assert out["status"] == "sent"
    req = opener.call_args.args[0]
    assert req.get_method() == "POST"
    assert req.headers["Content-type"] == "application/json"
    assert json.loads(req.data) == {"text": "hi"}
    assert opener.call_args.kwargs["timeout"] == 3


def test_webhook_retries_once_then_gives_up(monkeypatch):
    opener = MagicMock(side_effect=urllib.error.URLError("down"))
    monkeypatch.setattr(alerts, "urlopen", opener)
    monkeypatch.setattr(alerts.time, "sleep", lambda _s: None)
    out = alerts.send_webhook("https://hooks.example/abc", {"text": "hi"})
    assert out["status"] == "failed"
    assert opener.call_count == 2
    assert "hooks.example/abc" not in out["detail"]  # URL may embed a secret


def test_webhook_succeeds_on_retry(monkeypatch):
    opener = MagicMock(side_effect=[TimeoutError("slow"), _ok_response()])
    monkeypatch.setattr(alerts, "urlopen", opener)
    monkeypatch.setattr(alerts.time, "sleep", lambda _s: None)
    assert alerts.send_webhook("https://hooks.example/abc", {})["status"] == "sent"
    assert opener.call_count == 2


def test_webhook_rejects_non_http_scheme(monkeypatch):
    opener = MagicMock()
    monkeypatch.setattr(alerts, "urlopen", opener)
    out = alerts.send_webhook("file:///etc/passwd", {})
    assert out["status"] == "failed"
    opener.assert_not_called()


# ── email ───────────────────────────────────────────────────────────────────

def _email_cfg(**overrides) -> alerts.AlertConfig:
    base = dict(
        smtp_host="smtp.example.com", smtp_port=2525, smtp_user="bot",
        smtp_password="s3cret", smtp_starttls=True,
        email_from="alerts@example.com", email_to=["a@x.com", "b@x.com"],
    )
    base.update(overrides)
    return alerts.AlertConfig(**base)


def test_email_message_construction(monkeypatch):
    smtp_cls = MagicMock()
    server = smtp_cls.return_value.__enter__.return_value
    monkeypatch.setattr(alerts.smtplib, "SMTP", smtp_cls)
    payload = alerts.build_alert_payload(
        "job-1", _result([_det("CRITICAL", "R1-C1", gps={"lat": 1.0, "lon": 2.0})]),
        min_severity="CRITICAL",
    )
    out = alerts.send_email(_email_cfg(), payload)
    assert out["status"] == "sent"
    smtp_cls.assert_called_once_with("smtp.example.com", 2525, timeout=alerts.SMTP_TIMEOUT_S)
    server.starttls.assert_called_once()
    server.login.assert_called_once_with("bot", "s3cret")
    msg = server.send_message.call_args.args[0]
    assert msg["From"] == "alerts@example.com"
    assert msg["To"] == "a@x.com, b@x.com"
    assert "CRITICAL" in msg["Subject"] and "P1" in msg["Subject"]
    body = msg.get_content()
    assert "R1-C1" in body and "job-1" in body


def test_email_without_starttls_or_login(monkeypatch):
    smtp_cls = MagicMock()
    server = smtp_cls.return_value.__enter__.return_value
    monkeypatch.setattr(alerts.smtplib, "SMTP", smtp_cls)
    cfg = _email_cfg(smtp_user=None, smtp_password=None, smtp_starttls=False)
    assert alerts.send_email(cfg, {"text": "t", "subject": "s"})["status"] == "sent"
    server.starttls.assert_not_called()
    server.login.assert_not_called()


def test_email_failure_is_reported_not_raised(monkeypatch):
    monkeypatch.setattr(alerts.smtplib, "SMTP", MagicMock(side_effect=OSError("refused")))
    out = alerts.send_email(_email_cfg(), {"text": "t", "subject": "s"})
    assert out["status"] == "failed"
    assert "s3cret" not in out["detail"]


# ── dispatch / job notification ─────────────────────────────────────────────

def test_notify_skips_when_nothing_configured():
    out = alerts.notify_inspection_complete(
        "job-1", _result([_det("CRITICAL", "R1-C1")]), alerts.AlertConfig(),
    )
    assert out == {
        "webhook": {"status": "not_configured", "detail": ""},
        "email": {"status": "not_configured", "detail": ""},
    }


def test_notify_skips_below_threshold(monkeypatch):
    opener = MagicMock()
    monkeypatch.setattr(alerts, "urlopen", opener)
    cfg = alerts.AlertConfig(webhook_url="https://hooks.example/x")
    out = alerts.notify_inspection_complete("job-1", _result([_det("HIGH", "R1-C1")]), cfg)
    assert out["webhook"]["status"] == "skipped"
    opener.assert_not_called()


def test_notify_sends_and_never_raises(monkeypatch):
    monkeypatch.setattr(alerts, "urlopen", MagicMock(return_value=_ok_response()))
    monkeypatch.setattr(alerts.smtplib, "SMTP", MagicMock(side_effect=RuntimeError("x")))
    cfg = _email_cfg(webhook_url="https://hooks.example/x")
    out = alerts.notify_inspection_complete("job-1", _result([_det("CRITICAL", "R1-C1")]), cfg)
    assert out["webhook"]["status"] == "sent"
    assert out["email"]["status"] == "failed"


def test_notify_survives_malformed_result():
    cfg = alerts.AlertConfig(webhook_url="https://hooks.example/x")
    out = alerts.notify_inspection_complete("job-1", {"summary": "garbage"}, cfg)
    assert set(out) == {"webhook", "email"}


def test_run_batch_job_succeeds_when_alerting_throws(temp_db, tmp_path, monkeypatch):
    from axalon.api.support import jobs

    out_dir = tmp_path / "output"
    out_dir.mkdir()
    zip_path = tmp_path / "m.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("thermal/a.txt", "x")

    orch = MagicMock()
    orch.inspect_folder.return_value = _result([_det("CRITICAL", "R1-C1")])
    monkeypatch.setattr(jobs, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(jobs, "get_orchestrator", lambda: orch)
    for name in ("generate_json_report", "generate_excel_report",
                 "write_geojson", "generate_pdf_report"):
        monkeypatch.setattr(jobs, name, MagicMock())
    monkeypatch.setattr(
        jobs, "notify_inspection_complete", MagicMock(side_effect=RuntimeError("boom")),
    )

    jobs._create_job("job-alert-1", park_id="P1")
    jobs._run_batch_job("job-alert-1", zip_path, "P1", 40.0)

    state = jobs._get_job("job-alert-1")
    assert state["state"] == "succeeded"
    assert state["message"] is None
    jobs.notify_inspection_complete.assert_called_once()


def test_run_batch_job_alerts_after_success_is_committed(temp_db, tmp_path, monkeypatch):
    from axalon.api.support import jobs

    out_dir = tmp_path / "output"
    out_dir.mkdir()
    zip_path = tmp_path / "m.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("thermal/a.txt", "x")
    orch = MagicMock()
    orch.inspect_folder.return_value = _result([_det("CRITICAL", "R1-C1")])
    monkeypatch.setattr(jobs, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(jobs, "get_orchestrator", lambda: orch)
    for name in ("generate_json_report", "generate_excel_report",
                 "write_geojson", "generate_pdf_report"):
        monkeypatch.setattr(jobs, name, MagicMock())

    seen_state = {}

    def _notify(job_id, result):
        seen_state.update(jobs._get_job(job_id))
        return {}

    monkeypatch.setattr(jobs, "notify_inspection_complete", _notify)
    jobs._create_job("job-alert-2", park_id="P1")
    jobs._run_batch_job("job-alert-2", zip_path, "P1", 40.0)
    assert seen_state["state"] == "succeeded"


# ── POST /alerts/test ───────────────────────────────────────────────────────

def test_alerts_test_endpoint_not_configured(client):
    resp = client.post("/alerts/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is False
    assert body["channels"]["webhook"]["status"] == "not_configured"
    assert body["channels"]["email"]["status"] == "not_configured"


def test_alerts_test_endpoint_sends_through_configured_channels(client, monkeypatch):
    monkeypatch.setenv("AXALON_ALERT_WEBHOOK_URL", "https://hooks.example/x")
    monkeypatch.setenv("AXALON_ALERT_MIN_SEVERITY", "HIGH")
    opener = MagicMock(return_value=_ok_response())
    monkeypatch.setattr(alerts, "urlopen", opener)
    resp = client.post("/alerts/test")
    assert resp.status_code == 200
    body = resp.json()
    assert body["configured"] is True
    assert body["min_severity"] == "HIGH"
    assert body["channels"]["webhook"]["status"] == "sent"
    assert body["channels"]["email"]["status"] == "not_configured"
    sent = json.loads(opener.call_args.args[0].data)
    assert sent["test"] is True and "text" in sent


def test_alerts_test_endpoint_reports_failure(client, monkeypatch):
    monkeypatch.setenv("AXALON_ALERT_WEBHOOK_URL", "https://hooks.example/x")
    monkeypatch.setattr(alerts, "urlopen", MagicMock(side_effect=urllib.error.URLError("no")))
    monkeypatch.setattr(alerts.time, "sleep", lambda _s: None)
    resp = client.post("/alerts/test")
    assert resp.status_code == 200
    assert resp.json()["channels"]["webhook"]["status"] == "failed"
