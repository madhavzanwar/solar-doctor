"""Render park fault grids as static PNG images."""
from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

SEVERITY_COLORS: dict[str | None, tuple[int, int, int]] = {
    "CRITICAL": (220, 38, 38),
    "HIGH": (234, 88, 12),
    "MEDIUM": (202, 138, 4),
    "LOW": (2, 132, 199),
    None: (51, 65, 85),
}

_CELL = 48
_PAD = 20
_TITLE_H = 26
_LEGEND_H = 32
_BG = (15, 23, 42)
_TEXT = (203, 213, 225)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


def render_grid_png(panels: list[dict], title: str = "") -> bytes:
    """Render panel severity cells with a compact legend and return PNG bytes."""
    if not panels:
        img = Image.new("RGB", (320, 80), _BG)
        draw = ImageDraw.Draw(img)
        draw.text((10, 28), "No panel data", fill=_TEXT, font=_font(13))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()

    max_row = max(int(p["row"]) for p in panels) + 1
    max_col = max(int(p["col"]) for p in panels) + 1

    title_offset = _TITLE_H if title else 0
    width = max_col * _CELL + 2 * _PAD
    height = max_row * _CELL + 2 * _PAD + title_offset + _LEGEND_H

    img = Image.new("RGB", (width, height), _BG)
    draw = ImageDraw.Draw(img)
    small = _font(9)
    medium = _font(12)

    if title:
        draw.text((_PAD, 6), title, fill=_TEXT, font=medium)

    for panel in panels:
        row = int(panel["row"])
        col = int(panel["col"])
        severity = panel.get("worst_severity")
        color = SEVERITY_COLORS.get(severity, SEVERITY_COLORS[None])

        x1 = _PAD + col * _CELL + 1
        y1 = _PAD + title_offset + row * _CELL + 1
        x2 = x1 + _CELL - 2
        y2 = y1 + _CELL - 2

        draw.rectangle([x1, y1, x2, y2], fill=color, outline=(30, 41, 59))
        panel_id = str(panel.get("panel_id", ""))
        if panel_id:
            draw.text((x1 + 3, y1 + 3), panel_id[-6:], fill=(255, 255, 255), font=small)

    legend_y = height - _LEGEND_H + 6
    x_cursor = _PAD
    for label, color in [
        ("CRITICAL", SEVERITY_COLORS["CRITICAL"]),
        ("HIGH", SEVERITY_COLORS["HIGH"]),
        ("MEDIUM", SEVERITY_COLORS["MEDIUM"]),
        ("LOW", SEVERITY_COLORS["LOW"]),
        ("None", SEVERITY_COLORS[None]),
    ]:
        draw.rectangle([x_cursor, legend_y, x_cursor + 12, legend_y + 12], fill=color)
        draw.text((x_cursor + 16, legend_y), label, fill=_TEXT, font=small)
        x_cursor += 68

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
