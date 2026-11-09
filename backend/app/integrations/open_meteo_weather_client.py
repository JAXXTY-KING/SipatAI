import math
from datetime import datetime, timezone
from typing import Any

import httpx

GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
WEATHER_CODES = {
    0: ("Clear", "Clear sky"),
    1: ("Clear", "Mainly clear"),
    2: ("Clouds", "Partly cloudy"),
    3: ("Clouds", "Overcast"),
    45: ("Fog", "Fog"),
    48: ("Fog", "Depositing rime fog"),
    51: ("Drizzle", "Light drizzle"),
    53: ("Drizzle", "Moderate drizzle"),
    55: ("Drizzle", "Dense drizzle"),
    56: ("Drizzle", "Light freezing drizzle"),
    57: ("Drizzle", "Dense freezing drizzle"),
    61: ("Rain", "Slight rain"),
    63: ("Rain", "Moderate rain"),
    65: ("Rain", "Heavy rain"),
    66: ("Rain", "Light freezing rain"),
    67: ("Rain", "Heavy freezing rain"),
    71: ("Snow", "Slight snow fall"),
    73: ("Snow", "Moderate snow fall"),
    75: ("Snow", "Heavy snow fall"),
    77: ("Snow", "Snow grains"),
    80: ("Rain", "Slight rain showers"),
    81: ("Rain", "Moderate rain showers"),
    82: ("Rain", "Violent rain showers"),
    85: ("Snow", "Slight snow showers"),
    86: ("Snow", "Heavy snow showers"),
    95: ("Thunderstorm", "Thunderstorm"),
    96: ("Thunderstorm", "Thunderstorm with slight hail"),
    99: ("Thunderstorm", "Thunderstorm with heavy hail"),
}


class OpenMeteoWeatherError(RuntimeError):
    """Raised when Open-Meteo search or current weather data is unavailable."""


async def search_locations(query: str) -> list[dict[str, Any]]:
    """Search Open-Meteo's place catalog and return Philippine locations only."""
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
            response = await client.get(
                GEOCODING_URL,
                params={
                    "name": query.strip(),
                    "count": 20,
                    "language": "en",
                    "format": "json",
                },
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as error:
        raise OpenMeteoWeatherError(
            f"Open-Meteo place search returned HTTP {error.response.status_code}."
        ) from error
    except httpx.HTTPError as error:
        raise OpenMeteoWeatherError("Could not reach Open-Meteo place search.") from error
    except ValueError as error:
        raise OpenMeteoWeatherError("Open-Meteo place search returned invalid JSON.") from error

    try:
        results = payload.get("results", [])
        if not isinstance(results, list):
            raise TypeError("Place results are not a list.")
        return [
            {
                "name": item["name"],
                "state": item.get("admin1"),
                "country": item["country"],
                "latitude": float(item["latitude"]),
                "longitude": float(item["longitude"]),
            }
            for item in results
            if item.get("country_code") == "PH"
        ]
    except (AttributeError, KeyError, TypeError, ValueError) as error:
        raise OpenMeteoWeatherError("Open-Meteo returned unexpected place data.") from error


async def get_current_weather(latitude: float, longitude: float) -> dict[str, Any]:
    """Return Open-Meteo's current model conditions for a WGS 84 coordinate."""
    try:
        async with httpx.AsyncClient(timeout=15.0, follow_redirects=False) as client:
            response = await client.get(
                FORECAST_URL,
                params={
                    "latitude": latitude,
                    "longitude": longitude,
                    "current": (
                        "temperature_2m,relative_humidity_2m,apparent_temperature,"
                        "precipitation,weather_code,wind_speed_10m,wind_direction_10m"
                    ),
                    "wind_speed_unit": "ms",
                    "timezone": "UTC",
                    "forecast_days": 1,
                },
            )
            response.raise_for_status()
            payload = response.json()
    except httpx.HTTPStatusError as error:
        raise OpenMeteoWeatherError(
            f"Open-Meteo current-weather request returned HTTP {error.response.status_code}."
        ) from error
    except httpx.HTTPError as error:
        raise OpenMeteoWeatherError("Could not reach Open-Meteo current-weather service.") from error
    except ValueError as error:
        raise OpenMeteoWeatherError("Open-Meteo returned invalid current-weather JSON.") from error

    try:
        current = payload["current"]
        weather_code = int(current["weather_code"])
        condition, description = WEATHER_CODES.get(weather_code, ("Unknown", "Unknown conditions"))
        observed_at = datetime.fromisoformat(current["time"])
        if observed_at.tzinfo is None:
            observed_at = observed_at.replace(tzinfo=timezone.utc)
        values = {
            "temperature_c": float(current["temperature_2m"]),
            "feels_like_c": float(current["apparent_temperature"]),
            "humidity_percent": int(current["relative_humidity_2m"]),
            "wind_speed_mps": float(current["wind_speed_10m"]),
            "precipitation_1h_mm": float(current["precipitation"]),
            "wind_direction_deg": float(current["wind_direction_10m"]),
        }
        if any(not math.isfinite(value) for value in values.values()):
            raise ValueError("Current weather contains a non-finite value.")
        if not 0 <= values["humidity_percent"] <= 100:
            raise ValueError("Current weather contains invalid relative humidity.")
        return {
            "provider": "Open-Meteo",
            "location_name": None,
            "latitude": float(payload["latitude"]),
            "longitude": float(payload["longitude"]),
            "observed_at": observed_at.astimezone(timezone.utc).isoformat(),
            "condition": condition,
            "description": description,
            **values,
        }
    except (KeyError, TypeError, ValueError) as error:
        raise OpenMeteoWeatherError("Open-Meteo returned incomplete or invalid current weather.") from error
