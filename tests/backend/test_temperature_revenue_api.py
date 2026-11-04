"""Temperature (max/ΔT) and revenue-loss fields surfaced through the API.

Temperatures are nullable: images without a `_temp.raw` companion have none,
so every temperature key must be present but None rather than missing.
"""
from types import SimpleNamespace

import pytest

from axalon.db.models import Detection, Inspection, Park

TEMPS = {
    "min_temp": 31.5,
    "max_temp": 72.25,
    "avg_temp": 44.1,
    "reference_temp": 35.0,
    "delta_t_measured": 37.25,
    "delta_t_normalized": 46.56,
}


def test_serialize_detection_temps_present():
    from axalon.api.serializers import _serialize_detection_temps

    row = SimpleNamespace(**TEMPS)
    assert _serialize_detection_temps(row) == TEMPS


def test_serialize_detection_temps_absent_are_none():
    from axalon.api.serializers import _serialize_detection_temps

    row = SimpleNamespace(**{k: None for k in TEMPS})
    out = _serialize_detection_temps(row)
    assert set(out) == set(TEMPS)
    assert all(v is None for v in out.values())


def test_serialize_detection_temps_accepts_dicts_missing_keys():
    from axalon.api.serializers import _serialize_detection_temps

    out = _serialize_detection_temps({"max_temp": 50.0})
    assert out["max_temp"] == 50.0
    assert out["delta_t_measured"] is None


def _seed(session, park_id="PARK_T", flight_date="2026-06-01", insp_suffix="1"):
    if session.query(Park).filter_by(id=park_id).first() is None:
        session.add(Park(id=park_id, name=f"Park {park_id}", rows=2, cols=2))
        session.flush()
    insp = Inspection(id=f"INSP-{park_id}-{insp_suffix}", park_id=park_id, flight_date=flight_date)
    session.add(insp)
    session.flush()
    return insp


def test_grid_detections_carry_temperatures(client, db_session):
    insp = _seed(db_session)
    db_session.add(Detection(inspection_id=insp.id, panel_id="R1-C1", severity="CRITICAL",
                             class_="hot-spot-high", confidence=0.9, **TEMPS))
    db_session.add(Detection(inspection_id=insp.id, panel_id="R1-C2", severity="LOW",
                             class_="soiling", confidence=0.6))
    db_session.commit()

    body = client.get("/park/PARK_T/grid").json()
    by_panel = {p["panel_id"]: p for p in body["panels"]}
    hot = by_panel["R1-C1"]["detections"][0]
    for key, val in TEMPS.items():
        assert hot[key] == pytest.approx(val)
    cold = by_panel["R1-C2"]["detections"][0]
    for key in TEMPS:
        assert key in cold and cold[key] is None


def test_park_summary_reports_revenue_loss_per_inspection(client, db_session):
    insp = _seed(db_session)
    # 2 distinct known panels at CRITICAL/HIGH; LOW and unknown panels don't count.
    for panel, sev in [("R1-C1", "CRITICAL"), ("R1-C1", "HIGH"), ("R1-C2", "HIGH"),
                       ("R2-C1", "LOW"), ("R?-C?", "CRITICAL")]:
        db_session.add(Detection(inspection_id=insp.id, panel_id=panel, severity=sev, class_="cell"))
    db_session.commit()

    from axalon.api.support.revenue import load_economics
    from axalon.reporting.report import compute_revenue_loss

    expected = compute_revenue_loss(
        [{"panel_id": "R1-C1", "severity": "CRITICAL"}, {"panel_id": "R1-C2", "severity": "HIGH"}],
        load_economics(),
    )
    assert expected > 0

    body = client.get("/park/PARK_T").json()
    row = body["inspections"][0]
    assert row["revenue_loss_usd"] == pytest.approx(expected)
    assert row["revenue_currency"] == "USD"


def test_park_summary_revenue_loss_zero_without_serious_faults(client, db_session):
    insp = _seed(db_session)
    db_session.add(Detection(inspection_id=insp.id, panel_id="R1-C1", severity="LOW", class_="soiling"))
    db_session.commit()
    row = client.get("/park/PARK_T").json()["inspections"][0]
    assert row["revenue_loss_usd"] == 0


def test_overview_reports_latest_inspection_revenue_loss(client, db_session):
    old = _seed(db_session, flight_date="2026-05-01", insp_suffix="old")
    for panel in ["R1-C1", "R1-C2", "R2-C1"]:
        db_session.add(Detection(inspection_id=old.id, panel_id=panel, severity="CRITICAL", class_="cell"))
    new = _seed(db_session, flight_date="2026-06-01", insp_suffix="new")
    db_session.add(Detection(inspection_id=new.id, panel_id="R1-C1", severity="HIGH", class_="cell"))
    db_session.add(Park(id="PARK_EMPTY", name="Empty"))
    db_session.commit()

    from axalon.api.support.revenue import load_economics
    from axalon.reporting.report import compute_revenue_loss

    expected = compute_revenue_loss([{"panel_id": "R1-C1", "severity": "HIGH"}], load_economics())

    bundles = {b["park"]["id"]: b for b in client.get("/analytics/overview").json()}
    assert bundles["PARK_T"]["revenue_loss_usd"] == pytest.approx(expected)
    assert bundles["PARK_T"]["revenue_currency"] == "USD"
    assert bundles["PARK_EMPTY"]["revenue_loss_usd"] is None


def test_load_economics_reads_settings_and_tolerates_missing_file(tmp_path):
    from axalon.api.support.revenue import load_economics

    cfg = tmp_path / "settings.yaml"
    cfg.write_text("economics:\n  cost_per_kwh_usd: 0.12\n")
    assert load_economics(cfg)["cost_per_kwh_usd"] == 0.12

    assert load_economics(tmp_path / "missing.yaml") == {}
