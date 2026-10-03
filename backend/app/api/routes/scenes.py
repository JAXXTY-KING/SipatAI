from typing import Any

from fastapi import APIRouter, HTTPException

from app.integrations.sentinel_client import SentinelCatalogError, search_scenes
from app.schemas.sentinel import SceneSearchRequest

router = APIRouter(prefix="/scenes", tags=["satellite scenes"])


@router.post("/search")
async def search_satellite_scenes(request: SceneSearchRequest) -> dict[str, Any]:
    """Find Sentinel-1 or Sentinel-2 scenes by WGS 84 area and acquisition dates."""
    try:
        return await search_scenes(request)
    except SentinelCatalogError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
