import asyncio
import time
from datetime import datetime, timezone
from typing import Any

import httpx

from app.core.config import get_openweathermap_api_key

CACHE_TTL_SECONDS = 600
MAX_CACHED_TILES = 400
_TILE_CACHE: dict[tuple[str, int, int, int], tuple[float, bytes]] = {}
_OVERVIEW_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}

# Real Philippine cities used as observation points for the map overview.
OVERVIEW_POINTS = (
    ("Laoag", 18.1978, 120.5952),
    ("Tuguegarao", 17.6132, 121.7270),
    ("Baguio", 16.4023, 120.5960),
    ("San Fernando (Pampanga)", 15.0286, 120.6898),
    ("Metro Manila", 14.5995, 120.9842),
    ("Calapan", 13.4117, 121.1803),
    ("Legazpi", 13.1391, 123.7438),
    ("Puerto Princesa", 9.7392, 118.7353),
    ("Iloilo City", 10.7202, 122.5621),
    ("Cebu City", 10.3157, 123.8854),
    ("Tacloban", 11.2543, 124.9610),
    ("Dumaguete", 9.3068, 123.3054),
    ("Zamboanga City", 6.9214, 122.0790),
    ("Cagayan de Oro", 8.4542, 124.6319),
    ("Davao City", 7.1907, 125.4553),
    ("General Santos", 6.1164, 125.1716),
    ("Butuan", 8.9475, 125.5406),
)

OPENWEATHERMAP_CURRENT_URL = "https://api.openweathermap.org/data/2.5/weather"
OPENWEATHERMAP_GEOCODING_URL = "https://api.openweathermap.org/geo/1.0/direct"
OPENWEATHERMAP_TILE_URL = "https://tile.openweathermap.org/map/{layer}/{z}/{x}/{y}.png"
WEATHER_MAP_LAYERS = frozenset({
    "precipitation_new",
    "clouds_new",
    "temp_new",
    "wind_new",
    "pressure_new",
})


class WeatherConfigurationError(RuntimeError):
    """Raised when the private OpenWeatherMap key is missing or rejected."""


class WeatherServiceError(RuntimeError):
    """Raised when the weather provider cannot return current conditions."""


async def search_locations(query: str) -> list[dict[str, Any]]:
    """Resolve a Philippine place name using the official OpenWeatherMap geocoder."""
    api_key = get_openweathermap_api_key()
    if not api_key:
        raise WeatherConfigurationError("OpenWeatherMap is not configured on the backend.")

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
            response = await client.get(
                OPENWEATHERMAP_GEOCODING_URL,
                params={"q": f"{query.strip()},PH", "limit": 5, "appid": api_key},
            )
            if response.status_code in (401, 403):
                raise WeatherConfigurationError("OpenWeatherMap rejected the configured key.")
            if response.status_code == 429:
                raise WeatherServiceError("OpenWeatherMap rate limit reached; retry later.")
            response.raise_for_status()
            results = response.json()
    except WeatherConfigurationError:
        raise
    except WeatherServiceError:
        raise
    except httpx.HTTPStatusError as error:
        raise WeatherServiceError(
            f"OpenWeatherMap geocoding returned HTTP {error.response.status_code}."
        ) from error
    except httpx.HTTPError as error:
        raise WeatherServiceError("OpenWeatherMap location search failed.") from error
    except ValueError as error:
        raise WeatherServiceError("OpenWeatherMap geocoding returned invalid JSON.") from error

    try:
        return [
            {
                "name": item["name"],
                "state": item.get("state"),
                "country": item["country"],
                "latitude": item["lat"],
                "longitude": item["lon"],
            }
            for item in results
            if item.get("country") == "PH"
        ]
    except (AttributeError, KeyError, TypeError) as error:
        raise WeatherServiceError("OpenWeatherMap geocoding returned unexpected location data.") from error


async def get_current_weather(latitude: float, longitude: float) -> dict[str, Any]:
    """Fetch current weather for WGS 84 coordinates without exposing the API key."""
    api_key = get_openweathermap_api_key()
    if not api_key:
        raise WeatherConfigurationError("OpenWeatherMap is not configured on the backend.")

    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
            response = await client.get(
                OPENWEATHERMAP_CURRENT_URL,
                params={
                    "lat": latitude,
                    "lon": longitude,
                    "appid": api_key,
                    "units": "metric",
                },
            )
            if response.status_code in (401, 403):
                raise WeatherConfigurationError("OpenWeatherMap rejected the configured key.")
            if response.status_code == 429:
                raise WeatherServiceError("OpenWeatherMap rate limit reached; retry later.")
            response.raise_for_status()
            payload = response.json()
    except WeatherConfigurationError:
        raise
    except WeatherServiceError:
        raise
    except httpx.HTTPStatusError as error:
        raise WeatherServiceError(
            f"OpenWeatherMap returned HTTP {error.response.status_code}."
        ) from error
    except httpx.HTTPError as error:
        raise WeatherServiceError("OpenWeatherMap request failed.") from error
    except ValueError as error:
        raise WeatherServiceError("OpenWeatherMap returned invalid JSON.") from error

    try:
        condition = payload["weather"][0]
        main = payload["main"]
        wind = payload.get("wind", {})
        observed_at = datetime.fromtimestamp(payload["dt"], tz=timezone.utc)
        return {
            "provider": "OpenWeatherMap",
            "location_name": payload.get("name") or None,
            "latitude": payload["coord"]["lat"],
            "longitude": payload["coord"]["lon"],
            "observed_at": observed_at.isoformat(),
            "condition": condition["main"],
            "description": condition["description"],
            "temperature_c": main["temp"],
            "feels_like_c": main["feels_like"],
            "humidity_percent": main["humidity"],
            "wind_speed_mps": wind.get("speed"),
            "precipitation_1h_mm": payload.get("rain", {}).get("1h", 0),
        }
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise WeatherServiceError("OpenWeatherMap response did not contain expected weather fields.") from error


async def get_weather_tile(layer: str, zoom: int, x: int, y: int) -> bytes:
    """Fetch an allowlisted current-weather raster tile without exposing the API key."""
    if layer not in WEATHER_MAP_LAYERS:
        raise WeatherServiceError("Unsupported OpenWeatherMap layer.")

    api_key = get_openweathermap_api_key()
    if not api_key:
        raise WeatherConfigurationError("OpenWeatherMap is not configured on the backend.")

    cache_key = (layer, zoom, x, y)
    cached = _TILE_CACHE.get(cache_key)
    if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    tile_url = OPENWEATHERMAP_TILE_URL.format(layer=layer, z=zoom, x=x, y=y)
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as client:
            response = await client.get(tile_url, params={"appid": api_key})
            if response.status_code in (401, 403):
                raise WeatherConfigurationError("OpenWeatherMap rejected the configured key for weather maps.")
            if response.status_code == 429:
                raise WeatherServiceError("OpenWeatherMap rate limit reached; retry later.")
            response.raise_for_status()
            if response.headers.get("content-type", "").split(";")[0] != "image/png":
                raise WeatherServiceError("OpenWeatherMap returned an invalid weather tile.")
            if len(_TILE_CACHE) >= MAX_CACHED_TILES:
                _TILE_CACHE.pop(next(iter(_TILE_CACHE)))
            _TILE_CACHE[cache_key] = (time.monotonic(), response.content)
            return response.content
    except WeatherConfigurationError:
        raise
    except WeatherServiceError:
        raise
    except httpx.HTTPStatusError as error:
        raise WeatherServiceError(
            f"OpenWeatherMap weather tiles returned HTTP {error.response.status_code}."
        ) from error
    except httpx.HTTPError as error:
        raise WeatherServiceError("OpenWeatherMap weather tile request failed.") from error


async def get_weather_overview() -> dict[str, Any]:
    """Return current weather at reference Philippine cities as a GeoJSON collection."""
    cached = _OVERVIEW_CACHE.get("overview")
    if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    results = await asyncio.gather(
        *(get_current_weather(lat, lon) for _, lat, lon in OVERVIEW_POINTS),
        return_exceptions=True,
    )
    for result in results:
        if isinstance(result, WeatherConfigurationError):
            raise result
    features = []
    for (name, lat, lon), result in zip(OVERVIEW_POINTS, results):
        if isinstance(result, BaseException):
            continue
        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": {**result, "location_name": name},
        })
    if not features:
        raise WeatherServiceError("OpenWeatherMap returned no current observations.")
    collection = {
        "type": "FeatureCollection",
        "provider": "OpenWeatherMap",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "features": features,
    }
    _OVERVIEW_CACHE["overview"] = (time.monotonic(), collection)
    return collection
