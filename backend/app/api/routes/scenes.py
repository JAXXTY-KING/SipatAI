from typing import Any

from fastapi import APIRouter, HTTPException

from app.integrations.sentinel_client import SentinelCatalogError, search_scenes
from app.integrations.obs_client import OBSConfigurationError, OBSRequestError
from app.integrations.sentinel_download import (
    SentinelCredentialsError,
    SentinelDownloadError,
    download_product_to_obs,
)
from app.schemas.sentinel import SceneDownloadRequest, SceneSearchRequest

router = APIRouter(prefix="/scenes", tags=["satellite scenes"])


@router.post("/download")
async def download_satellite_scene(request: SceneDownloadRequest) -> dict[str, str]:
    """Copy a Sentinel product from Copernicus into the private OBS bucket."""
    try:
        object_key = await download_product_to_obs(request.collection, request.product_name)
    except SentinelCredentialsError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except (SentinelDownloadError, OBSConfigurationError, OBSRequestError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return {"object_key": object_key}


@router.post("/search")
async def search_satellite_scenes(request: SceneSearchRequest) -> dict[str, Any]:
    """Find Sentinel-1 or Sentinel-2 scenes by WGS 84 area and acquisition dates."""
    try:
        return await search_scenes(request)
    except SentinelCatalogError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
