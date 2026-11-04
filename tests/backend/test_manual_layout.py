"""Manual park layouts for parks auto-grid cannot handle (curved rows, hillsides).

Spec §15.4 #3: auto-grid detection fails on non-rectangular parks, so an
operator-supplied layout (JSON, or GeoJSON of panel polygons) must take
precedence when one exists for the park.
"""
from __future__ import annotations

import copy
import json
import math

import pytest

from axalon.park.locator import PANEL_ID_UNKNOWN, locate_faults
from axalon.park.manual_layout import (
    LAYOUT_FORMAT,
    LayoutError,
    delete_park_layout,
    geojson_to_layout,
    load_park_layout,
    local_to_gps,
    parse_layout,
    parse_layout_upload,
    save_park_layout,
)

_R = 6_371_000.0
_ORIGIN = {"lat": 23.0300, "lon": 72.5800}


def _offset(east_m: float, north_m: float, origin: dict = _ORIGIN) -> dict:
    """GPS point ``east_m``/``north_m`` metres from ``origin``."""
    lat = origin["lat"] + math.degrees(north_m / _R)
    lon = origin["lon"] + math.degrees(east_m / (_R * math.cos(math.radians(origin["lat"]))))
    return {"lat": lat, "lon": lon}


def _curved_hillside_layout() -> dict:
    """A curved array: tables on a 60 m-radius arc, each rotated tangent to it,
    with irregular row lengths (2–5 panels). Panels are 1.0 m x 2.0 m local
    rectangles spaced 1.05 m apart inside each table."""
    tables = []
    lengths = [2, 3, 5, 4, 5, 3, 2, 4]
    for t, n_panels in enumerate(lengths):
        angle = math.radians(10 + t * 9)  # position along the arc
        anchor = _offset(60 * math.cos(angle), 60 * math.sin(angle))
        tangent_deg = math.degrees(angle) + 90
        tables.append({
            "id": f"T{t + 1:02d}",
            "georeference": {"origin": anchor, "rotation_deg": tangent_deg},
            "panels": [
                {"id": f"T{t + 1:02d}-P{p + 1}",
                 "rect": {"x": p * 1.05, "y": 0.0, "width": 1.0, "height": 2.0}}
                for p in range(n_panels)
            ],
        })
    return {
        "format": LAYOUT_FORMAT,
        "version": 1,
        "name": "Hillside curve",
        "match_tolerance_m": 0.5,
        "tables": tables,
    }


def _panel_center_gps(doc: dict, table_idx: int, panel_idx: int) -> dict:
    table = doc["tables"][table_idx]
    rect = table["panels"][panel_idx]["rect"]
    geo = table["georeference"]
    return local_to_gps(rect["x"] + rect["width"] / 2, rect["y"] + rect["height"] / 2,
                        geo["origin"], geo["rotation_deg"])


def _det(gps: dict | None) -> dict:
    return {"class": "hot-spot-high", "class_id": 10, "confidence": 0.9,
            "bbox": [0, 0, 5, 5], "severity": "CRITICAL", "gps": gps}


# ── validation ───────────────────────────────────────────────────────────────

def test_curved_layout_parses_with_irregular_rows():
    layout = parse_layout(_curved_hillside_layout())
    assert layout.total_panels == sum([2, 3, 5, 4, 5, 3, 2, 4])
    assert layout.table_count == 8
    assert layout.tolerance_m == 0.5


@pytest.mark.parametrize(
    "mutate, fragment",
    [
        (lambda d: d.update(format="nope"), "format"),
        (lambda d: d.update(version=9), "version"),
        (lambda d: d.update(tables=[]), "tables"),
        (lambda d: d["tables"][0].update(id=""), r"tables\[0\].*id"),
        (lambda d: d["tables"][1].update(id="T01"), "duplicate table"),
        (lambda d: d["tables"][0]["panels"][1].update(id="T01-P1"), "duplicate panel"),
        (lambda d: d["tables"][0]["panels"][0].update(center=_ORIGIN), "exactly one"),
        (lambda d: d["tables"][0]["panels"][0].pop("rect"), "exactly one"),
        (lambda d: d["tables"][0]["panels"][0]["rect"].update(width=0), "width"),
        (lambda d: d["tables"][0].pop("georeference"), "georeference"),
        (lambda d: d["tables"][0]["georeference"]["origin"].update(lat=123), "lat"),
        (lambda d: d["tables"][0]["panels"][0].update(
            rect=None, polygon=[_ORIGIN, _offset(1, 0)]), "3 vertices"),
        (lambda d: d["tables"][0]["panels"].__setitem__(0, {
            "id": "T01-P1", "polygon": [_ORIGIN, _offset(1, 0), _offset(2, 0)]}), "area"),
        (lambda d: d.update(match_tolerance_m=-1), "match_tolerance_m"),
        (lambda d: d.update(park_id="bad id!"), "park_id"),
    ],
)
def test_invalid_layouts_are_rejected(mutate, fragment):
    doc = _curved_hillside_layout()
    mutate(doc)
    for p in (doc["tables"][0]["panels"] if doc["tables"] else []):
        if p.get("rect", "missing") is None:
            del p["rect"]
    with pytest.raises(LayoutError, match=fragment):
        parse_layout(doc)


def test_upload_rejects_non_json():
    with pytest.raises(LayoutError, match="JSON"):
        parse_layout_upload(b"\x00not json")


# ── locator: manual layout ───────────────────────────────────────────────────

def test_locator_assigns_detection_to_the_right_curved_panel():
    # Arrange — a detection at the centre of table 5 (index 4), panel 3
    doc = _curved_hillside_layout()
    layout = parse_layout(doc).to_locator_layout()
    target = _panel_center_gps(doc, 4, 2)
    # a second detection 0.3 m inside the neighbouring panel boundary
    neighbour = _panel_center_gps(doc, 4, 3)

    # Act
    located = locate_faults([_det(target), _det(neighbour)], layout)

    # Assert
    assert located[0].panel_id == "T05-P3"
    assert located[0].confidence == pytest.approx(1.0)
    assert located[1].panel_id == "T05-P4"


def test_locator_matches_near_miss_within_tolerance_only():
    doc = _curved_hillside_layout()
    layout = parse_layout(doc).to_locator_layout()
    table = doc["tables"][0]
    geo = table["georeference"]
    # 0.3 m beyond the long edge of T01-P1 (tolerance 0.5 m), and 3 m beyond it
    near = local_to_gps(0.5, -0.3, geo["origin"], geo["rotation_deg"])
    far = local_to_gps(0.5, -3.0, geo["origin"], geo["rotation_deg"])

    located = locate_faults([_det(near), _det(far), _det(None)], layout)

    assert located[0].panel_id == "T01-P1"
    assert 0.0 < located[0].confidence < 1.0
    assert located[1].panel_id == PANEL_ID_UNKNOWN
    assert located[2].panel_id == PANEL_ID_UNKNOWN


def test_locator_supports_center_only_and_polygon_panels():
    doc = {
        "format": LAYOUT_FORMAT, "version": 1, "match_tolerance_m": 1.0,
        "tables": [{
            "id": "A",
            "panels": [
                {"id": "A-1", "center": _offset(0, 0)},
                {"id": "A-2", "polygon": [_offset(5, -1), _offset(7, -1), _offset(7, 1), _offset(5, 1)]},
            ],
        }],
    }
    layout = parse_layout(doc).to_locator_layout()

    located = locate_faults([_det(_offset(0.4, 0.2)), _det(_offset(6, 0.5))], layout)

    assert [lf.panel_id for lf in located] == ["A-1", "A-2"]


def test_locator_without_manual_mode_still_uses_auto_grid_nearest():
    layout = {"mode": "auto-grid", "panel_map": {
        "R1-C1": {"bbox_image": [0, 0, 1, 1], "center": [0, 0], "gps": _offset(0, 0)},
        "R1-C2": {"bbox_image": [0, 0, 1, 1], "center": [0, 0], "gps": _offset(3, 0)},
    }}
    located = locate_faults([_det(_offset(2.6, 0))], layout)
    assert located[0].panel_id == "R1-C2"
    assert located[0].panel_index == (0, 1)


# ── GeoJSON input ────────────────────────────────────────────────────────────

def _ring(e0, n0, e1, n1):
    pts = [_offset(e0, n0), _offset(e1, n0), _offset(e1, n1), _offset(e0, n1), _offset(e0, n0)]
    return [[p["lon"], p["lat"]] for p in pts]


def test_geojson_feature_collection_converts_to_layout():
    fc = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {"panel_id": "B-1", "table": "B"},
             "geometry": {"type": "Polygon", "coordinates": [_ring(0, 0, 1, 2)]}},
            {"type": "Feature", "properties": {"panel_id": "B-2", "table": "B"},
             "geometry": {"type": "Polygon", "coordinates": [_ring(1.1, 0, 2.1, 2)]}},
            {"type": "Feature", "id": "C-1", "properties": {"row": "C"},
             "geometry": {"type": "Point", "coordinates": [_offset(0, 10)["lon"], _offset(0, 10)["lat"]]}},
        ],
    }

    doc = geojson_to_layout(fc)
    layout = parse_layout(doc)
    located = locate_faults([_det(_offset(1.6, 1.0))], layout.to_locator_layout())

    assert doc["format"] == LAYOUT_FORMAT
    assert doc["source_format"] == "geojson"
    assert {t["id"] for t in doc["tables"]} == {"B", "C"}
    assert layout.total_panels == 3
    # closing vertex dropped, lat/lon order swapped from GeoJSON [lon, lat]
    polygon = doc["tables"][0]["panels"][0]["polygon"]
    assert len(polygon) == 4 and set(polygon[0]) == {"lat", "lon"}
    assert located[0].panel_id == "B-2"


def test_geojson_upload_is_detected_automatically():
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"id": "X-1"},
         "geometry": {"type": "Polygon", "coordinates": [_ring(0, 0, 1, 2)]}},
    ]}
    doc, layout = parse_layout_upload(json.dumps(fc).encode())
    assert doc["source_format"] == "geojson"
    assert layout.total_panels == 1


@pytest.mark.parametrize(
    "feature, fragment",
    [
        ({"type": "Feature", "properties": {},
          "geometry": {"type": "Polygon", "coordinates": [_ring(0, 0, 1, 2)]}}, "id"),
        ({"type": "Feature", "properties": {"id": "L"},
          "geometry": {"type": "LineString", "coordinates": [[0, 0], [1, 1]]}}, "Polygon or Point"),
    ],
)
def test_geojson_invalid_features_rejected(feature, fragment):
    with pytest.raises(LayoutError, match=fragment):
        geojson_to_layout({"type": "FeatureCollection", "features": [feature]})


def test_geojson_empty_collection_rejected():
    with pytest.raises(LayoutError, match="features"):
        geojson_to_layout({"type": "FeatureCollection", "features": []})


# ── persistence ──────────────────────────────────────────────────────────────

def test_save_load_delete_roundtrip(db_session):
    doc = _curved_hillside_layout()

    save_park_layout(db_session, "HILL_01", doc)
    loaded = load_park_layout(db_session, "HILL_01")

    assert loaded is not None
    assert loaded.total_panels == parse_layout(doc).total_panels
    assert loaded.park_id == "HILL_01"
    assert load_park_layout(db_session, "OTHER") is None
    assert delete_park_layout(db_session, "HILL_01") is True
    assert load_park_layout(db_session, "HILL_01") is None
    assert delete_park_layout(db_session, "HILL_01") is False


# ── orchestrator: manual layout wins, auto-grid is the fallback ──────────────

class _StubGridDetector:
    def __init__(self):
        self.calls = 0

    def build_layout(self, rgb_images, gps_coords):
        self.calls += 1
        return {"mode": "auto-grid", "total_panels": 1, "rows": 1,
                "panel_map": {"R1-C1": {"bbox_image": [0, 0, 1, 1], "center": [0, 0], "gps": None}}}


def _bare_orchestrator():
    from axalon.pipeline.orchestrator import InspectionOrchestrator

    orch = object.__new__(InspectionOrchestrator)
    orch.layout_detector = _StubGridDetector()
    return orch


def test_orchestrator_prefers_stored_manual_layout(db_session):
    save_park_layout(db_session, "HILL_02", _curved_hillside_layout())
    orch = _bare_orchestrator()

    def _must_not_load():
        raise AssertionError("RGB frames loaded although a manual layout exists")

    layout = orch._resolve_layout("HILL_02", load_rgb=_must_not_load)

    assert layout["mode"] == "manual"
    assert orch.layout_detector.calls == 0


def test_orchestrator_falls_back_to_auto_grid_without_manual_layout(db_session):
    orch = _bare_orchestrator()

    layout = orch._resolve_layout("FLAT_01", load_rgb=lambda: ([object()], [None]))
    none_layout = orch._resolve_layout("FLAT_01", load_rgb=lambda: ([], []))

    assert layout["mode"] == "auto-grid"
    assert none_layout is None


def test_orchestrator_does_not_silently_fall_back_on_corrupt_manual_layout(db_session):
    from axalon.core.app_config import set_config

    set_config(db_session, "park_layout:BROKEN_01", json.dumps({"format": "axalon-park-layout"}))
    orch = _bare_orchestrator()

    with pytest.raises(LayoutError):
        orch._resolve_layout("BROKEN_01", load_rgb=lambda: ([object()], [None]))


def test_manual_panel_id_not_overwritten_by_pixel_fallback():
    from axalon.pipeline.orchestrator import assign_panel_ids

    doc = _curved_hillside_layout()
    layout = parse_layout(doc).to_locator_layout()
    dets = [_det(_panel_center_gps(doc, 0, 0)), _det(None)]

    out = assign_panel_ids(dets, layout)

    assert out[0]["panel_id"] == "T01-P1"
    assert out[1]["panel_id"] == "R?-C?"


# ── API ──────────────────────────────────────────────────────────────────────

def test_api_layout_upload_get_delete(client):
    park = "API_HILL"
    assert client.get(f"/park/{park}/layout").json()["mode"] == "auto"

    payload = json.dumps(_curved_hillside_layout()).encode()
    r = client.post(f"/park/{park}/layout", files={"file": ("layout.json", payload, "application/json")})
    assert r.status_code == 201, r.text
    assert r.json()["summary"]["total_panels"] == 28

    body = client.get(f"/park/{park}/layout").json()
    assert body["mode"] == "manual"
    assert body["summary"]["tables"] == 8
    assert "layout" not in body or body["layout"] is None
    full = client.get(f"/park/{park}/layout?full=true").json()
    assert full["layout"]["tables"][0]["id"] == "T01"

    assert client.delete(f"/park/{park}/layout").status_code == 200
    assert client.get(f"/park/{park}/layout").json()["mode"] == "auto"
    assert client.delete(f"/park/{park}/layout").status_code == 404


def test_api_layout_upload_rejects_invalid_and_mismatched_park(client):
    bad = copy.deepcopy(_curved_hillside_layout())
    bad["tables"] = []
    r = client.post("/park/API_BAD/layout",
                    files={"file": ("l.json", json.dumps(bad).encode(), "application/json")})
    assert r.status_code == 400
    assert "tables" in r.json()["detail"]

    other = _curved_hillside_layout()
    other["park_id"] = "SOMEWHERE_ELSE"
    r = client.post("/park/API_BAD/layout",
                    files={"file": ("l.json", json.dumps(other).encode(), "application/json")})
    assert r.status_code == 400
    assert "park_id" in r.json()["detail"]


def test_api_layout_accepts_geojson(client):
    fc = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"panel_id": "G-1"},
         "geometry": {"type": "Polygon", "coordinates": [_ring(0, 0, 1, 2)]}},
    ]}
    r = client.post("/park/API_GEO/layout",
                    files={"file": ("panels.geojson", json.dumps(fc).encode(), "application/geo+json")})
    assert r.status_code == 201, r.text
    assert r.json()["summary"]["source_format"] == "geojson"
