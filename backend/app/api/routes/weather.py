from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query, Response

from app.integrations.openweathermap_client import (
    WEATHER_MAP_LAYERS,
    WeatherConfigurationError,
    WeatherServiceError,
    get_current_weather,
    get_weather_overview,
    get_weather_tile,
    search_locations,
)
from app.schemas.weather import WeatherRequest

router = APIRouter(prefix="/weather", tags=["weather context"])


@router.get("/locations")
async def search_weather_locations(q: str = Query(min_length=2, max_length=120)) -> dict[str, Any]:
    """Search Philippine place names without exposing the provider key."""
    try:
        return {"locations": await search_locations(q)}
    except WeatherConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except WeatherServiceError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.get("/tiles/{layer}/{z}/{x}/{y}.png", include_in_schema=False)
async def read_weather_tile(
    layer: str,
    z: int = Path(ge=0, le=12),
    x: int = Path(ge=0),
    y: int = Path(ge=0),
) -> Response:
    """Proxy current weather tiles while keeping the provider key on the backend."""
    if layer not in WEATHER_MAP_LAYERS:
        raise HTTPException(status_code=404, detail="Weather map layer not found.")
    if x >= 2**z or y >= 2**z:
        raise HTTPException(status_code=404, detail="Weather map tile is outside the selected zoom level.")

    try:
        tile = await get_weather_tile(layer, z, x, y)
    except WeatherConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except WeatherServiceError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    return Response(
        content=tile,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=300"},
    )


@router.get("/overview")
async def read_weather_overview() -> dict[str, Any]:
    """Current observations at reference Philippine cities for the map overlay."""
    try:
        return await get_weather_overview()
    except WeatherConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except WeatherServiceError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.post("/current")
async def read_current_weather(request: WeatherRequest) -> dict[str, Any]:
    """Return current provider weather for a selected map coordinate."""
    try:
        return await get_current_weather(request.latitude, request.longitude)
    except WeatherConfigurationError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except WeatherServiceError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
