from typing import Any

import httpx

from app.schemas.sentinel import SceneSearchRequest

STAC_SEARCH_URL = "https://stac.dataspace.copernicus.eu/v1/search"


class SentinelCatalogError(RuntimeError):
    """Raised when the Copernicus Data Space catalogue cannot be queried."""


async def search_scenes(request: SceneSearchRequest) -> dict[str, Any]:
    """Search the official Copernicus Data Space STAC catalogue."""
    payload: dict[str, Any] = {
        "collections": [request.collection],
        "bbox": list(request.bbox),
        "datetime": f"{request.start_datetime.isoformat()}/{request.end_datetime.isoformat()}",
        "limit": request.limit,
    }
    if request.collection == "sentinel-2-l2a" and request.max_cloud_cover is not None:
        payload["query"] = {"eo:cloud_cover": {"lte": request.max_cloud_cover}}

    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=False) as client:
            response = await client.post(STAC_SEARCH_URL, json=payload)
            response.raise_for_status()
            result = response.json()
    except httpx.HTTPStatusError as error:
        raise SentinelCatalogError(
            f"Copernicus catalogue returned HTTP {error.response.status_code}."
        ) from error
    except httpx.HTTPError as error:
        raise SentinelCatalogError("Copernicus catalogue request failed.") from error
    except ValueError as error:
        raise SentinelCatalogError("Copernicus catalogue returned invalid JSON.") from error

    return result
