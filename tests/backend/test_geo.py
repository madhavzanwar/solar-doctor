"""Unit tests for platform/core/geo.py — GPS/EXIF extraction and pixel→GPS math."""
from __future__ import annotations

import math

import piexif
import pytest
from PIL import Image

from axalon.core.geo import (
    compute_gsd,
    detection_to_gps,
    extract_gps_exif,
    parse_dji_xmp_heading,
    pixel_to_gps,
)


def _deg_to_dms_rational(deg: float):
    """Convert a positive decimal degree to EXIF DMS rational tuples."""
    d = int(deg)
    m_full = (deg - d) * 60
    m = int(m_full)
    s = round((m_full - m) * 60 * 100)
    return ((d, 1), (m, 1), (s, 100))


def _make_jpg_with_gps(path, lat: float, lon: float, alt: float = 30.0):
    lat_ref = b"N" if lat >= 0 else b"S"
    lon_ref = b"E" if lon >= 0 else b"W"
    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: lat_ref,
        piexif.GPSIFD.GPSLatitude: _deg_to_dms_rational(abs(lat)),
        piexif.GPSIFD.GPSLongitudeRef: lon_ref,
        piexif.GPSIFD.GPSLongitude: _deg_to_dms_rational(abs(lon)),
        piexif.GPSIFD.GPSAltitude: (int(alt * 100), 100),
    }
    exif_bytes = piexif.dump({"GPS": gps_ifd})
    img = Image.new("RGB", (16, 16), color=(120, 80, 40))
    img.save(str(path), "jpeg", exif=exif_bytes)


def test_extract_gps_from_exif_jpg(tmp_path):
    # Arrange
    img_path = tmp_path / "with_gps.jpg"
    _make_jpg_with_gps(img_path, lat=19.076, lon=72.877, alt=42.0)

    # Act
    result = extract_gps_exif(img_path)

    # Assert
    assert result is not None
    assert result["lat"] == pytest.approx(19.076, abs=1e-3)
    assert result["lon"] == pytest.approx(72.877, abs=1e-3)
    assert result["alt"] == pytest.approx(42.0, abs=0.5)


def test_extract_gps_handles_southern_western_hemisphere(tmp_path):
    # Arrange — negative lat/lon must round-trip through S/W refs
    img_path = tmp_path / "south_west.jpg"
    _make_jpg_with_gps(img_path, lat=-33.865, lon=-70.000)

    # Act
    result = extract_gps_exif(img_path)

    # Assert
    assert result["lat"] == pytest.approx(-33.865, abs=1e-3)
    assert result["lon"] == pytest.approx(-70.000, abs=1e-3)


def test_extract_gps_returns_none_when_no_exif(tmp_path):
    # Arrange — image saved without any EXIF block
    img_path = tmp_path / "no_exif.jpg"
    Image.new("RGB", (8, 8)).save(str(img_path), "jpeg")

    # Act
    result = extract_gps_exif(img_path)

    # Assert
    assert result is None


def test_extract_gps_handles_corrupt_file(tmp_path):
    # Arrange — not a real image at all
    bad = tmp_path / "corrupt.jpg"
    bad.write_bytes(b"this is not a jpeg")

    # Act
    result = extract_gps_exif(bad)

    # Assert — must not raise, returns None
    assert result is None


def test_compute_gsd_scales_with_altitude():
    # Arrange / Act
    low = compute_gsd(altitude_m=10.0)
    high = compute_gsd(altitude_m=20.0)

    # Assert — GSD is linear in altitude
    assert high == pytest.approx(2 * low)
    assert low > 0


def test_pixel_to_gps_center_pixel_returns_image_gps():
    # Arrange — center pixel of a 640x480 image
    image_gps = {"lat": 19.0, "lon": 72.0}

    # Act
    result = pixel_to_gps(320, 240, 640, 480, image_gps, gsd_cm_per_px=5.0)

    # Assert — no offset from center → same coordinate
    assert result["lat"] == pytest.approx(19.0, abs=1e-9)
    assert result["lon"] == pytest.approx(72.0, abs=1e-9)


def test_pixel_to_gps_offset_moves_south_and_east():
    # Arrange — pixel below+right of center should move south (lower lat) and east
    image_gps = {"lat": 19.0, "lon": 72.0}

    # Act
    result = pixel_to_gps(400, 300, 640, 480, image_gps, gsd_cm_per_px=10.0)

    # Assert
    assert result["lat"] < 19.0  # y increases downward = south
    assert result["lon"] > 72.0  # x increases rightward = east


def test_detection_to_gps_uses_bbox_center():
    # Arrange — a bbox centered exactly at the image center
    image_gps = {"lat": 19.0, "lon": 72.0}
    bbox = [310, 230, 330, 250]  # center (320, 240) of 640x480

    # Act
    result = detection_to_gps(
        bbox, image_width=640, image_height=480,
        image_gps=image_gps, altitude_m=20.0,
    )

    # Assert — centered bbox maps to image GPS
    assert result["lat"] == pytest.approx(19.0, abs=1e-6)
    assert result["lon"] == pytest.approx(72.0, abs=1e-6)


# ── Heading (yaw) correction ────────────────────────────────────────────────
# Drones fly survey lanes at arbitrary headings, so "up" in the frame is only
# north when heading == 0. These pin the rotation's sign convention: heading is
# degrees clockwise from true north that the TOP of the image faces.

_CENTER = {"lat": 19.0, "lon": 72.0}
# Top-centre of a 640x480 frame: 200 px above centre → 20 m at 10 cm/px.
_TOP_CENTRE = (320, 40)


def _offset_m(result: dict, origin: dict = _CENTER) -> tuple[float, float]:
    """(east_m, north_m) of result relative to origin (small-offset approximation)."""
    r = 6_371_000.0
    north = math.radians(result["lat"] - origin["lat"]) * r
    east = math.radians(result["lon"] - origin["lon"]) * r * math.cos(math.radians(origin["lat"]))
    return east, north


def test_pixel_to_gps_heading_zero_matches_default():
    # Act
    default = pixel_to_gps(*_TOP_CENTRE, 640, 480, _CENTER, gsd_cm_per_px=10.0)
    explicit = pixel_to_gps(*_TOP_CENTRE, 640, 480, _CENTER, gsd_cm_per_px=10.0, heading_deg=0.0)

    # Assert — heading 0: top-centre is 20 m due north
    assert explicit == default
    east, north = _offset_m(explicit)
    assert east == pytest.approx(0.0, abs=1e-6)
    assert north == pytest.approx(20.0, abs=1e-3)


def test_pixel_to_gps_heading_90_top_centre_lands_east():
    # Act — image top faces east
    result = pixel_to_gps(*_TOP_CENTRE, 640, 480, _CENTER, gsd_cm_per_px=10.0, heading_deg=90.0)

    # Assert
    east, north = _offset_m(result)
    assert east == pytest.approx(20.0, abs=1e-3)
    assert north == pytest.approx(0.0, abs=1e-3)


def test_pixel_to_gps_heading_180_top_centre_lands_south():
    # Act
    result = pixel_to_gps(*_TOP_CENTRE, 640, 480, _CENTER, gsd_cm_per_px=10.0, heading_deg=180.0)

    # Assert
    east, north = _offset_m(result)
    assert east == pytest.approx(0.0, abs=1e-3)
    assert north == pytest.approx(-20.0, abs=1e-3)


def test_pixel_to_gps_heading_90_right_edge_lands_south():
    # Act — top faces east, so the image's right-hand side faces south.
    # (520, 240) is 200 px right of centre → 20 m.
    result = pixel_to_gps(520, 240, 640, 480, _CENTER, gsd_cm_per_px=10.0, heading_deg=90.0)

    # Assert
    east, north = _offset_m(result)
    assert east == pytest.approx(0.0, abs=1e-3)
    assert north == pytest.approx(-20.0, abs=1e-3)


def test_pixel_to_gps_negative_heading_equals_wrapped_heading():
    # Act — DJI reports yaw in [-180, 180]; -90 must equal 270 (top faces west)
    neg = pixel_to_gps(*_TOP_CENTRE, 640, 480, _CENTER, gsd_cm_per_px=10.0, heading_deg=-90.0)
    wrapped = pixel_to_gps(*_TOP_CENTRE, 640, 480, _CENTER, gsd_cm_per_px=10.0, heading_deg=270.0)

    # Assert
    east, _ = _offset_m(neg)
    assert east == pytest.approx(-20.0, abs=1e-3)
    assert neg["lat"] == pytest.approx(wrapped["lat"], abs=1e-12)
    assert neg["lon"] == pytest.approx(wrapped["lon"], abs=1e-12)


def test_detection_to_gps_threads_heading():
    # Arrange — bbox at top-centre of a 640x480 frame
    bbox = [310, 30, 330, 50]

    # Act
    north_up = detection_to_gps(bbox, 640, 480, _CENTER, altitude_m=40.0)
    east_up = detection_to_gps(bbox, 640, 480, _CENTER, altitude_m=40.0, heading_deg=90.0)

    # Assert — rotating 90° turns a due-north offset into an equal due-east one
    _, north0 = _offset_m(north_up)
    east90, north90 = _offset_m(east_up)
    assert north0 > 0
    assert east90 == pytest.approx(north0, rel=1e-6)
    assert north90 == pytest.approx(0.0, abs=1e-3)


# ── Heading extraction from metadata ────────────────────────────────────────

_DJI_XMP_ATTRS = (
    b'<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF><rdf:Description '
    b'xmlns:drone-dji="http://www.dji.com/drone-dji/1.0/" '
    b'drone-dji:FlightYawDegree="+12.30" drone-dji:GimbalYawDegree="-95.40" '
    b'drone-dji:GimbalPitchDegree="-90.00"/></rdf:RDF></x:xmpmeta>'
)


def test_parse_dji_xmp_prefers_gimbal_yaw():
    # Act
    heading = parse_dji_xmp_heading(_DJI_XMP_ATTRS)

    # Assert — gimbal yaw is the camera direction; normalised into [0, 360)
    assert heading == pytest.approx(360.0 - 95.4)


def test_parse_dji_xmp_falls_back_to_flight_yaw():
    # Arrange — element syntax, no gimbal yaw
    xmp = (
        "<rdf:Description><drone-dji:FlightYawDegree>+45.5</drone-dji:FlightYawDegree>"
        "</rdf:Description>"
    )

    # Act / Assert
    assert parse_dji_xmp_heading(xmp) == pytest.approx(45.5)


def test_parse_dji_xmp_returns_none_without_yaw():
    assert parse_dji_xmp_heading(b"<x:xmpmeta></x:xmpmeta>") is None
    assert parse_dji_xmp_heading(b'drone-dji:GimbalYawDegree="garbage"') is None


def _make_jpg_with_heading(path, direction: float | None = None, xmp: bytes | None = None):
    gps_ifd = {
        piexif.GPSIFD.GPSLatitudeRef: b"N",
        piexif.GPSIFD.GPSLatitude: _deg_to_dms_rational(19.0),
        piexif.GPSIFD.GPSLongitudeRef: b"E",
        piexif.GPSIFD.GPSLongitude: _deg_to_dms_rational(72.0),
        piexif.GPSIFD.GPSAltitude: (3000, 100),
    }
    if direction is not None:
        gps_ifd[piexif.GPSIFD.GPSImgDirectionRef] = b"T"
        gps_ifd[piexif.GPSIFD.GPSImgDirection] = (int(round(direction * 100)), 100)
    kwargs = {"exif": piexif.dump({"GPS": gps_ifd})}
    if xmp is not None:
        kwargs["xmp"] = xmp
    Image.new("RGB", (16, 16)).save(str(path), "jpeg", **kwargs)


def test_extract_gps_exif_reads_gps_img_direction(tmp_path):
    # Arrange
    img_path = tmp_path / "dir.jpg"
    _make_jpg_with_heading(img_path, direction=123.45)

    # Act
    result = extract_gps_exif(img_path)

    # Assert — existing keys intact, heading added
    assert result["lat"] == pytest.approx(19.0, abs=1e-3)
    assert result["alt"] == pytest.approx(30.0, abs=0.5)
    assert result["heading"] == pytest.approx(123.45, abs=1e-6)


def test_extract_gps_exif_prefers_dji_xmp_over_exif_direction(tmp_path):
    # Arrange — both sources present; XMP gimbal yaw wins
    img_path = tmp_path / "dji.jpg"
    _make_jpg_with_heading(img_path, direction=10.0, xmp=_DJI_XMP_ATTRS)

    # Act
    result = extract_gps_exif(img_path)

    # Assert
    assert result["heading"] == pytest.approx(264.6, abs=1e-6)


def test_extract_gps_exif_omits_heading_when_absent(tmp_path):
    # Arrange
    img_path = tmp_path / "plain.jpg"
    _make_jpg_with_gps(img_path, lat=19.0, lon=72.0)

    # Act
    result = extract_gps_exif(img_path)

    # Assert — key set unchanged for images with no heading metadata
    assert set(result) == {"lat", "lon", "alt"}
