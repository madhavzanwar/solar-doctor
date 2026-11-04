"""
geo.py — GPS/EXIF extraction and geospatial coordinate conversion.

Converts image pixel coordinates → real-world GPS coordinates using
drone altitude, camera specs, or orthomosaic geotransform.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

import numpy as np

# DJI writes yaw into XMP either as an attribute (drone-dji:GimbalYawDegree="-95.4")
# or as an element (<drone-dji:GimbalYawDegree>-95.4</...>). Gimbal yaw is the
# camera's direction; flight yaw is the airframe's and only a fallback.
_DJI_YAW_TAGS = ("GimbalYawDegree", "FlightYawDegree")
_NUMBER = r"([+-]?\d+(?:\.\d+)?)"


def parse_dji_xmp_heading(xmp: bytes | str) -> float | None:
    """Return camera heading in [0, 360) from DJI XMP metadata, or None.

    Heading is degrees clockwise from true north that the top of the image faces.
    """
    text = xmp.decode("utf-8", errors="ignore") if isinstance(xmp, bytes) else xmp
    for tag in _DJI_YAW_TAGS:
        match = re.search(
            rf'drone-dji:{tag}\s*=\s*"\s*{_NUMBER}\s*"|<drone-dji:{tag}>\s*{_NUMBER}\s*<',
            text,
        )
        if match:
            return float(match.group(1) or match.group(2)) % 360.0
    return None


def _exif_img_direction(gps: dict) -> float | None:
    """Return EXIF GPSImgDirection (tag 17) in [0, 360), or None."""
    raw = gps.get(17)
    if raw is None:
        return None
    try:
        value = raw[0] / raw[1] if isinstance(raw, tuple) else float(raw)
    except (TypeError, ZeroDivisionError, IndexError):
        return None
    return value % 360.0


def extract_gps_exif(image_path: str | Path) -> dict | None:
    """Extract GPS data from JPEG EXIF metadata.

    Returns:
        {"lat": float, "lon": float, "alt": float} or None if no GPS data.
        Adds "heading" (degrees clockwise from true north that the image top
        faces) when DJI XMP yaw or EXIF GPSImgDirection is present.
    """
    try:
        import piexif
        from PIL import Image

        img = Image.open(str(image_path))
        exif_data = img.info.get("exif", b"")
        if not exif_data:
            return None

        exif_dict = piexif.load(exif_data)
        gps = exif_dict.get("GPS", {})
        if not gps:
            return None

        def _dms_to_decimal(dms, ref):
            d, m, s = [(n / d) for n, d in dms]
            decimal = d + m / 60 + s / 3600
            if ref in (b"S", b"W"):
                decimal = -decimal
            return decimal

        lat = _dms_to_decimal(gps.get(2, []), gps.get(1, b"N"))
        lon = _dms_to_decimal(gps.get(4, []), gps.get(3, b"E"))
        alt_raw = gps.get(6, (0, 1))
        alt = alt_raw[0] / alt_raw[1] if isinstance(alt_raw, tuple) else float(alt_raw)

        result = {"lat": lat, "lon": lon, "alt": alt}

        # XMP sits in a plain-text APP1 segment, so a byte scan finds it without
        # depending on Pillow's XMP support. DJI XMP wins over GPSImgDirection.
        heading = parse_dji_xmp_heading(Path(image_path).read_bytes())
        if heading is None:
            heading = _exif_img_direction(gps)
        if heading is not None:
            result["heading"] = heading

        return result

    except Exception:
        return None


def compute_gsd(
    altitude_m: float,
    focal_length_mm: float = 13.0,
    sensor_width_mm: float = 17.3,
    image_width_px: int = 640,
) -> float:
    """Compute Ground Sampling Distance in cm/pixel.

    GSD = (altitude_m * sensor_width_mm * 100) / (focal_length_mm * image_width_px)

    Default values suit common drone thermal cameras.
    """
    return (altitude_m * sensor_width_mm * 100) / (focal_length_mm * image_width_px)


def pixel_to_gps(
    px: int,
    py: int,
    image_width: int,
    image_height: int,
    image_gps: dict,
    gsd_cm_per_px: float,
    heading_deg: float = 0.0,
) -> dict:
    """Convert a pixel coordinate to GPS.

    Assumes the image GPS (from EXIF) represents the image CENTER and the
    camera points straight down (nadir).

    Args:
        px, py:       Pixel coordinate (x right, y down).
        image_width, image_height: Image dimensions in pixels.
        image_gps:    {"lat": float, "lon": float} of image center.
        gsd_cm_per_px: Ground sampling distance in cm/pixel.
        heading_deg:  Degrees clockwise from true north that the TOP of the
                      image faces. 0 = north-up (previous behaviour).

    Returns:
        {"lat": float, "lon": float}
    """
    # Pixel offset from image center
    dx_px = px - image_width / 2
    dy_px = py - image_height / 2

    # Convert to meters in the image frame: right = +x, up = -y
    right_m = dx_px * gsd_cm_per_px / 100.0
    up_m = -dy_px * gsd_cm_per_px / 100.0

    # Rotate image frame → ground (east, north). The image top points along
    # (sin h, cos h) and the image right along (cos h, -sin h).
    h = math.radians(heading_deg)
    east_m = right_m * math.cos(h) + up_m * math.sin(h)
    north_m = -right_m * math.sin(h) + up_m * math.cos(h)

    # Earth radius (WGS84 mean)
    R = 6_371_000.0

    lat0 = math.radians(image_gps["lat"])
    lon0 = math.radians(image_gps["lon"])

    new_lat = math.degrees(lat0 + north_m / R)
    new_lon = math.degrees(lon0 + east_m / (R * math.cos(lat0)))

    return {"lat": new_lat, "lon": new_lon}


def detection_to_gps(
    bbox: list[int],
    image_width: int,
    image_height: int,
    image_gps: dict,
    altitude_m: float,
    focal_length_mm: float = 13.0,
    sensor_width_mm: float = 17.3,
    heading_deg: float = 0.0,
) -> dict:
    """Convert a detection bounding box to a GPS coordinate (bbox center).

    Args:
        bbox:  [x1, y1, x2, y2] pixel coords.
        image_gps: {"lat", "lon"} of drone/image center.
        altitude_m: Drone altitude in meters.
        heading_deg: Degrees clockwise from true north the image top faces.

    Returns:
        {"lat": float, "lon": float}
    """
    cx = (bbox[0] + bbox[2]) // 2
    cy = (bbox[1] + bbox[3]) // 2

    gsd = compute_gsd(altitude_m, focal_length_mm, sensor_width_mm, image_width)
    return pixel_to_gps(cx, cy, image_width, image_height, image_gps, gsd, heading_deg)


def read_geotiff_transform(geotiff_path: str | Path):
    """Read geotransform from a GeoTIFF orthomosaic (requires rasterio).

    Returns (transform, crs) for coordinate mapping.
    """
    import rasterio
    with rasterio.open(str(geotiff_path)) as src:
        return src.transform, src.crs


def pixel_to_gps_geotiff(px: int, py: int, transform) -> dict:
    """Convert pixel to GPS using rasterio geotransform (more accurate than EXIF).

    Args:
        px, py:    Pixel column, row.
        transform: rasterio Affine transform from read_geotiff_transform().

    Returns:
        {"lat": float, "lon": float} in EPSG:4326 (WGS84).
    """
    import rasterio.transform
    lon, lat = rasterio.transform.xy(transform, py, px)
    return {"lat": float(lat), "lon": float(lon)}
