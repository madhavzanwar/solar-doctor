"""
manual_layout.py — Operator-defined panel layouts for irregular parks.

Auto-grid detection (layout.py) clusters panels into straight rows, which
breaks on curved arrays and hillside installations (spec §15.4 #3). For those
parks an operator uploads the real geometry instead, and the locator matches
detections to it (point-in-polygon, then nearest panel within a tolerance).

Layout JSON (``format: "axalon-park-layout"``, version 1)::

    {
      "format": "axalon-park-layout",
      "version": 1,
      "park_id": "HILL_01",              # optional; must match the URL when uploaded
      "name": "Hillside block B",        # optional
      "match_tolerance_m": 1.0,          # optional (default 1.0): how far outside a
                                         #   polygon / from a centre a GPS hit may land
      "georeference": {                  # optional default frame for "rect" panels
        "origin": {"lat": 23.03, "lon": 72.58},
        "rotation_deg": 0                # local x-axis, counter-clockwise from east
      },
      "tables": [                        # tables/rows; lengths may differ
        {
          "id": "T01",
          "georeference": {...},         # optional per-table frame → rotated tables
          "panels": [                    # exactly ONE geometry per panel:
            {"id": "T01-P1", "polygon": [{"lat": .., "lon": ..}, ...]},   # >= 3 vertices
            {"id": "T01-P2", "center": {"lat": .., "lon": ..}},           # point only
            {"id": "T01-P3", "rect": {"x": 0, "y": 0, "width": 1.0, "height": 2.0}}
                                         # metres in the table (or top-level) frame
          ]
        }
      ]
    }

A GeoJSON FeatureCollection of panel Polygons (or Points) is also accepted and
converted: panel id from ``properties.panel_id`` / ``properties.id`` / feature
``id``; table from ``properties.table`` / ``table_id`` / ``row`` (default "T1").

Layouts are stored as JSON in the ``app_config`` key/value table under
``park_layout:<park_id>`` — a Text column that behaves the same on SQLite and
PostgreSQL, so no migration is needed.
"""

from __future__ import annotations

import copy
import json
import math
import re
from dataclasses import dataclass
from typing import Any

from ml.src.utils import get_logger

from axalon.park.geometry import gps_to_local, local_to_gps, polygon_area_m2

__all__ = [
    "LAYOUT_FORMAT", "LayoutError", "LayoutPanel", "ParkLayout",
    "delete_park_layout", "geojson_to_layout", "load_park_layout", "local_to_gps",
    "parse_layout", "parse_layout_upload", "save_park_layout",
]

logger = get_logger("axalon.manual_layout")

LAYOUT_FORMAT = "axalon-park-layout"
LAYOUT_VERSION = 1
LAYOUT_MODE = "manual"
DEFAULT_TOLERANCE_M = 1.0
MAX_TOLERANCE_M = 50.0
MAX_PANELS = 200_000
MIN_PANEL_AREA_M2 = 0.01
SOURCE_FORMATS = ("layout", "geojson")
_CONFIG_KEY_PREFIX = "park_layout:"
_PARK_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_GEOMETRY_KEYS = ("polygon", "center", "rect")


class LayoutError(ValueError):
    """Raised when a park layout document is invalid."""


@dataclass(frozen=True)
class LayoutPanel:
    id: str
    table_id: str
    center: tuple[float, float]                         # (lat, lon)
    polygon: tuple[tuple[float, float], ...] | None     # (lat, lon) vertices, open ring


@dataclass(frozen=True)
class ParkLayout:
    park_id: str | None
    name: str | None
    tolerance_m: float
    table_count: int
    panels: tuple[LayoutPanel, ...]
    source_format: str = "layout"

    @property
    def total_panels(self) -> int:
        return len(self.panels)

    def summary(self) -> dict:
        return {
            "park_id": self.park_id,
            "name": self.name,
            "tables": self.table_count,
            "total_panels": self.total_panels,
            "match_tolerance_m": self.tolerance_m,
            "source_format": self.source_format,
        }

    def to_locator_layout(self) -> dict:
        """Layout dict in the shape ``locator.locate_faults`` consumes."""
        return {
            "mode": LAYOUT_MODE,
            "total_panels": self.total_panels,
            "rows": self.table_count,
            "match_tolerance_m": self.tolerance_m,
            "panel_map": {
                p.id: {
                    "gps": {"lat": p.center[0], "lon": p.center[1]},
                    "polygon": [list(v) for v in p.polygon] if p.polygon else None,
                    "table": p.table_id,
                    "bbox_image": None,
                    "center": None,
                }
                for p in self.panels
            },
        }


# ── field parsers ────────────────────────────────────────────────────────────

def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _parse_gps(value: Any, where: str) -> tuple[float, float]:
    if not isinstance(value, dict):
        raise LayoutError(f"{where}: expected {{'lat': .., 'lon': ..}}")
    lat, lon = value.get("lat"), value.get("lon")
    if not _is_number(lat) or not -90 <= lat <= 90:
        raise LayoutError(f"{where}: 'lat' must be a number in [-90, 90]")
    if not _is_number(lon) or not -180 <= lon <= 180:
        raise LayoutError(f"{where}: 'lon' must be a number in [-180, 180]")
    return float(lat), float(lon)


def _parse_id(value: Any, where: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LayoutError(f"{where}: 'id' must be a non-empty string")
    return value.strip()


def _parse_georeference(value: Any, where: str) -> dict | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise LayoutError(f"{where}.georeference: must be an object")
    lat, lon = _parse_gps(value.get("origin"), f"{where}.georeference.origin")
    rotation = value.get("rotation_deg", 0.0)
    if not _is_number(rotation):
        raise LayoutError(f"{where}.georeference: 'rotation_deg' must be a number")
    return {"origin": {"lat": lat, "lon": lon}, "rotation_deg": float(rotation)}


def _polygon_from_vertices(vertices: list[tuple[float, float]], where: str) -> tuple:
    if len(vertices) > 3 and vertices[0] == vertices[-1]:
        vertices = vertices[:-1]  # closed ring → open ring
    if len(vertices) < 3:
        raise LayoutError(f"{where}: polygon needs at least 3 vertices")
    ref_lat, ref_lon = vertices[0]
    local = [gps_to_local(lat, lon, ref_lat, ref_lon) for lat, lon in vertices]
    if polygon_area_m2(local) < MIN_PANEL_AREA_M2:
        raise LayoutError(f"{where}: polygon area is (near) zero — vertices are collinear")
    return tuple(vertices)


def _centroid(vertices: tuple[tuple[float, float], ...]) -> tuple[float, float]:
    return (sum(v[0] for v in vertices) / len(vertices),
            sum(v[1] for v in vertices) / len(vertices))


def _parse_rect(rect: Any, frame: dict | None, where: str) -> tuple:
    if not isinstance(rect, dict):
        raise LayoutError(f"{where}: 'rect' must be an object with x, y, width, height")
    for key in ("x", "y", "width", "height"):
        if not _is_number(rect.get(key)):
            raise LayoutError(f"{where}: rect '{key}' must be a number")
    if rect["width"] <= 0 or rect["height"] <= 0:
        raise LayoutError(f"{where}: rect 'width' and 'height' must be > 0")
    if frame is None:
        raise LayoutError(
            f"{where}: 'rect' panels need a georeference on the table or the layout"
        )
    x, y, w, h = rect["x"], rect["y"], rect["width"], rect["height"]
    corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    points = [local_to_gps(cx, cy, frame["origin"], frame["rotation_deg"]) for cx, cy in corners]
    return tuple((p["lat"], p["lon"]) for p in points)


def _parse_panel(raw: Any, table_id: str, frame: dict | None, where: str) -> LayoutPanel:
    if not isinstance(raw, dict):
        raise LayoutError(f"{where}: panel must be an object")
    panel_id = _parse_id(raw.get("id"), where)
    present = [k for k in _GEOMETRY_KEYS if raw.get(k) is not None]
    if len(present) != 1:
        raise LayoutError(f"{where}: panel needs exactly one of 'polygon', 'center', 'rect'")
    kind = present[0]
    if kind == "center":
        return LayoutPanel(panel_id, table_id, _parse_gps(raw["center"], f"{where}.center"), None)
    if kind == "rect":
        polygon = _polygon_from_vertices(list(_parse_rect(raw["rect"], frame, where)), where)
    else:
        vertices = raw["polygon"]
        if not isinstance(vertices, list):
            raise LayoutError(f"{where}: 'polygon' must be a list of {{lat, lon}}")
        polygon = _polygon_from_vertices(
            [_parse_gps(v, f"{where}.polygon[{i}]") for i, v in enumerate(vertices)], where
        )
    return LayoutPanel(panel_id, table_id, _centroid(polygon), polygon)


def _parse_header(doc: Any, park_id: str | None) -> tuple[str | None, float, str]:
    if not isinstance(doc, dict):
        raise LayoutError("layout must be a JSON object")
    if doc.get("format") != LAYOUT_FORMAT:
        raise LayoutError(f"'format' must be '{LAYOUT_FORMAT}'")
    if doc.get("version") != LAYOUT_VERSION:
        raise LayoutError(f"unsupported 'version' (expected {LAYOUT_VERSION})")
    doc_park = doc.get("park_id")
    if doc_park is not None and (not isinstance(doc_park, str) or not _PARK_ID_RE.match(doc_park)):
        raise LayoutError("'park_id' may only contain letters, digits, '-' and '_' (max 64)")
    if park_id is not None and doc_park is not None and doc_park != park_id:
        raise LayoutError(f"layout 'park_id' {doc_park!r} does not match park {park_id!r}")
    tolerance = doc.get("match_tolerance_m", DEFAULT_TOLERANCE_M)
    if not _is_number(tolerance) or not 0 <= tolerance <= MAX_TOLERANCE_M:
        raise LayoutError(f"'match_tolerance_m' must be a number in [0, {MAX_TOLERANCE_M}]")
    source = doc.get("source_format", "layout")
    if source not in SOURCE_FORMATS:
        raise LayoutError(f"'source_format' must be one of {SOURCE_FORMATS}")
    name = doc.get("name")
    if name is not None and not isinstance(name, str):
        raise LayoutError("'name' must be a string")
    return park_id or doc_park, float(tolerance), source


def parse_layout(doc: Any, park_id: str | None = None) -> ParkLayout:
    """Validate a layout document and resolve every panel to GPS geometry."""
    resolved_park, tolerance, source = _parse_header(doc, park_id)
    default_frame = _parse_georeference(doc.get("georeference"), "layout")

    tables = doc.get("tables")
    if not isinstance(tables, list) or not tables:
        raise LayoutError("'tables' must be a non-empty list")

    panels: list[LayoutPanel] = []
    table_ids: set[str] = set()
    panel_ids: set[str] = set()
    for t_idx, table in enumerate(tables):
        where = f"tables[{t_idx}]"
        if not isinstance(table, dict):
            raise LayoutError(f"{where}: table must be an object")
        table_id = _parse_id(table.get("id"), where)
        if table_id in table_ids:
            raise LayoutError(f"{where}: duplicate table id {table_id!r}")
        table_ids.add(table_id)
        frame = _parse_georeference(table.get("georeference"), where) or default_frame
        raw_panels = table.get("panels")
        if not isinstance(raw_panels, list) or not raw_panels:
            raise LayoutError(f"{where}: 'panels' must be a non-empty list")
        for p_idx, raw in enumerate(raw_panels):
            panel = _parse_panel(raw, table_id, frame, f"{where}.panels[{p_idx}]")
            if panel.id in panel_ids:
                raise LayoutError(f"{where}.panels[{p_idx}]: duplicate panel id {panel.id!r}")
            panel_ids.add(panel.id)
            panels.append(panel)
            if len(panels) > MAX_PANELS:
                raise LayoutError(f"layout exceeds {MAX_PANELS} panels")

    return ParkLayout(
        park_id=resolved_park,
        name=doc.get("name"),
        tolerance_m=tolerance,
        table_count=len(tables),
        panels=tuple(panels),
        source_format=source,
    )


# ── GeoJSON input ────────────────────────────────────────────────────────────

def _ring_to_gps(ring: Any, where: str) -> list[dict]:
    if not isinstance(ring, list):
        raise LayoutError(f"{where}: polygon ring must be a list of [lon, lat]")
    out = []
    for i, pos in enumerate(ring):
        if not isinstance(pos, list) or len(pos) < 2:
            raise LayoutError(f"{where}: position {i} must be [lon, lat]")
        out.append({"lat": pos[1], "lon": pos[0]})
    if len(out) > 1 and out[0] == out[-1]:
        out = out[:-1]
    return out


def _feature_geometry(geometry: Any, where: str) -> dict:
    gtype = geometry.get("type") if isinstance(geometry, dict) else None
    coords = geometry.get("coordinates") if isinstance(geometry, dict) else None
    if gtype == "MultiPolygon" and isinstance(coords, list) and len(coords) == 1:
        gtype, coords = "Polygon", coords[0]
    if gtype == "Polygon" and isinstance(coords, list) and coords:
        return {"polygon": _ring_to_gps(coords[0], where)}
    if gtype == "Point" and isinstance(coords, list) and len(coords) >= 2:
        return {"center": {"lat": coords[1], "lon": coords[0]}}
    raise LayoutError(f"{where}: geometry must be Polygon or Point (got {gtype!r})")


def geojson_to_layout(fc: Any, park_id: str | None = None) -> dict:
    """Convert a GeoJSON FeatureCollection of panels into a layout document."""
    if not isinstance(fc, dict) or fc.get("type") != "FeatureCollection":
        raise LayoutError("GeoJSON input must be a FeatureCollection")
    features = fc.get("features")
    if not isinstance(features, list) or not features:
        raise LayoutError("GeoJSON 'features' must be a non-empty list")

    tables: dict[str, list[dict]] = {}
    for i, feature in enumerate(features):
        where = f"features[{i}]"
        if not isinstance(feature, dict):
            raise LayoutError(f"{where}: must be a Feature object")
        props = feature.get("properties") or {}
        raw_id = props.get("panel_id") or props.get("id") or feature.get("id")
        if raw_id is None or not str(raw_id).strip():
            raise LayoutError(
                f"{where}: panel id missing (properties.panel_id, properties.id or feature id)"
            )
        table = props.get("table") or props.get("table_id") or props.get("row") or "T1"
        panel = {"id": str(raw_id).strip(), **_feature_geometry(feature.get("geometry"), where)}
        tables.setdefault(str(table), []).append(panel)

    doc: dict[str, Any] = {
        "format": LAYOUT_FORMAT,
        "version": LAYOUT_VERSION,
        "source_format": "geojson",
        "tables": [{"id": tid, "panels": panels} for tid, panels in tables.items()],
    }
    if park_id:
        doc["park_id"] = park_id
    if isinstance(fc.get("name"), str):
        doc["name"] = fc["name"]
    if fc.get("match_tolerance_m") is not None:
        doc["match_tolerance_m"] = fc["match_tolerance_m"]
    return doc


def parse_layout_upload(payload: bytes | str, park_id: str | None = None) -> tuple[dict, ParkLayout]:
    """Decode an uploaded layout (layout JSON or GeoJSON) → (canonical doc, layout)."""
    try:
        doc = json.loads(payload)
    except (ValueError, UnicodeDecodeError) as exc:
        raise LayoutError(f"layout is not valid JSON: {exc}") from None
    if isinstance(doc, dict) and doc.get("type") == "FeatureCollection":
        doc = geojson_to_layout(doc)
    layout = parse_layout(doc, park_id)
    canonical = copy.deepcopy(doc)
    canonical.setdefault("source_format", layout.source_format)
    if park_id:
        canonical["park_id"] = park_id
    return canonical, layout


# ── persistence (app_config key/value) ───────────────────────────────────────

def _config_key(park_id: str) -> str:
    if not _PARK_ID_RE.match(park_id or ""):
        raise LayoutError("invalid park_id")
    return f"{_CONFIG_KEY_PREFIX}{park_id}"


def save_park_layout(session, park_id: str, doc: dict) -> ParkLayout:
    from axalon.core.app_config import set_config

    layout = parse_layout(doc, park_id)
    stored = {**copy.deepcopy(doc), "park_id": park_id}
    set_config(session, _config_key(park_id), json.dumps(stored, separators=(",", ":")))
    logger.info("Saved manual layout for %s: %d panels", park_id, layout.total_panels)
    return layout


def load_park_layout_doc(session, park_id: str) -> dict | None:
    from axalon.core.app_config import get_config

    raw = get_config(session, _config_key(park_id))
    return json.loads(raw) if raw else None


def load_park_layout(session, park_id: str) -> ParkLayout | None:
    """The stored manual layout for a park, or ``None`` when it uses auto-grid.

    Raises LayoutError if a stored layout no longer validates — callers must
    surface that rather than silently localising against auto-grid.
    """
    doc = load_park_layout_doc(session, park_id)
    return parse_layout(doc, park_id) if doc is not None else None


def delete_park_layout(session, park_id: str) -> bool:
    from axalon.core.app_config import delete_config

    return delete_config(session, _config_key(park_id))
