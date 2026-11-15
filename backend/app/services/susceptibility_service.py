import json
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
from shapely.geometry import Point

from app.core.config import REPOSITORY_ROOT
from app.integrations.province_forecast_client import _provinces, get_province_forecast

SUSCEPTIBILITY_DIRECTORY = REPOSITORY_ROOT / "ml" / "artifacts" / "susceptibility"
NATIONAL_DIRECTORY = SUSCEPTIBILITY_DIRECTORY / "national"
MODERATE_SCORE, HIGH_SCORE = 0.5, 0.75
LOCAL_RADIUS_KM = 5.0
CELL_DEGREES = 3 / 3600
# Same rainfall bands as the existing screening layer (mm in the wettest 24 h of the next 72 h).
RAIN_BANDS = ((100.0, "extreme"), (50.0, "heavy"), (25.0, "moderate"))
_lock = threading.Lock()


class SusceptibilityUnavailableError(RuntimeError):
    """Raised when the nationwide susceptibility map has not been built."""


def _index() -> list[dict[str, Any]]:
    path = NATIONAL_DIRECTORY / "index.json"
    if not path.is_file():
        raise SusceptibilityUnavailableError("The nationwide flood-prone map has not been built yet (see ml/README.md).")
    return json.loads(path.read_text(encoding="utf-8"))


def get_susceptibility_status() -> dict[str, Any]:
    card_path = SUSCEPTIBILITY_DIRECTORY / "model_card.json"
    status: dict[str, Any] = {"framework": "MindSpore", "ready": False}
    try:
        index = _index()
    except SusceptibilityUnavailableError as error:
        status["reason"] = str(error)
        return status
    status.update(
        ready=True,
        chunks=len(index),
        land_km2=round(sum(chunk["land_km2"] for chunk in index)),
        high_km2=round(sum(chunk["high_km2"] for chunk in index)),
    )
    if card_path.is_file():
        card = json.loads(card_path.read_text(encoding="utf-8"))
        status.update(
            label=card.get("label"),
            inputs=card.get("inputs"),
            heldout_auc=card.get("final", {}).get("heldout_province_auc"),
            heldout_regions=len(card.get("heldout_provinces", [])),
        )
    return status


def chunks_in_bbox(west: float, south: float, east: float, north: float) -> list[dict[str, Any]]:
    return [
        chunk for chunk in _index()
        if chunk["east"] > west and chunk["west"] < east and chunk["north"] > south and chunk["south"] < north
        and chunk["high_km2"] + chunk["moderate_km2"] > 0
    ]


def chunk_png(chunk_id: str) -> Path:
    if not all(character.isalnum() or character in "_-" for character in chunk_id):
        raise SusceptibilityUnavailableError("Unknown chunk.")
    path = NATIONAL_DIRECTORY / f"{chunk_id}.png"
    if not path.is_file():
        raise SusceptibilityUnavailableError("No overlay for this chunk.")
    return path


@lru_cache(maxsize=24)
def _scores(chunk_id: str) -> np.ndarray:
    return np.load(NATIONAL_DIRECTORY / f"{chunk_id}.npy")


def local_susceptibility(longitude: float, latitude: float) -> dict[str, Any]:
    """Susceptibility at a point and across the surrounding 5 km, from the precomputed national map."""
    west, south = int(np.floor(longitude)), int(np.floor(latitude))
    chunk_id = f"{west}E_{south}N"
    if not (NATIONAL_DIRECTORY / f"{chunk_id}.npy").is_file():
        raise SusceptibilityUnavailableError("No flood-prone data covers this point (open sea or outside the Philippines).")
    scores = _scores(chunk_id).astype(np.float32) / 255.0
    size = scores.shape[0]
    row = min(size - 1, int((south + 1 - latitude) / CELL_DEGREES))
    column = min(size - 1, int((longitude - west) / CELL_DEGREES))
    radius = int(LOCAL_RADIUS_KM / (CELL_DEGREES * 111.32))
    window = scores[max(0, row - radius) : row + radius + 1, max(0, column - radius) : column + radius + 1]
    land = window > 0
    return {
        "point_score": round(float(scores[row, column]), 3),
        "radius_km": LOCAL_RADIUS_KM,
        "land_share_high": round(float((window >= HIGH_SCORE).sum() / max(land.sum(), 1)), 3),
        "land_share_moderate_or_high": round(float((window >= MODERATE_SCORE).sum() / max(land.sum(), 1)), 3),
    }


async def _forecast_for(longitude: float, latitude: float) -> dict[str, Any] | None:
    try:
        _, geometries = _provinces()
        forecast = await get_province_forecast()
    except Exception:
        return None
    point = Point(longitude, latitude)
    for index, geometry in enumerate(geometries):
        if geometry.covers(point):
            properties = forecast["features"][index]["properties"]
            return {key: properties[key] for key in (
                "name", "rainfall_24h_mm", "rainfall_72h_mm", "precipitation_6h_mm",
                "temperature_2m_c", "pressure_msl_hpa", "forecast_start", "sample_points",
            )}
    return None


def _rain_band(rainfall_24h_mm: float) -> str:
    for minimum, label in RAIN_BANDS:
        if rainfall_24h_mm >= minimum:
            return label
    return "light"


def flood_watch(local: dict[str, Any], forecast: dict[str, Any] | None) -> dict[str, str]:
    """Combine local flood-proneness with the forecast rain. The rain-to-flood link is a documented rule, not learned."""
    share = local["land_share_high"]
    terrain = "high" if share >= 0.2 else "moderate" if share >= 0.05 else "low"
    if forecast is None:
        return {"level": "unknown", "terrain": terrain, "rain": "unavailable",
                "message": "Rainfall forecast unavailable. Showing flood-prone terrain only."}
    rain = _rain_band(forecast["rainfall_24h_mm"])
    score = {"light": 0, "moderate": 1, "heavy": 2, "extreme": 3}[rain] * {"low": 1, "moderate": 2, "high": 3}[terrain]
    level = "warning" if score >= 6 else "watch" if score >= 3 else "advisory" if score >= 2 else "none"
    messages = {
        "none": "Our rule finds no heavy rain over flood-prone terrain in the current forecast. This is not a guarantee of safety. Flood-prone areas are shown for planning.",
        "advisory": "Some rain is forecast and parts of this area are flood-prone. Monitor local advisories.",
        "watch": "Heavy rain is forecast over flood-prone terrain. Low-lying areas could flood.",
        "warning": "Very heavy rain is forecast over highly flood-prone terrain. Flooding is possible in the red areas. Check PAGASA for advisories.",
    }
    return {"level": level, "terrain": terrain, "rain": rain, "message": messages[level]}


async def assess_point(longitude: float, latitude: float) -> dict[str, Any]:
    from app.integrations.province_forecast_client import get_forecast_samples
    from app.services import rain_flood_service

    local = local_susceptibility(longitude, latitude)
    forecast = await _forecast_for(longitude, latitude)
    result = {"local": local, "forecast": forecast, "watch": flood_watch(local, forecast), "rain_model": None}
    try:
        samples, _ = await get_forecast_samples()
        result["rain_model"] = rain_flood_service.point_prediction(longitude, latitude, samples)
    except Exception:
        pass  # The terrain result is still returned if the rain model or forecast is unavailable.
    return result


@lru_cache(maxsize=1)
def province_terrain_shares() -> dict[str, float]:
    """Share of each province's land (sampled at the 13,594 nationwide scan-grid points) rated high flood-prone.

    Reads the precomputed MindSpore susceptibility map; the result is cached on disk next to it.
    """
    cache = NATIONAL_DIRECTORY / "province_shares.json"
    if cache.is_file():
        return json.loads(cache.read_text(encoding="utf-8"))
    from app.services.nationwide_grid import land_tiles

    by_chunk: dict[tuple[int, int], list[Any]] = {}
    for tile in land_tiles():
        by_chunk.setdefault((int(np.floor(tile.longitude)), int(np.floor(tile.latitude))), []).append(tile)
    high: dict[str, int] = {}
    total: dict[str, int] = {}
    for (west, south), tiles in by_chunk.items():
        path = NATIONAL_DIRECTORY / f"{west}E_{south}N.npy"
        scores = np.load(path).astype(np.float32) / 255.0 if path.is_file() else None
        for tile in tiles:
            total[tile.province] = total.get(tile.province, 0) + 1
            if scores is None:
                continue
            row = min(scores.shape[0] - 1, int((south + 1 - tile.latitude) / CELL_DEGREES))
            column = min(scores.shape[1] - 1, int((tile.longitude - west) / CELL_DEGREES))
            high[tile.province] = high.get(tile.province, 0) + int(scores[row, column] >= HIGH_SCORE)
    shares = {name: high.get(name, 0) / count for name, count in total.items()}
    cache.write_text(json.dumps(shares), encoding="utf-8")
    return shares


_outlook_cache: dict[tuple[str, str], bytes] = {}


def render_outlook_chunk(chunk_id: str, samples: list[dict[str, Any]], fetched_at: str) -> bytes:
    """The flood-prone map of one 1-degree chunk, recoloured by the real forecast rain over each pixel."""
    import io

    from PIL import Image

    from app.services.weather_fields import outlook_rgba

    key = (chunk_id, fetched_at)
    if key not in _outlook_cache:
        path = chunk_png(chunk_id)
        west, south = (int(part[:-1]) for part in chunk_id.split("_"))
        base = np.array(Image.open(path).convert("RGBA"))
        recoloured = outlook_rgba(base, _scores(chunk_id), west, south, samples)
        buffer = io.BytesIO()
        Image.fromarray(recoloured, mode="RGBA").save(buffer, format="PNG", optimize=True)
        for stale in [item for item in _outlook_cache if item[1] != fetched_at]:
            del _outlook_cache[stale]
        _outlook_cache[key] = buffer.getvalue()
    return _outlook_cache[key]


async def province_outlook() -> dict[str, Any]:
    """The province forecast with an automatic MindSpore-based flood outlook added to every province."""
    forecast = await get_province_forecast()
    try:
        _index()
        shares = province_terrain_shares()
    except SusceptibilityUnavailableError:
        shares = {}
    features = []
    for feature in forecast["features"]:
        properties = dict(feature["properties"])
        share = shares.get(properties["name"])
        if share is None:
            properties.update(flood_level="unknown", flood_terrain="unknown", flood_message="Terrain model not available.", terrain_share=None)
        else:
            watch = flood_watch(_local_from_share(share), properties)
            properties.update(flood_level=watch["level"], flood_terrain=watch["terrain"], flood_rain=watch["rain"],
                              flood_message=watch["message"], terrain_share=round(share, 3))
        features.append({**feature, "properties": properties})
    return {**forecast, "features": features}


def _local_from_share(share: float) -> dict[str, float]:
    return {"point_score": 0.0, "radius_km": 0.0, "land_share_high": share, "land_share_moderate_or_high": share}
