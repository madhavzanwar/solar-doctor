"""
geometry.py — Small-area planar geometry for park layouts.

Parks span at most a few kilometres, so a local equirectangular projection
around a reference point is accurate to centimetres there and keeps panel
matching free of heavyweight GIS dependencies. Coordinates are
``{"lat", "lon"}`` dicts or ``(lat, lon)`` tuples; local frames are metres
east (x) and north (y).
"""

from __future__ import annotations

import math
from typing import Sequence

EARTH_RADIUS_M = 6_371_000.0

LatLon = tuple[float, float]
XY = tuple[float, float]


def local_to_gps(x_m: float, y_m: float, origin: dict, rotation_deg: float = 0.0) -> dict:
    """Map a point in a (possibly rotated) local metric frame to GPS.

    ``rotation_deg`` rotates the local frame counter-clockwise from east, so a
    table whose long axis points north-east uses ``rotation_deg=45``.
    """
    theta = math.radians(rotation_deg)
    east = x_m * math.cos(theta) - y_m * math.sin(theta)
    north = x_m * math.sin(theta) + y_m * math.cos(theta)
    lat0 = float(origin["lat"])
    lon0 = float(origin["lon"])
    return {
        "lat": lat0 + math.degrees(north / EARTH_RADIUS_M),
        "lon": lon0 + math.degrees(east / (EARTH_RADIUS_M * math.cos(math.radians(lat0)))),
    }


def gps_to_local(lat: float, lon: float, ref_lat: float, ref_lon: float) -> XY:
    """Metres east/north of ``(ref_lat, ref_lon)``."""
    east = math.radians(lon - ref_lon) * EARTH_RADIUS_M * math.cos(math.radians(ref_lat))
    north = math.radians(lat - ref_lat) * EARTH_RADIUS_M
    return east, north


def polygon_area_m2(points: Sequence[XY]) -> float:
    """Unsigned shoelace area of a local-metre polygon."""
    total = 0.0
    for (x1, y1), (x2, y2) in zip(points, list(points[1:]) + [points[0]]):
        total += x1 * y2 - x2 * y1
    return abs(total) / 2.0


def point_in_polygon(x: float, y: float, polygon: Sequence[XY]) -> bool:
    """Even-odd ray casting; points on an edge may fall either way."""
    inside = False
    n = len(polygon)
    for i in range(n):
        x1, y1 = polygon[i]
        x2, y2 = polygon[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            x_cross = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
            if x < x_cross:
                inside = not inside
    return inside


def distance_to_polygon_edge(x: float, y: float, polygon: Sequence[XY]) -> float:
    """Shortest distance (m) from a point to the polygon boundary."""
    best = math.inf
    n = len(polygon)
    for i in range(n):
        ax, ay = polygon[i]
        bx, by = polygon[(i + 1) % n]
        dx, dy = bx - ax, by - ay
        seg_len2 = dx * dx + dy * dy
        t = 0.0 if seg_len2 == 0 else max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / seg_len2))
        px, py = ax + t * dx, ay + t * dy
        best = min(best, math.hypot(x - px, y - py))
    return best


def metres_to_lat_deg(metres: float) -> float:
    return math.degrees(metres / EARTH_RADIUS_M)


def metres_to_lon_deg(metres: float, lat: float) -> float:
    return math.degrees(metres / (EARTH_RADIUS_M * max(math.cos(math.radians(lat)), 1e-6)))
