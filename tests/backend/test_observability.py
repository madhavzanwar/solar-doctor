"""Sentry error monitoring for the API.

Credentials in this system travel in query strings — `?api_key=` for <img> and
download URLs, `?share=` for share links, `?token=` for the drone relay. Sentry's
default scrubber filters dict keys (headers, extras) but not the raw query
string or URLs, so without our own scrubbing those tokens would be stored in
Sentry events, breadcrumbs and spans.
"""
import pytest


@pytest.fixture(autouse=True)
def _no_real_sentry(monkeypatch):
    for key in ("SENTRY_DSN", "SENTRY_TRACES_SAMPLE_RATE", "SENTRY_PROFILE_SAMPLE_RATE",
                "SENTRY_ENVIRONMENT", "SENTRY_SEND_PII"):
        monkeypatch.delenv(key, raising=False)
    yield
    import sentry_sdk
    sentry_sdk.init()  # detach any client a test installed


def test_init_is_a_no_op_without_dsn(monkeypatch):
    import sentry_sdk
    from axalon.core import observability

    calls = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: calls.append(kw))

    assert observability.init_sentry() is False
    assert calls == []


def test_init_reads_config_from_env(monkeypatch):
    import sentry_sdk
    from axalon.core import observability

    calls = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: calls.append(kw))
    monkeypatch.setenv("SENTRY_DSN", "https://public@o1.ingest.sentry.io/1")
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "0.25")
    monkeypatch.setenv("SENTRY_ENVIRONMENT", "production")

    assert observability.init_sentry() is True
    kw = calls[0]
    assert kw["dsn"] == "https://public@o1.ingest.sentry.io/1"
    assert kw["traces_sample_rate"] == 0.25
    assert kw["environment"] == "production"
    assert kw["send_default_pii"] is False
    assert kw["before_send"] is observability.scrub_event


def test_invalid_sample_rate_falls_back_to_default(monkeypatch):
    import sentry_sdk
    from axalon.core import observability

    calls = []
    monkeypatch.setattr(sentry_sdk, "init", lambda **kw: calls.append(kw))
    monkeypatch.setenv("SENTRY_DSN", "https://public@o1.ingest.sentry.io/1")
    monkeypatch.setenv("SENTRY_TRACES_SAMPLE_RATE", "lots")

    observability.init_sentry()

    assert calls[0]["traces_sample_rate"] == observability.DEFAULT_TRACES_SAMPLE_RATE


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("api_key=abc123&park=P1", "api_key=[Filtered]&park=P1"),
        ("token=relaytok&operator=op-a", "token=[Filtered]&operator=op-a"),
        ("share=s3cr3t", "share=[Filtered]"),
        ("format=pdf", "format=pdf"),
        ("", ""),
    ],
)
def test_scrub_query(raw, expected):
    from axalon.core.observability import scrub_query

    assert scrub_query(raw) == expected


def test_scrub_event_covers_request_breadcrumbs_and_spans():
    from axalon.core.observability import scrub_event

    event = {
        "request": {
            "url": "https://api.example/report/j1?format=pdf&api_key=abc123",
            "query_string": "format=pdf&api_key=abc123",
        },
        "breadcrumbs": {"values": [{"data": {"url": "https://relay/turn-credentials?token=relaytok"}}]},
        "spans": [{"data": {"http.query": "share=s3cr3t", "url": "/x?api_key=abc123"}}],
    }

    out = scrub_event(event, {})

    text = repr(out)
    for secret in ("abc123", "relaytok", "s3cr3t"):
        assert secret not in text
    assert out["request"]["query_string"] == "format=pdf&api_key=[Filtered]"


def test_real_error_event_contains_no_query_token():
    """End to end through the SDK: an exception in a FastAPI route."""
    import sentry_sdk
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from axalon.core import observability

    envelopes = []

    class CaptureTransport(sentry_sdk.transport.Transport):
        def capture_envelope(self, envelope):
            envelopes.append(envelope)

    app = FastAPI()

    @app.get("/boom")
    def boom():
        raise RuntimeError("kaboom")

    import os
    os.environ["SENTRY_DSN"] = "https://public@o1.ingest.sentry.io/1"
    try:
        observability.init_sentry(transport=CaptureTransport, traces_sample_rate=1.0)
        with pytest.raises(RuntimeError):
            TestClient(app).get("/boom?api_key=abc123&park=P1")
        sentry_sdk.flush()
    finally:
        del os.environ["SENTRY_DSN"]

    payloads = [item.payload.get_bytes() for env in envelopes for item in env.items]
    assert any(b"kaboom" in p for p in payloads), "error event was not captured"
    assert not any(b"abc123" in p for p in payloads), "query token leaked to Sentry"


def test_deep_scrub_masks_whole_token_inside_free_text():
    from axalon.core.observability import scrub_event

    event = {"exception": {"values": [{"value": "upstream rejected share=sss_secret_value for P1"}]},
             "logentry": {"message": "GET /x?token=ssXss&y=1"}}

    text = repr(scrub_event(event, {}))

    assert "sss_secret_value" not in text and "_secret_value" not in text
    assert "ssXss" not in text and "Xss" not in text
