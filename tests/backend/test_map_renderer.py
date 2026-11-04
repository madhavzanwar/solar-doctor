"""Unit tests for the static park grid PNG renderer."""
import io

from PIL import Image


def test_render_returns_bytes():
    from axalon.core.map_renderer import render_grid_png

    panels = [
        {"panel_id": "R1-C1", "row": 0, "col": 0, "worst_severity": "CRITICAL", "detection_count": 2},
        {"panel_id": "R1-C2", "row": 0, "col": 1, "worst_severity": "HIGH", "detection_count": 1},
        {"panel_id": "R2-C1", "row": 1, "col": 0, "worst_severity": None, "detection_count": 0},
    ]
    result = render_grid_png(panels, title="Test Park")
    assert isinstance(result, bytes)
    assert len(result) > 100


def test_render_produces_valid_png():
    from axalon.core.map_renderer import render_grid_png

    panels = [{"panel_id": "R1-C1", "row": 0, "col": 0, "worst_severity": "MEDIUM", "detection_count": 1}]
    result = render_grid_png(panels)
    img = Image.open(io.BytesIO(result))
    assert img.format == "PNG"
    assert img.size[0] > 0 and img.size[1] > 0


def test_render_empty_panels_returns_placeholder():
    from axalon.core.map_renderer import render_grid_png

    result = render_grid_png([])
    img = Image.open(io.BytesIO(result))
    assert img.format == "PNG"


def test_render_uses_severity_colors():
    from axalon.core.map_renderer import SEVERITY_COLORS

    assert "CRITICAL" in SEVERITY_COLORS
    assert "HIGH" in SEVERITY_COLORS
    assert "MEDIUM" in SEVERITY_COLORS
    assert "LOW" in SEVERITY_COLORS
