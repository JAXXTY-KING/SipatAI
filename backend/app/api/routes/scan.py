from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from app.db.scan_store import overlay_path, overlays_in_bbox, scan_summary
from app.services.nationwide_grid import tiles_by_province

router = APIRouter(prefix="/scan", tags=["nationwide-scan"])


def _totals() -> dict[str, int]:
    return {name: len(tiles) for name, tiles in tiles_by_province().items()}


@router.get("/summary")
async def read_scan_summary() -> dict[str, Any]:
    """Coverage and flood totals of the nationwide MindSpore satellite scan."""
    return await run_in_threadpool(lambda: scan_summary(_totals()))


@router.get("/overlays")
async def read_scan_overlays(
    west: float = Query(ge=110, le=130),
    south: float = Query(ge=0, le=25),
    east: float = Query(ge=110, le=130),
    north: float = Query(ge=0, le=25),
    limit: int = Query(default=250, ge=1, le=500),
) -> dict[str, Any]:
    """Scanned tiles with detected flooding inside a map viewport."""
    tiles = await run_in_threadpool(overlays_in_bbox, west, south, east, north, limit)
    return {"tiles": tiles}


@router.get("/overlay/{tile_id}.png")
async def read_scan_overlay(tile_id: str) -> FileResponse:
    if not all(character.isdigit() or character in "._-" for character in tile_id):
        raise HTTPException(status_code=404, detail="Unknown tile.")
    path = overlay_path(tile_id)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="No overlay stored for this tile.")
    return FileResponse(path, media_type="image/png", headers={"Cache-Control": "public, max-age=300"})
