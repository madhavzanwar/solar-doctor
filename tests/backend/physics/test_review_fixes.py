"""Regression tests for the sd-qa review of feat/physics-port (REVIEW_physics.md)."""
import logging
from datetime import datetime, timezone

import httpx
import pytest

PLANT = dict(name="P", latitude=18.5, longitude=73.8, timezone="Asia/Kolkata",
             capacity_kw=120.0, inverter_capacity_kw=100.0)


@pytest.fixture(autouse=True)
def _iso(monkeypatch, tmp_path):
    monkeypatch.delenv("SOLARDOCTOR_WEATHER_API_KEY", raising=False)
    monkeypatch.setenv("SOLARDOCTOR_FORECAST_ARTIFACTS", str(tmp_path / "a"))
    from solardoctor.physics.registry import reset_registry
    reset_registry()
    # alembic's fileConfig (run by migration tests in the same process) disables existing loggers.
    for name in list(logging.root.manager.loggerDict):
        if name.startswith(("solardoctor", "httpx", "httpcore")):
            logging.getLogger(name).disabled = False
    logging.getLogger("httpx").setLevel(logging.INFO)  # httpx logs full request URLs at INFO
    yield
    reset_registry()


def _mk(client, **kw):
    r = client.post("/api/v1/plants", json={**PLANT, **kw})
    assert r.status_code == 201, r.text
    return r.json()


# ── M1: API key never reaches logs ──────────────────────────────────────────

@pytest.mark.parametrize("status_code", [401, 500])
def test_weather_api_key_not_logged(monkeypatch, caplog, status_code):
    from solardoctor.physics import weather_service as ws
    monkeypatch.setenv("SOLARDOCTOR_WEATHER_API_KEY", "SUPERSECRETKEY")
    caplog.set_level(logging.DEBUG)
    wd = ws.get_current_weather(18.5, 73.8, transport=httpx.MockTransport(lambda r: httpx.Response(status_code)))
    assert wd.source == "mock"
    assert "SUPERSECRETKEY" not in caplog.text
    assert f"HTTP {status_code}" in caplog.text


def test_httpx_info_logging_is_redacted_even_if_level_lowered(monkeypatch, caplog):
    from solardoctor.physics import weather_service as ws
    monkeypatch.setenv("SOLARDOCTOR_WEATHER_API_KEY", "SUPERSECRETKEY")
    ws.harden_http_logging()                       # what building the client does
    logging.getLogger("httpx").setLevel(logging.INFO)  # someone (basicConfig, ops) lowers it again
    caplog.set_level(logging.DEBUG)
    ws.get_current_weather(18.5, 73.8, transport=httpx.MockTransport(lambda r: httpx.Response(401)))
    ws.get_current_weather(18.5, 73.8, transport=httpx.MockTransport(lambda r: httpx.Response(200, json={})))
    http_lines = [r.getMessage() for r in caplog.records if r.name == "httpx"]
    assert http_lines, "httpx INFO request line should be emitted for this test to prove the filter"
    assert all("SUPERSECRETKEY" not in m for m in http_lines) and any("key=***" in m for m in http_lines)
    assert "SUPERSECRETKEY" not in caplog.text


def test_client_construction_raises_http_loggers_to_warning(monkeypatch):
    import solardoctor.physics.weather_service as ws
    monkeypatch.setattr(ws, "_http_level_set", False)
    ws.WeatherAPIClient("k")
    assert logging.getLogger("httpx").level == logging.WARNING


def test_weather_connection_error_not_logged_with_key(monkeypatch, caplog):
    from solardoctor.physics import weather_service as ws
    monkeypatch.setenv("SOLARDOCTOR_WEATHER_API_KEY", "SUPERSECRETKEY")

    def boom(request):
        raise httpx.ConnectError("failed for https://api.weatherapi.com/v1/forecast.json?key=SUPERSECRETKEY&q=1")

    caplog.set_level(logging.DEBUG)
    ws.get_forecast_weather(18.5, 73.8, transport=httpx.MockTransport(boom))
    assert "SUPERSECRETKEY" not in caplog.text


def test_redact_helper():
    from solardoctor.physics.weather_service import redact
    out = redact("GET https://x/y?a=1&key=ABC123&q=2 and api_key=ZZZ")
    assert "ABC123" not in out and "ZZZ" not in out and "q=2" in out


def test_forecast_service_weather_failure_log_is_redacted(client, monkeypatch, caplog):
    from solardoctor.physics import forecast_service as fs, weather_service as ws
    p = _mk(client)

    def fail(*a, **k):
        raise RuntimeError("bad url https://api.weatherapi.com/v1/forecast.json?key=SUPERSECRETKEY")

    monkeypatch.setattr(ws, "get_forecast_weather", fail)
    caplog.set_level(logging.DEBUG)
    assert client.post(f"/api/v1/forecast/{p['id']}/generate").status_code == 200
    assert "SUPERSECRETKEY" not in caplog.text


# ── M2: no fabricated diagnoses ─────────────────────────────────────────────

def test_diagnose_without_telemetry_is_422_and_not_persisted(client, db_session):
    p = _mk(client)
    for body in ({"plant_id": p["id"]}, {"plant_id": p["id"], "inverter_error_code": "F056"},
                 {"plant_id": p["id"], "expected_power_kw": 80}):
        r = client.post("/api/v1/diagnosis/diagnose", json=body)
        assert r.status_code == 422, (body, r.text)
    from solardoctor.physics.models import Diagnosis
    assert db_session.query(Diagnosis).count() == 0
    assert client.get(f"/api/v1/diagnosis/plant/{p['id']}").json() == []


def test_diagnose_uses_latest_telemetry_when_request_has_no_numbers(client, db_session):
    from solardoctor.physics.models import Telemetry
    p = _mk(client, tariff_inr_kwh=6.0)
    db_session.add(Telemetry(plant_id=p["id"], ts=datetime.now(tz=timezone.utc), p_ac_kw=40.0,
                             p_expected_kw=80.0, ghi_wm2=800.0, source="USER"))
    db_session.commit()  # (SIMULATED rows now need allow_simulated: see test_simulated_telemetry_*)
    r = client.post("/api/v1/diagnosis/diagnose", json={"plant_id": p["id"], "inverter_error_code": "F056"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["telemetry_evidence"]["expected_power_kw"] == 80.0 and d["telemetry_evidence"]["actual_power_kw"] == 40.0
    assert d["estimated_loss_kw"] == 40.0


def test_alert_diagnosis_without_power_values_is_422(client, db_session):
    from solardoctor.physics.models import PlantAlert
    p = _mk(client)
    a = PlantAlert(plant_id=p["id"], timestamp=datetime.now(tz=timezone.utc), alert_type="x",
                   severity="WARNING", message="something")
    db_session.add(a)
    db_session.commit()
    assert client.get(f"/api/v1/diagnosis/alert/{a.id}").status_code == 422


def test_no_tariff_does_not_invent_a_price(client):
    p = _mk(client)
    d = client.post("/api/v1/diagnosis/diagnose", json={
        "plant_id": p["id"], "expected_power_kw": 100, "actual_power_kw": 60}).json()
    assert d["currency"] == "unset" and d["financial_impact_per_day"] == 0.0
    assert "No tariff" in d["financial_assumption"] and "$" not in d["summary"]
    assert d["estimated_loss_kw"] == 40.0


def test_with_tariff_is_inr_and_no_assumption_flag(client):
    p = _mk(client, tariff_inr_kwh=6.5)
    d = client.post("/api/v1/diagnosis/diagnose", json={
        "plant_id": p["id"], "expected_power_kw": 100, "actual_power_kw": 60}).json()
    assert d["currency"] == "INR" and d["financial_assumption"] is None
    assert d["financial_impact_per_day"] == round(40 * 5.5 * 6.5, 2)


# ── m1, m2: validation ──────────────────────────────────────────────────────

def test_timezone_and_length_validation(client):
    assert client.post("/api/v1/plants", json={**PLANT, "timezone": "Mars/Phobos"}).status_code == 422
    assert client.post("/api/v1/plants", json={**PLANT, "name": "x" * 5000}).status_code == 422
    assert client.post("/api/v1/plants", json={**PLANT, "name": ""}).status_code == 422
    p = _mk(client)
    assert client.put(f"/api/v1/plants/{p['id']}", json={"timezone": "Nope/Zone"}).status_code == 422
    assert client.put(f"/api/v1/plants/{p['id']}", json={"timezone": "UTC"}).status_code == 200


@pytest.mark.parametrize("q,code", [("limit=-1", 422), ("limit=0", 422), ("limit=100000000", 422),
                                    ("skip=-5", 422), ("limit=500", 200)])
def test_plants_list_bounds(client, q, code):
    assert client.get(f"/api/v1/plants?{q}").status_code == code


# ── m4: batch cap + no per-row persist ──────────────────────────────────────

def test_batch_cap(client):
    p = _mk(client)
    ts = datetime.now(tz=timezone.utc).isoformat()
    too_many = [{"plant_id": p["id"], "timestamp": ts, "power_kw": 1.0}] * 1001
    assert client.post("/api/v1/scada/readings/batch", json={"readings": too_many}).status_code == 422
    ok = [{"plant_id": p["id"], "timestamp": ts, "power_kw": 1.0}] * 1000
    assert client.post("/api/v1/scada/readings/batch", json={"readings": ok}).status_code == 201


def test_batch_persists_adapter_once_per_plant(client, db_session, monkeypatch):
    from solardoctor.physics.models import Forecast
    from solardoctor.physics.registry import get_registry
    p = _mk(client)
    now = datetime.now(tz=timezone.utc).replace(microsecond=0)
    db_session.add(Forecast(plant_id=p["id"], forecast_time=now, predicted_power_kw=80.0, ml_power_kw=80.0,
                            model_name="physics_baseline"))
    db_session.commit()
    reg = get_registry()
    calls = []
    orig = reg._persist_adapter
    monkeypatch.setattr(reg, "_persist_adapter", lambda a: (calls.append(1), orig(a))[1])
    rows = [{"plant_id": p["id"], "timestamp": now.isoformat(), "power_kw": 70.0 + i, "irradiance_w_m2": 700.0}
            for i in range(5)]
    r = client.post("/api/v1/scada/readings/batch", json={"readings": rows})
    assert r.status_code == 201 and len(r.json()) == 5 and all(x["id"] for x in r.json())
    assert len(calls) == 1
    assert reg.get_online_adapter(str(p["id"])).state.samples_observed == 5


def test_batch_unknown_plant_404(client):
    ts = datetime.now(tz=timezone.utc).isoformat()
    r = client.post("/api/v1/scada/readings/batch", json={"readings": [{"plant_id": 424242, "timestamp": ts}]})
    assert r.status_code == 404


# ── m6: unique park race -> 409 ─────────────────────────────────────────────

def test_duplicate_park_link_integrity_error_is_409(client, db_session, monkeypatch):
    from solardoctor.db.models import Park
    from solardoctor.physics import plant_service
    db_session.add(Park(id="PK", name="k"))
    db_session.commit()
    assert client.post("/api/v1/plants", json={**PLANT, "park_id": "PK"}).status_code == 201
    monkeypatch.setattr(plant_service, "_check_park", lambda *a, **k: None)  # simulate losing the race
    r = client.post("/api/v1/plants", json={**PLANT, "park_id": "PK"})
    assert r.status_code == 409


# ── m7: websocket credential channels ───────────────────────────────────────

@pytest.fixture
def ws_client(client, monkeypatch):
    monkeypatch.setenv("SOLARDOCTOR_API_KEY", "k-secret")
    monkeypatch.delenv("SOLARDOCTOR_AUTH_MODE", raising=False)
    return client


def _first(ws):
    return ws.receive_json()["_source"]


def _rejected(client, url, **kw):
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as ei:
        with client.websocket_connect(url, **kw) as ws:
            ws.receive_json()
    return ei.value.code


def test_ws_credential_channels(ws_client):
    c = ws_client
    pid = c.post("/api/v1/plants", json=PLANT, headers={"Authorization": "Bearer k-secret"}).json()["id"]
    url = f"/api/v1/ws/scada/{pid}"
    assert _rejected(c, url) == 4401
    assert _rejected(c, url + "?token=wrong") == 4401
    with c.websocket_connect(url + "?token=k-secret") as ws:                       # query (legacy)
        assert _first(ws) == "stream_init"
    with c.websocket_connect(url, headers={"Authorization": "Bearer k-secret"}) as ws:  # header
        assert _first(ws) == "stream_init"
    with c.websocket_connect(url, subprotocols=["solardoctor.bearer", "k-secret"]) as ws:  # subprotocol
        assert ws.accepted_subprotocol == "solardoctor.bearer" and _first(ws) == "stream_init"
    assert _rejected(c, url, subprotocols=["solardoctor.bearer", "nope"]) == 4401
    with c.websocket_connect(url, subprotocols=["solardoctor.auth-first"]) as ws:   # first message
        ws.send_json({"type": "auth", "token": "k-secret"})
        assert _first(ws) == "stream_init"
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect) as ei:
        with c.websocket_connect(url, subprotocols=["solardoctor.auth-first"]) as ws:
            ws.send_json({"type": "auth", "token": "bad"})
            ws.receive_json()
    assert ei.value.code == 4401


# ── F2: telemetry fallback honesty ──────────────────────────────────────────

def _tel(db, pid, hours_ago=1.0, expected=80.0, actual=40.0, source="USER"):
    from datetime import timedelta
    from solardoctor.physics.models import Telemetry
    db.add(Telemetry(plant_id=pid, ts=datetime.now(tz=timezone.utc) - timedelta(hours=hours_ago),
                     p_expected_kw=expected, p_ac_kw=actual, ghi_wm2=800.0, source=source))
    db.commit()


def _diag(client, pid, **kw):
    return client.post("/api/v1/diagnosis/diagnose", json={"plant_id": pid, **kw})


def test_stale_telemetry_rejected(client, db_session):
    p = _mk(client)
    _tel(db_session, p["id"], hours_ago=90 * 24)
    r = _diag(client, p["id"])
    assert r.status_code == 422 and "last 24" in r.json()["detail"]
    assert client.get(f"/api/v1/diagnosis/plant/{p['id']}").json() == []


def test_max_age_is_configurable(client, db_session, monkeypatch):
    p = _mk(client)
    _tel(db_session, p["id"], hours_ago=30)
    assert _diag(client, p["id"]).status_code == 422
    monkeypatch.setenv("SOLARDOCTOR_DIAGNOSIS_MAX_TELEMETRY_AGE_H", "48")
    assert _diag(client, p["id"]).status_code == 200


def test_night_rows_skipped_in_favour_of_earlier_daylight_row(client, db_session):
    p = _mk(client)                       # ac 100 kW -> floor 5 kW
    _tel(db_session, p["id"], hours_ago=6, expected=90.0, actual=45.0)
    _tel(db_session, p["id"], hours_ago=0.5, expected=0.0, actual=0.0)   # latest row is night
    d = _diag(client, p["id"]).json()
    assert d["telemetry_evidence"]["expected_power_kw"] == 90.0 and d["estimated_loss_kw"] == 45.0
    only_night = _mk(client, name="N")
    _tel(db_session, only_night["id"], hours_ago=0.5, expected=1.0, actual=0.0)
    assert _diag(client, only_night["id"]).status_code == 422


def test_mixed_request_and_telemetry_rejected(client, db_session):
    p = _mk(client)
    _tel(db_session, p["id"])
    for body in ({"expected_power_kw": 100}, {"actual_power_kw": 10}):
        r = _diag(client, p["id"], **body)
        assert r.status_code == 422 and "mixing" in r.json()["detail"]


def test_simulated_telemetry_needs_opt_in_and_is_labelled(client, db_session):
    p = _mk(client)
    _tel(db_session, p["id"], source="SIMULATED")
    r = _diag(client, p["id"])
    assert r.status_code == 422 and "allow_simulated" in r.json()["detail"]
    ok = _diag(client, p["id"], allow_simulated=True)
    assert ok.status_code == 200
    d = ok.json()
    assert d["telemetry_source"] == "SIMULATED" and d["telemetry_ts"]
    assert d["telemetry_evidence"]["telemetry_source"] == "SIMULATED" and d["telemetry_evidence"]["telemetry_ts"]
    stored = client.get(f"/api/v1/diagnosis/plant/{p['id']}").json()[0]
    assert stored["telemetry_source"] == "SIMULATED"          # provenance survives persistence


def test_real_recent_telemetry_prefers_non_simulated(client, db_session):
    p = _mk(client)
    _tel(db_session, p["id"], hours_ago=3, expected=70.0, actual=35.0, source="USER")
    _tel(db_session, p["id"], hours_ago=1, expected=90.0, actual=10.0, source="SIMULATED")
    d = _diag(client, p["id"]).json()
    assert d["telemetry_source"] == "USER" and d["telemetry_evidence"]["expected_power_kw"] == 70.0


def test_request_values_do_not_touch_telemetry(client, db_session):
    p = _mk(client)
    d = _diag(client, p["id"], expected_power_kw=100, actual_power_kw=60).json()
    assert d["telemetry_ts"] is None and d["telemetry_source"] is None


# ── F4/F5: bounds ───────────────────────────────────────────────────────────

def test_bounds(client):
    assert client.get("/api/v1/plants?skip=99999999999999999999").status_code == 422
    assert client.get("/api/v1/plants?skip=1000001").status_code == 422
    assert client.post("/api/v1/plants", json={**PLANT, "capacity_kw": 1e308}).status_code == 422
    assert client.post("/api/v1/plants", json={**PLANT, "inverter_capacity_kw": 1e8}).status_code == 422
    p = _mk(client)
    assert client.put(f"/api/v1/plants/{p['id']}", json={"capacity_kw": 1e9}).status_code == 422
    for body in ({"expected_power_kw": -1, "actual_power_kw": 5}, {"expected_power_kw": 5, "actual_power_kw": -1}):
        assert _diag(client, p["id"], **body).status_code == 422
    assert client.get(f"/api/v1/diagnosis/plant/{p['id']}").json() == []
