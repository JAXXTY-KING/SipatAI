import base64
import io
import os
import sys
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image
from shapely.geometry import Point

from app.core.config import REPOSITORY_ROOT
from app.integrations.province_forecast_client import _provinces, get_province_forecast

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

MODERATE_SCORE = 0.5
HIGH_SCORE = 0.75
CACHE_SIZE = 12
PIXEL_KM2 = 0.03 * 0.03

_network = None
_network_lock = threading.Lock()
_cache: OrderedDict[tuple, dict[str, Any]] = OrderedDict()
_cache_lock = threading.Lock()


class SusceptibilityUnavailableError(RuntimeError):
    """Raised when the trained susceptibility model or its terrain data cannot be used."""


def _checkpoint() -> Path:
    configured = os.getenv("SIPATAI_SUSCEPTIBILITY_CHECKPOINT", "").strip()
    return Path(configured) if configured else REPOSITORY_ROOT / "ml" / "artifacts" / "susceptibility" / "susceptibility.ckpt"


def get_susceptibility_status() -> dict[str, Any]:
    checkpoint = _checkpoint()
    card_path = checkpoint.with_name("model_card.json")
    status: dict[str, Any] = {"framework": "MindSpore", "ready": checkpoint.is_file()}
    if card_path.is_file():
        import json

        card = json.loads(card_path.read_text(encoding="utf-8"))
        status.update(
            label=card.get("label"),
            inputs=card.get("inputs"),
            heldout_province_auc=card.get("final", {}).get("heldout_province_auc"),
            observed_flood_validation=card.get("observed_flood_validation"),
        )
    if not checkpoint.is_file():
        status["reason"] = "The susceptibility model has not been trained yet (see ml/README.md)."
    return status


def _load_network():
    global _network
    with _network_lock:
        if _network is None:
            checkpoint = _checkpoint()
            if not checkpoint.is_file():
                raise SusceptibilityUnavailableError("The susceptibility model has not been trained yet.")
            try:
                from ml.susceptibility.model import load_susceptibility_net
            except ImportError as error:
                raise SusceptibilityUnavailableError("MindSpore is not installed in the backend environment.") from error
            _network = load_susceptibility_net(checkpoint)
    return _network


def _score_map(features: np.ndarray) -> np.ndarray:
    import mindspore as ms
    from mindspore import Tensor

    network = _load_network()
    flat = np.ascontiguousarray(features.reshape(features.shape[0], -1).T)
    with _network_lock:
        logits = np.concatenate(
            [network(Tensor(flat[i : i + 65536], ms.float32)).asnumpy()[:, 0] for i in range(0, len(flat), 65536)]
        )
    return (1.0 / (1.0 + np.exp(-logits))).reshape(features.shape[1:]).astype(np.float32)


def _overlay_png(score: np.ndarray) -> str:
    rgba = np.zeros((*score.shape, 4), dtype=np.uint8)
    moderate = (score >= MODERATE_SCORE) & (score < HIGH_SCORE)
    high = score >= HIGH_SCORE
    rgba[moderate] = (251, 191, 36, 120)
    rgba[high] = (220, 38, 38, 170)
    buffer = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buffer, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


async def _forecast_for(longitude: float, latitude: float) -> dict[str, Any] | None:
    """The real Open-Meteo forecast for the province containing the point, if it is available."""
    try:
        features, geometries = _provinces()
        forecast = await get_province_forecast()
    except Exception:
        return None
    point = Point(longitude, latitude)
    for index, geometry in enumerate(geometries):
        if geometry.covers(point):
            properties = forecast["features"][index]["properties"]
            return {
                "province": properties["name"],
                "rainfall_24h_mm": properties["rainfall_24h_mm"],
                "rainfall_72h_mm": properties["rainfall_72h_mm"],
                "screening_level": properties["screening_level"],
                "forecast_start": properties["forecast_start"],
            }
    return None


def _outlook(forecast: dict[str, Any] | None, high_km2: float) -> str:
    if forecast is None:
        return "Rainfall forecast unavailable; showing where water tends to collect, not a forecast."
    level = forecast["screening_level"]
    if level == "elevated":
        return "Heavy rain is forecast for this province: the red and amber areas are where floodwater is most likely to collect."
    if level == "watch":
        return "Significant rain is forecast: the red and amber areas are the most likely to flood if the rain falls here."
    return "No heavy rain is forecast for this province in the next 72 h. Red and amber areas are flood-prone terrain, not a flood warning."


def susceptibility_for_tile(longitude: float, latitude: float) -> dict[str, Any]:
    from ml.data import planetary_computer as pc
    from ml.susceptibility import features as terrain

    grid = terrain.make_terrain_grid(longitude, latitude)
    key = (grid.crs, grid.transform.c, grid.transform.f)
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    try:
        elevation = terrain.read_elevation(grid)
        occurrence = terrain.read_water_occurrence(grid)
    except pc.SceneUnavailableError as error:
        raise SusceptibilityUnavailableError(str(error)) from error
    except Exception as error:
        raise SusceptibilityUnavailableError("Terrain data could not be retrieved right now.") from error

    score = _score_map(terrain.build_features(elevation, occurrence))
    land_only = (elevation > 0.5) & (np.nan_to_num(occurrence, nan=0.0) < terrain.PERMANENT_WATER_OCCURRENCE)
    score = np.where(land_only, score, 0.0).astype(np.float32)
    high, moderate = score >= HIGH_SCORE, (score >= MODERATE_SCORE) & (score < HIGH_SCORE)
    land_km2 = float(land_only.sum()) * PIXEL_KM2
    result = {
        "model": {"framework": "MindSpore", "name": "SusceptibilityNet"},
        "overlay": {
            "image": _overlay_png(score),
            "coordinates": [[float(x), float(y)] for x, y in grid.corners],
        },
        "statistics": {
            "tile_km2": round(score.size * PIXEL_KM2, 1),
            "land_km2": round(land_km2, 1),
            "high_km2": round(float(high.sum()) * PIXEL_KM2, 2),
            "moderate_km2": round(float(moderate.sum()) * PIXEL_KM2, 2),
            "high_share_of_land": round(float(high.sum()) * PIXEL_KM2 / land_km2, 4) if land_km2 else None,
        },
        "thresholds": {"moderate": MODERATE_SCORE, "high": HIGH_SCORE},
        "data": "Copernicus DEM GLO-30 (30 m) and JRC Global Surface Water 1984-2020 (Landsat)",
    }
    with _cache_lock:
        _cache[key] = result
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return result


async def predict_flood_prone_areas(longitude: float, latitude: float) -> dict[str, Any]:
    from fastapi.concurrency import run_in_threadpool

    result = dict(await run_in_threadpool(susceptibility_for_tile, longitude, latitude))
    forecast = await _forecast_for(longitude, latitude)
    result["forecast"] = forecast
    result["outlook"] = _outlook(forecast, result["statistics"]["high_km2"])
    return result
