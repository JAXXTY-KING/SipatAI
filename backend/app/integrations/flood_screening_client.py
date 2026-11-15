import asyncio
import json
import logging
import math
import random
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Awaitable, Callable

import httpx
from shapely.geometry import Point, shape
from shapely.ops import unary_union

logger = logging.getLogger(__name__)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
# Open-Meteo refreshes its models about hourly and rate-limits free usage per location.
CACHE_TTL_SECONDS = 3600
FETCH_CONCURRENCY = 2
FETCH_ATTEMPTS = 4
PAST_HOURS = 72
RETRYABLE_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
GRID_STEP_DEGREES = 0.5
GRID_WEST = 116.0
GRID_EAST = 127.0
GRID_SOUTH = 4.0
GRID_NORTH = 21.0
WIND_GRID_STEP_DEGREES = 1.5
WIND_GRID_WEST = 114.0
WIND_GRID_EAST = 130.0
WIND_GRID_SOUTH = 1.5
WIND_GRID_NORTH = 25.5
LOW_ELEVATION_METERS = 30
_SCREENING_CACHE: tuple[float, dict[str, Any]] | None = None
_WIND_CACHE: tuple[float, dict[str, Any]] | None = None
_IN_FLIGHT: dict[str, asyncio.Task] = {}


class FloodScreeningError(RuntimeError):
    """Raised when forecast or Philippine land-boundary data are unavailable."""


async def _share_in_flight(key: str, start: Callable[[], Awaitable[dict[str, Any]]]) -> dict[str, Any]:
    """Let simultaneous requests share one provider fetch instead of each calling it."""
    task = _IN_FLIGHT.get(key)
    if task is None or task.done():
        task = asyncio.ensure_future(start())
        _IN_FLIGHT[key] = task

        def _finished(finished: asyncio.Task) -> None:
            if _IN_FLIGHT.get(key) is finished:
                del _IN_FLIGHT[key]
            if not finished.cancelled():
                finished.exception()

        task.add_done_callback(_finished)
    return await asyncio.shield(task)


@lru_cache(maxsize=1)
def _philippines_land_geometry():
    project_root = Path(__file__).resolve().parents[3]
    regions_path = project_root / "frontend" / "public" / "data" / "ph_admin1.geojson"
    try:
        with regions_path.open(encoding="utf-8") as regions_file:
            regions = json.load(regions_file)
        land = unary_union([
            shape(feature["geometry"])
            for feature in regions["features"]
            if feature.get("geometry")
        ])
    except (OSError, KeyError, TypeError, ValueError) as error:
        raise FloodScreeningError("Philippine administrative boundaries are unavailable.") from error
    if land.is_empty:
        raise FloodScreeningError("Philippine administrative boundaries contain no land geometry.")
    return land


@lru_cache(maxsize=1)
def _forecast_grid() -> tuple[tuple[float, float], ...]:
    land = _philippines_land_geometry()
    locations = []
    latitude = GRID_SOUTH + GRID_STEP_DEGREES / 2
    while latitude < GRID_NORTH:
        longitude = GRID_WEST + GRID_STEP_DEGREES / 2
        while longitude < GRID_EAST:
            if land.covers(Point(longitude, latitude)):
                locations.append((round(latitude, 3), round(longitude, 3)))
            longitude += GRID_STEP_DEGREES
        latitude += GRID_STEP_DEGREES
    if not locations:
        raise FloodScreeningError("No forecast grid points fall inside Philippine land boundaries.")
    return tuple(locations)


def _screening_level(rainfall_24h_mm: float, elevation_m: float | None) -> str:
    low_lying = elevation_m is not None and elevation_m <= LOW_ELEVATION_METERS
    if rainfall_24h_mm >= 100 or (rainfall_24h_mm >= 50 and low_lying):
        return "elevated"
    if rainfall_24h_mm >= 50 or (rainfall_24h_mm >= 25 and low_lying):
        return "watch"
    return "lower"


@lru_cache(maxsize=1)
def _wind_forecast_grid() -> tuple[tuple[float, float], ...]:
    locations = []
    latitude = WIND_GRID_SOUTH
    while latitude <= WIND_GRID_NORTH:
        longitude = WIND_GRID_WEST
        while longitude <= WIND_GRID_EAST:
            locations.append((round(latitude, 3), round(longitude, 3)))
            longitude += WIND_GRID_STEP_DEGREES
        latitude += WIND_GRID_STEP_DEGREES
    return tuple(locations)


def _parse_location_forecast(
    payload: dict[str, Any],
    latitude: float,
    longitude: float,
) -> dict[str, Any]:
    try:
        times = payload["hourly"]["time"]
        rainfall = payload["hourly"]["precipitation"]
        temperatures = payload["hourly"]["temperature_2m"]
        pressures = payload["hourly"]["pressure_msl"]
        wind_speeds = payload["hourly"]["wind_speed_10m"]
        wind_directions = payload["hourly"]["wind_direction_10m"]
        if (
            not times
            or len(times) != len(rainfall)
            or len(times) != len(temperatures)
            or len(times) != len(pressures)
            or len(times) != len(wind_speeds)
            or len(times) != len(wind_directions)
        ):
            raise ValueError("Hourly forecast is empty or inconsistent.")
        values = [float(value) for value in rainfall]
        temperature_values = [float(value) for value in temperatures]
        pressure_values = [float(value) for value in pressures]
        speeds = [float(value) for value in wind_speeds]
        directions = [float(value) for value in wind_directions]
        # Open-Meteo returns the last PAST_HOURS of rain (model analysis) before the 72 forecast hours.
        past_rain = values[:-72] if len(values) > 72 else []
        if past_rain:
            values, temperature_values, pressure_values = values[-72:], temperature_values[-72:], pressure_values[-72:]
            speeds, directions, times = speeds[-72:], directions[-72:], times[-72:]
        flood_window = past_rain[-48:] + values[:24]
        model_rain_24h = max(sum(flood_window[start:start + 24]) for start in range(max(1, len(flood_window) - 23)))
        model_rain_72h = sum(flood_window)
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("Hourly forecast contains invalid precipitation.")
        if any(not math.isfinite(value) or not -100 <= value <= 70 for value in temperature_values):
            raise ValueError("Hourly forecast contains invalid temperature.")
        if any(not math.isfinite(value) or not 500 <= value <= 1200 for value in pressure_values):
            raise ValueError("Hourly forecast contains invalid atmospheric pressure.")
        if any(not math.isfinite(value) or value < 0 for value in speeds):
            raise ValueError("Hourly forecast contains invalid wind speed.")
        if any(not math.isfinite(value) or not 0 <= value <= 360 for value in directions):
            raise ValueError("Hourly forecast contains an invalid wind direction.")
        rainfall_24h = max(
            sum(values[start:start + 24])
            for start in range(max(1, len(values) - 23))
            if len(values[start:start + 24]) == 24
        )
        rainfall_72h = sum(values[:72])
        elevation = payload.get("elevation")
        elevation_m = float(elevation) if elevation is not None else None
        if elevation_m is not None and (not math.isfinite(elevation_m) or not (-500 <= elevation_m <= 9000)):
            raise ValueError("Forecast elevation is outside the expected range.")
    except (KeyError, TypeError, ValueError) as error:
        raise FloodScreeningError("Forecast provider returned incomplete or invalid grid data.") from error

    return {
        "latitude": latitude,
        "longitude": longitude,
        "forecast_start": times[0],
        "forecast_times": times,
        "temperature_2m_c": round(temperature_values[0], 1),
        "precipitation_6h_mm": round(sum(values[:6]), 1),
        "pressure_msl_hpa": round(pressure_values[0], 1),
        "rainfall_24h_mm": round(rainfall_24h, 1),
        "rainfall_72h_mm": round(rainfall_72h, 1),
        "past_72h_mm": round(sum(past_rain), 1),
        "model_rain_24h_mm": round(model_rain_24h, 1),
        "model_rain_72h_mm": round(model_rain_72h, 1),
        "wind_speed_10m_mps": [round(speed / 3.6, 1) for speed in speeds],
        "wind_direction_10m_deg": [round(direction % 360, 1) for direction in directions],
        "elevation_m": round(elevation_m, 1) if elevation_m is not None else None,
    }


async def _fetch_forecast_batch(
    client: httpx.AsyncClient,
    locations: tuple[tuple[float, float], ...],
) -> list[dict[str, Any]]:
    request_params = {
        "latitude": ",".join(str(latitude) for latitude, _ in locations),
        "longitude": ",".join(str(longitude) for _, longitude in locations),
        "hourly": (
            "precipitation,temperature_2m,pressure_msl,"
            "wind_speed_10m,wind_direction_10m"
        ),
        "past_hours": PAST_HOURS,
        "forecast_hours": 72,
        "timezone": "UTC",
    }
    payload = None
    for attempt in range(1, FETCH_ATTEMPTS + 1):
        try:
            response = await client.get(FORECAST_URL, params=request_params)
            response.raise_for_status()
            payload = response.json()
            break
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            if status not in RETRYABLE_STATUS_CODES or attempt == FETCH_ATTEMPTS:
                raise FloodScreeningError(f"Forecast provider returned HTTP {status}.") from error
            retry_after = error.response.headers.get("Retry-After", "")
            delay = min(10.0, float(retry_after)) if retry_after.isdigit() else 2.0 * attempt
        except httpx.HTTPError as error:
            if attempt == FETCH_ATTEMPTS:
                logger.warning("Forecast request failed: %r", error)
                raise FloodScreeningError("Could not retrieve rainfall forecasts.") from error
            delay = 1.5 * attempt
        except ValueError as error:
            raise FloodScreeningError("Forecast provider returned invalid JSON.") from error
        await asyncio.sleep(delay + random.uniform(0, 0.5))

    if isinstance(payload, dict):
        payloads = [payload]
    elif isinstance(payload, list):
        payloads = payload
    else:
        raise FloodScreeningError("Forecast provider returned an unexpected response.")
    if len(payloads) != len(locations):
        raise FloodScreeningError("Forecast provider returned an incomplete grid batch.")
    if any(not isinstance(item, dict) for item in payloads):
        raise FloodScreeningError("Forecast provider returned an invalid grid location.")
    return [
        _parse_location_forecast(item, latitude, longitude)
        for item, (latitude, longitude) in zip(payloads, locations)
    ]


async def get_nationwide_flood_screening() -> dict[str, Any]:
    global _SCREENING_CACHE
    now = time.monotonic()
    if _SCREENING_CACHE and now - _SCREENING_CACHE[0] < CACHE_TTL_SECONDS:
        return _SCREENING_CACHE[1]
    try:
        return await _share_in_flight("screening", _build_flood_screening)
    except FloodScreeningError:
        if _SCREENING_CACHE:
            logger.warning("Serving the last rainfall forecast because the provider is unavailable.")
            return _SCREENING_CACHE[1]
        raise


async def _fetch_grid(locations: tuple[tuple[float, float], ...]) -> list[list[dict[str, Any]]]:
    batches = [locations[index:index + 50] for index in range(0, len(locations), 50)]
    slots = asyncio.Semaphore(FETCH_CONCURRENCY)

    async def fetch_limited(client: httpx.AsyncClient, batch: tuple[tuple[float, float], ...]):
        async with slots:
            return await _fetch_forecast_batch(client, batch)

    try:
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=15.0),
            follow_redirects=False,
        ) as client:
            return await asyncio.gather(*(fetch_limited(client, batch) for batch in batches))
    except FloodScreeningError:
        raise
    except httpx.HTTPError as error:
        raise FloodScreeningError("Could not retrieve the nationwide forecast.") from error


async def _build_flood_screening() -> dict[str, Any]:
    global _SCREENING_CACHE
    forecasts = await _fetch_grid(_forecast_grid())

    features = []
    half_step = GRID_STEP_DEGREES / 2
    for forecast in (item for batch in forecasts for item in batch):
        latitude = forecast["latitude"]
        longitude = forecast["longitude"]
        level = _screening_level(forecast["rainfall_24h_mm"], forecast["elevation_m"])
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Polygon",
                "coordinates": [[
                    [longitude - half_step, latitude - half_step],
                    [longitude + half_step, latitude - half_step],
                    [longitude + half_step, latitude + half_step],
                    [longitude - half_step, latitude + half_step],
                    [longitude - half_step, latitude - half_step],
                ]],
            },
            "properties": {
                "latitude": latitude,
                "longitude": longitude,
                "forecast_start": forecast["forecast_start"],
                "temperature_2m_c": forecast["temperature_2m_c"],
                "precipitation_6h_mm": forecast["precipitation_6h_mm"],
                "pressure_msl_hpa": forecast["pressure_msl_hpa"],
                "rainfall_24h_mm": forecast["rainfall_24h_mm"],
                "rainfall_72h_mm": forecast["rainfall_72h_mm"],
                "past_72h_mm": forecast["past_72h_mm"],
                "model_rain_24h_mm": forecast["model_rain_24h_mm"],
                "model_rain_72h_mm": forecast["model_rain_72h_mm"],
                "elevation_m": forecast["elevation_m"],
                "screening_level": level,
            },
        })

    result = {
        "type": "FeatureCollection",
        "provider": "Open-Meteo",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "forecast_period_hours": 72,
        "grid_resolution_degrees": GRID_STEP_DEGREES,
        "method": {
            "elevated": "At least 100 mm forecast in a 24-hour window during the next 72 hours, or at least 50 mm with model elevation at or below 30 m.",
            "watch": "At least 50 mm in a 24-hour window during the next 72 hours, or at least 25 mm with model elevation at or below 30 m.",
            "lower": "Below the prototype rainfall-screening thresholds.",
        },
        "features": features,
    }
    _SCREENING_CACHE = (time.monotonic(), result)
    return result


async def get_nationwide_wind_forecast() -> dict[str, Any]:
    global _WIND_CACHE
    now = time.monotonic()
    if _WIND_CACHE and now - _WIND_CACHE[0] < CACHE_TTL_SECONDS:
        return _WIND_CACHE[1]
    try:
        return await _share_in_flight("wind", _build_wind_forecast)
    except FloodScreeningError:
        if _WIND_CACHE:
            logger.warning("Serving the last wind forecast because the provider is unavailable.")
            return _WIND_CACHE[1]
        raise


async def _build_wind_forecast() -> dict[str, Any]:
    global _WIND_CACHE
    forecasts = await _fetch_grid(_wind_forecast_grid())

    points = [item for batch in forecasts for item in batch]
    forecast_times = points[0]["forecast_times"]
    if any(item["forecast_times"] != forecast_times for item in points[1:]):
        raise FloodScreeningError("Forecast provider returned inconsistent wind forecast times.")

    result = {
        "type": "FeatureCollection",
        "provider": "Open-Meteo",
        "model": "Open-Meteo best-match forecast",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "forecast_times": forecast_times,
        "wind_grid_step_degrees": WIND_GRID_STEP_DEGREES,
        "wind_direction_convention": "Direction the wind blows from, clockwise from north.",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [item["longitude"], item["latitude"]],
                },
                "properties": {
                    "wind_speed_10m_mps": item["wind_speed_10m_mps"],
                    "wind_direction_10m_deg": item["wind_direction_10m_deg"],
                },
            }
            for item in points
        ],
    }
    _WIND_CACHE = (time.monotonic(), result)
    return result
