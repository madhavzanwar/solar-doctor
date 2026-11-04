"""Unit tests for trend and recurring-fault aggregators."""
from types import SimpleNamespace

from axalon.park.recurring import build_recurring
from axalon.park.trend import build_trend


def _row(id_, date, critical, high, medium, low):
    return SimpleNamespace(
        id=id_,
        flight_date=date,
        critical_count=critical,
        high_count=high,
        medium_count=medium,
        low_count=low,
    )


def test_build_trend_returns_sorted_list():
    rows = [
        _row("b2", "2026-05-07", 2, 4, 10, 6),
        _row("b1", "2026-04-22", 3, 5, 12, 4),
        _row("b3", "2026-05-22", 5, 8, 15, 3),
    ]
    result = build_trend(rows)
    assert [r["inspection_id"] for r in result] == ["b1", "b2", "b3"]


def test_build_trend_maps_severity_counts():
    rows = [_row("b1", "2026-04-22", 1, 2, 3, 4)]
    result = build_trend(rows)
    assert result[0] == {
        "inspection_id": "b1",
        "date": "2026-04-22",
        "CRITICAL": 1,
        "HIGH": 2,
        "MEDIUM": 3,
        "LOW": 4,
    }


def test_build_trend_handles_null_counts():
    rows = [_row("b1", "2026-04-22", None, None, None, None)]
    result = build_trend(rows)
    assert result[0]["CRITICAL"] == 0
    assert result[0]["HIGH"] == 0


def test_build_trend_empty_input():
    assert build_trend([]) == []


def _rec_row(panel_id, inspection_count, sev_rank, classes, first_seen, last_seen):
    return SimpleNamespace(
        panel_id=panel_id,
        inspection_count=inspection_count,
        sev_rank=sev_rank,
        classes=classes,
        first_seen=first_seen,
        last_seen=last_seen,
    )


def test_build_recurring_maps_fields():
    rows = [_rec_row("R2-C3", 3, 4, "hot-spot-low,hot-spot-high", "2026-04-22", "2026-05-22")]
    result = build_recurring(rows)
    assert result[0] == {
        "panel_id": "R2-C3",
        "inspection_count": 3,
        "worst_severity": "CRITICAL",
        "classes": ["hot-spot-low", "hot-spot-high"],
        "first_seen": "2026-04-22",
        "last_seen": "2026-05-22",
    }


def test_build_recurring_dedupes_classes():
    rows = [_rec_row("R1-C1", 2, 2, "soiling,soiling", "2026-04-22", "2026-05-07")]
    result = build_recurring(rows)
    assert result[0]["classes"] == ["soiling"]


def test_build_recurring_empty_input():
    assert build_recurring([]) == []


def test_build_recurring_severity_rank_mapping():
    rows = [_rec_row("R1-C1", 2, 3, "hot-spot-low", "2026-04-22", "2026-05-07")]
    assert build_recurring(rows)[0]["worst_severity"] == "HIGH"
