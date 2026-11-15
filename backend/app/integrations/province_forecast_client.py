import json
import time
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any

from shapely import STRtree
from shapely.geometry import Point, shape

from app.integrations.flood_screening_client import (
    CACHE_TTL_SECONDS,
    FloodScreeningError,
    _fetch_grid,
    _screening_level,
    _share_in_flight,
    get_nationwide_flood_screening,
)

PROVINCES_PATH = Path(__file__).resolve().parents[3] / "frontend" / "public" / "data" / "ph_admin2.geojson"
_CACHE: tuple[float, dict[str, Any]] | None = None
_SAMPLES: list[dict[str, Any]] = []


@lru_cache(maxsize=1)
def _provinces() -> tuple[list[dict[str, Any]], list[Any]]:
    try:
        collection = json.loads(PROVINCES_PATH.read_text(encoding="utf-8"))
        features = collection["features"]
        geometries = [shape(feature["geometry"]) for feature in features]
    except (OSError, KeyError, ValueError) as error:
        raise FloodScreeningError("Philippine province boundaries are unavailable.") from error
    return features, geometries


def _province_index(
    points: list[tuple[float, float]],
    geometries: list[Any],
) -> dict[int, list[int]]:
    """Map province index to the indexes of the forecast points that fall inside it."""
    tree = STRtree(geometries)
    members: dict[int, list[int]] = {}
    for point_index, (latitude, longitude) in enumerate(points):
        point = Point(longitude, latitude)
        for province_index in tree.query(point, predicate="intersects"):
            members.setdefault(int(province_index), []).append(point_index)
            break
    return members


async def _build_province_forecast() -> dict[str, Any]:
    global _CACHE, _SAMPLES
    features, geometries = _provinces()
    screening = await get_nationwide_flood_screening()
    samples = [dict(item["properties"]) for item in screening["features"]]
    members = _province_index([(sample["latitude"], sample["longitude"]) for sample in samples], geometries)

    # Provinces too small to contain a 0.5 degree forecast point get their own real forecast point.
    uncovered = [index for index in range(len(features)) if index not in members]
    if uncovered:
        locations = tuple(
            (round(geometries[index].representative_point().y, 3), round(geometries[index].representative_point().x, 3))
            for index in uncovered
        )
        fetched = [item for batch in await _fetch_grid(locations) for item in batch]
        for index, forecast in zip(uncovered, fetched):
            members[index] = [len(samples)]
            samples.append({
                "latitude": forecast["latitude"],
                "longitude": forecast["longitude"],
                "forecast_start": forecast["forecast_start"],
                "temperature_2m_c": forecast["temperature_2m_c"],
                "precipitation_6h_mm": forecast["precipitation_6h_mm"],
                "pressure_msl_hpa": forecast["pressure_msl_hpa"],
                "rainfall_24h_mm": forecast["rainfall_24h_mm"],
                "rainfall_72h_mm": forecast["rainfall_72h_mm"],
                "elevation_m": forecast["elevation_m"],
            })

    result_features = []
    for index, feature in enumerate(features):
        group = [samples[position] for position in members[index]]
        peak = max(group, key=lambda sample: sample["rainfall_24h_mm"])
        elevations = [sample["elevation_m"] for sample in group if sample["elevation_m"] is not None]
        mean = lambda key: round(sum(sample[key] for sample in group) / len(group), 1)  # noqa: E731
        result_features.append({
            "type": "Feature",
            "geometry": feature["geometry"],
            "properties": {
                "name": feature["properties"]["name"],
                "sample_points": len(group),
                "forecast_start": peak["forecast_start"],
                "temperature_2m_c": mean("temperature_2m_c"),
                "precipitation_6h_mm": mean("precipitation_6h_mm"),
                "pressure_msl_hpa": mean("pressure_msl_hpa"),
                "rainfall_24h_mm": peak["rainfall_24h_mm"],
                "rainfall_72h_mm": peak["rainfall_72h_mm"],
                "elevation_m": round(sum(elevations) / len(elevations), 1) if elevations else None,
                "screening_level": _screening_level(peak["rainfall_24h_mm"], peak["elevation_m"]),
            },
        })

    result = {
        "type": "FeatureCollection",
        "provider": "Open-Meteo",
        "boundaries": "geoBoundaries gbOpen ADM2 (NAMRIA, PSA, OCHA Philippines), CC BY 3.0 IGO",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "forecast_period_hours": 72,
        "method": (
            "Real Open-Meteo model forecast points are grouped by province. Rainfall shows the wettest forecast point "
            "inside the province; temperature, pressure and 6-hour precipitation are the mean of its points."
        ),
        "features": result_features,
    }
    _SAMPLES = samples
    _CACHE = (time.monotonic(), result)
    return result


async def get_forecast_samples() -> tuple[list[dict[str, Any]], str]:
    """The real forecast points behind the province forecast (about 0.5 degrees apart) and its fetch time."""
    forecast = await get_province_forecast()
    return list(_SAMPLES), forecast["fetched_at"]


async def get_province_forecast() -> dict[str, Any]:
    if _CACHE and time.monotonic() - _CACHE[0] < CACHE_TTL_SECONDS:
        return _CACHE[1]
    try:
        return await _share_in_flight("provinces", _build_province_forecast)
    except FloodScreeningError:
        if _CACHE:
            return _CACHE[1]
        raise
