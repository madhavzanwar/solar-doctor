"""Orthomosaic GeoTIFF access: name validation, safe path resolution, metadata.

Named `orthos` rather than `ortho` to stay distinct from routers/ortho.py.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

from fastapi import HTTPException

from axalon.api.support.paths import ORTHO_DIR
from axalon.api.support.security import _validate_park_id

logger = logging.getLogger("axalon.api")

_MAX_ORTHO_BYTES = 4 * 1024 * 1024 * 1024
_ORTHO_NAME_RE = re.compile(r"^[a-zA-Z0-9_\-]{1,80}\.(tif|tiff)$", re.IGNORECASE)

_EMPTY_TILE_CACHE: bytes | None = None


def _empty_tile_png() -> bytes:
    """A fully-transparent 256×256 PNG used for tiles outside the ortho bounds."""
    global _EMPTY_TILE_CACHE
    if _EMPTY_TILE_CACHE is None:
        from io import BytesIO

        from PIL import Image
        buf = BytesIO()
        Image.new("RGBA", (256, 256), (0, 0, 0, 0)).save(buf, format="PNG")
        _EMPTY_TILE_CACHE = buf.getvalue()
    return _EMPTY_TILE_CACHE


def _validate_ortho_name(name: str) -> str:
    if not _ORTHO_NAME_RE.match(name):
        raise HTTPException(
            status_code=400,
            detail="Ortho name must be 1–80 chars (a-z, 0-9, _-) and end in .tif or .tiff",
        )
    return name


def _ortho_path(park_id: str, name: str) -> Path:
    park_id = _validate_park_id(park_id)
    name = _validate_ortho_name(name)
    park_dir = (ORTHO_DIR / park_id).resolve()
    ortho_dir_resolved = ORTHO_DIR.resolve()
    if not str(park_dir).startswith(str(ortho_dir_resolved)):
        raise HTTPException(status_code=403, detail="Access denied")
    path = (park_dir / name).resolve()
    if not str(path).startswith(str(park_dir)):
        raise HTTPException(status_code=403, detail="Access denied")
    return path


def _ortho_metadata(park_id: str, path: Path) -> dict:
    """Open the GeoTIFF and return WGS84 bounds + native CRS."""
    import rasterio
    from rasterio.warp import transform_bounds

    with rasterio.open(str(path)) as src:
        if src.crs is None:
            raise HTTPException(status_code=400, detail="GeoTIFF has no CRS")
        west, south, east, north = transform_bounds(src.crs, "EPSG:4326", *src.bounds)
        return {
            "park_id": park_id,
            "name": path.name,
            "crs": str(src.crs),
            "width": src.width,
            "height": src.height,
            "band_count": src.count,
            "bounds": {"west": west, "south": south, "east": east, "north": north},
            "center": {"lat": (south + north) / 2, "lon": (west + east) / 2},
            "size_bytes": path.stat().st_size,
        }


def _register_ortho(park_id: str, name: str, staged: Path) -> dict:
    """Move a staged GeoTIFF into the park's ortho store and validate it.

    The single ingestion path for orthomosaics — manual uploads and
    NodeODM-generated orthos both land here, so tiles and overlays behave
    identically. The file is removed again if it is not a readable,
    georeferenced raster. Returns the ortho metadata dict.
    """
    target = _ortho_path(park_id, name)
    target.parent.mkdir(parents=True, exist_ok=True)
    Path(staged).replace(target)
    try:
        return _ortho_metadata(park_id, target)
    except HTTPException:
        target.unlink(missing_ok=True)
        raise
    except Exception:
        target.unlink(missing_ok=True)
        logger.exception("Ortho %s is not a valid GeoTIFF", name)
        raise HTTPException(status_code=400, detail="File is not a valid georeferenced TIFF")


__all__ = [
    "_EMPTY_TILE_CACHE",
    "_MAX_ORTHO_BYTES",
    "_ORTHO_NAME_RE",
    "_empty_tile_png",
    "_ortho_metadata",
    "_ortho_path",
    "_register_ortho",
    "_validate_ortho_name",
]
