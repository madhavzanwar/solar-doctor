"""ortho router — extracted from app.py (Plan 01)."""
from __future__ import annotations

from fastapi import APIRouter
from axalon.api.deps import *  # noqa: F401,F403
from axalon.api.schemas.responses import OrthoListOut, OrthoMetaOut

router = APIRouter(tags=["ortho"])

@router.post("/park/{park_id}/ortho", status_code=201)
async def upload_ortho(
    park_id: str,
    file: UploadFile = File(..., description="GeoTIFF orthomosaic (.tif/.tiff, max 4 GB)"),
    principal: Principal = Depends(current_principal),
):
    """Upload a georeferenced orthomosaic for a park."""
    park_id = _validate_park_id(park_id)
    ensure_park_visible(principal, park_id)
    name = _validate_ortho_name(_safe_filename(file.filename, "ortho.tif"))

    # Stream to disk so we don't hold a 4 GB file in memory
    park_dir = (ORTHO_DIR / park_id)
    park_dir.mkdir(parents=True, exist_ok=True)
    target = _ortho_path(park_id, name)

    total = 0
    tmp_target = target.with_suffix(target.suffix + ".part")
    try:
        with tmp_target.open("wb") as out:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > _MAX_ORTHO_BYTES:
                    raise HTTPException(status_code=413, detail="Orthomosaic exceeds 4 GB limit")
                out.write(chunk)
    except HTTPException:
        tmp_target.unlink(missing_ok=True)
        raise
    except Exception:
        tmp_target.unlink(missing_ok=True)
        logger.exception("Failed to write uploaded ortho")
        raise HTTPException(status_code=500, detail="Failed to store uploaded file")

    # Validate it's actually a readable georeferenced raster
    meta = _register_ortho(park_id, name, tmp_target)
    return meta


@router.get("/park/{park_id}/orthos", response_model=OrthoListOut)
def list_orthos(park_id: str, principal: Principal = Depends(current_principal)):
    """List all uploaded orthos for a park."""
    park_id = _validate_park_id(park_id)
    ensure_park_visible(principal, park_id)
    park_dir = ORTHO_DIR / park_id
    if not park_dir.exists():
        return {"park_id": park_id, "orthos": []}

    orthos = []
    for path in sorted(park_dir.iterdir()):
        if path.suffix.lower() not in (".tif", ".tiff"):
            continue
        try:
            orthos.append(_ortho_metadata(park_id, path))
        except Exception:
            logger.exception("Skipping unreadable ortho: %s", path)
    return {"park_id": park_id, "orthos": orthos}


@router.get("/park/{park_id}/grid/png")
def export_park_grid_png(
    park_id: str, inspection_id: str | None = None, principal: Principal = Depends(current_principal),
):
    """Export the park fault grid as a static PNG image."""
    from axalon.core.map_renderer import render_grid_png

    park_id = _validate_park_id(park_id)
    ensure_park_visible(principal, park_id)
    try:
        grid = get_park_grid(park_id, inspection_id)
        panels = [
            {
                "panel_id": p.get("panel_id"),
                "row": p.get("row", 0),
                "col": p.get("col", 0),
                "worst_severity": p.get("worst_severity"),
                "detection_count": p.get("detection_count", 0),
            }
            for p in (grid.get("panels") or [])
        ]
    except Exception:
        panels = []

    png_bytes = render_grid_png(panels, title=park_id)
    safe_name = park_id.replace("/", "_").replace("..", "")
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}_grid.png"',
            "Cache-Control": "no-store",
        },
    )


@router.get("/park/{park_id}/ortho/{name}", response_model=OrthoMetaOut)
def get_ortho_metadata(park_id: str, name: str, principal: Principal = Depends(current_principal)):
    """Get metadata for a single ortho."""
    ensure_park_visible(principal, park_id, detail="Ortho not found")
    path = _ortho_path(park_id, name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Ortho not found")
    return _ortho_metadata(park_id, path)


@router.delete("/park/{park_id}/ortho/{name}")
def delete_ortho(park_id: str, name: str, principal: Principal = Depends(current_principal)):
    """Delete an uploaded ortho."""
    ensure_park_visible(principal, park_id, detail="Ortho not found")
    path = _ortho_path(park_id, name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Ortho not found")
    path.unlink()
    return {"deleted": True, "name": name}


@router.get("/park/{park_id}/ortho/{name}/tiles/{z}/{x}/{y}.png")
def get_ortho_tile(
    park_id: str, name: str, z: int, x: int, y: int, principal: Principal = Depends(current_principal),
):
    """Stream a Web Mercator XYZ tile from a GeoTIFF using rio-tiler.

    Centimeter accuracy comes from this endpoint — markers anchored in
    WGS84 are rendered on tiles built from the customer's own ortho, so
    visual and geometric coordinates stay in lockstep.
    """
    if not (0 <= z <= 24 and 0 <= x < 2 ** z and 0 <= y < 2 ** z):
        raise HTTPException(status_code=400, detail="Invalid tile coordinates")
    ensure_park_visible(principal, park_id, detail="Ortho not found")

    path = _ortho_path(park_id, name)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Ortho not found")

    try:
        from rio_tiler.io import Reader
        from rio_tiler.errors import TileOutsideBounds
    except ImportError:
        raise HTTPException(
            status_code=503,
            detail="rio-tiler is not installed on this server. Install with: pip install rio-tiler",
        )

    try:
        with Reader(str(path)) as src:
            img = src.tile(x, y, z, tilesize=256)
            png_bytes = img.render(img_format="PNG")
    except TileOutsideBounds:
        png_bytes = _empty_tile_png()
    except Exception:
        logger.exception("Tile rendering failed for %s z=%s x=%s y=%s", path.name, z, x, y)
        raise HTTPException(status_code=500, detail="Tile rendering failed")

    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=86400"},
    )
