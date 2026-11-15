from typing import Any

from fastapi import APIRouter, HTTPException, Path, Query, Response

from app.integrations.openweathermap_client import (
    WEATHER_MAP_LAYERS,
    WeatherConfigurationError,
    WeatherServiceError,
    get_weather_overview,
    get_weather_tile,
)
from app.integrations.open_meteo_weather_client import (
    OpenMeteoWeatherError,
    get_current_weather,
    search_locations,
)
from app.integrations.province_forecast_client import get_province_forecast
from app.services.susceptibility_service import province_outlook
from app.services import weather_fields
from app.integrations.imerg_client import latest_imerg_time
from app.integrations.flood_screening_client import (
    FloodScreeningError,
    get_nationwide_flood_screening,
    get_nationwide_wind_forecast,
)
from app.integrations.himawari_client import (
    BANDS as HIMAWARI_BANDS,
    HimawariServiceError,
    get_himawari_cloud_tile,
    get_himawari_frames,
    get_himawari_image,
    get_himawari_tile_frames,
    get_latest_himawari_image,
)
from app.schemas.weather import WeatherRequest

router = APIRouter(prefix="/weather", tags=["weather context"])


@router.get("/field/{variable}.png", include_in_schema=False)
async def read_forecast_field(variable: str = Path(pattern="^(rain|pressure)$")) -> Response:
    """Smooth rain (next 6 h) or sea-level pressure picture interpolated from the real forecast points."""
    try:
        image, fetched_at = await weather_fields.field_png(variable)
    except Exception as error:
        raise HTTPException(status_code=502, detail="The forecast field is unavailable.") from error
    return Response(image, media_type="image/png", headers={"Cache-Control": "public, max-age=300", "X-Forecast-Fetched": fetched_at})


@router.get("/pressure-isobars")
async def read_pressure_isobars() -> dict[str, Any]:
    try:
        return await weather_fields.isobars()
    except Exception as error:
        raise HTTPException(status_code=502, detail="The pressure forecast is unavailable.") from error


@router.get("/imerg/latest")
async def read_latest_imerg() -> dict[str, Any]:
    """Latest NASA IMERG satellite rain-rate scene available from NASA GIBS (real observation, hours old)."""
    observed = await latest_imerg_time()
    if observed is None:
        raise HTTPException(status_code=502, detail="NASA IMERG rain scenes are unavailable.")
    return observed


@router.get("/himawari/tile-frames", include_in_schema=False)
async def read_himawari_tile_frames() -> dict[str, Any]:
    """Return recent JMA full-disk observation times for tiled cloud playback."""
    try:
        return {"frames": await get_himawari_tile_frames()}
    except HimawariServiceError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.get("/himawari/tiles/{time_code}/{z}/{x}/{y}.png", include_in_schema=False)
async def read_himawari_cloud_tile(
    time_code: str = Path(pattern="^\\d{14}$"),
    z: int = Path(ge=0, le=12),
    x: int = Path(ge=0),
    y: int = Path(ge=0),
) -> Response:
    """Serve a transparent cloud-only tile derived from JMA Himawari-9 infrared imagery."""
    try:
        tile = await get_himawari_cloud_tile(time_code, z, x, y)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except HimawariServiceError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    return Response(
        content=tile,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=1800"},
    )


@router.get("/himawari/frames", include_in_schema=False)
async def read_himawari_frames(
    band: str = Query(default="b13", pattern="^(b13|b03|cve|ngt|dms|arm)$"),
) -> dict[str, Any]:
    """Return recent JMA image times for live map playback."""
    try:
        return {"band": band, "frames": await get_himawari_frames(band)}
    except HimawariServiceError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.get("/himawari/latest.jpg", include_in_schema=False)
async def read_latest_himawari_image(
    band: str = Query(default="b13", pattern="^(b13|b03|cve|ngt|dms|arm)$"),
    time_code: str | None = Query(default=None, pattern="^\\d{4}$"),
) -> Response:
    """Proxy a selected timestamped JMA Himawari-9 image."""
    try:
        if time_code:
            image, observed_at = await get_himawari_image(band, time_code)
        else:
            image, observed_at = await get_latest_himawari_image(band)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except HimawariServiceError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error

    return Response(
        content=image,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=300",
            "X-Himawari-Observation-Time": observed_at,
            "X-Himawari-Band": HIMAWARI_BANDS[band],
        },
    )


@router.get("/flood-screening")
async def read_flood_screening() -> dict[str, Any]:
    """Return a nationwide, forecast-rainfall screening layer."""
    try:
        return await get_nationwide_flood_screening()
    except FloodScreeningError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.get("/province-forecast")
async def read_province_forecast() -> dict[str, Any]:
    """Return the real forecast by province, each with an automatic MindSpore-based flood outlook."""
    try:
        return await province_outlook()
    except FloodScreeningError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.get("/wind-forecast")
async def read_wind_forecast() -> dict[str, Any]:
    """Return a short-range regional wind forecast from Open-Meteo."""
    try:
        return await get_nationwide_wind_forecast()
    except FloodScreeningError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@router.get("/locations")
async def search_weather_locations(q: str = Query(min_length=2, max_length=120)) -> dict[str, Any]:
    """Search Philippine place names using Open-Meteo's public geocoding service."""
    try:
        return {"locations": await search_locations(q)}
    except OpenMeteoWeatherError as error:
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
    """Return current Open-Meteo model conditions for a selected coordinate."""
    try:
        return await get_current_weather(request.latitude, request.longitude)
    except OpenMeteoWeatherError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
