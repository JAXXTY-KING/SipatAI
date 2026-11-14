import base64
import io
import sys
import threading
from collections import OrderedDict
from datetime import date as Date, datetime, timedelta, timezone
from typing import Any

import numpy as np
from PIL import Image

from app.core.config import REPOSITORY_ROOT, get_flood_model_checkpoint

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

FLOOD_THRESHOLD = 0.5
FLOOD_COLOUR = (37, 99, 235)
CACHE_SIZE = 16
LATEST_WINDOW_DAYS = 30
EVENT_RADAR_WINDOW_DAYS = 7
EVENT_OPTICAL_WINDOW_DAYS = 12

_predictor = None
_predictor_lock = threading.Lock()
_result_cache: OrderedDict[tuple, dict[str, Any]] = OrderedDict()
_cache_lock = threading.Lock()


class FloodModelUnavailableError(RuntimeError):
    """Raised when MindSpore or a trained checkpoint is not available locally."""


class FloodModelDataError(RuntimeError):
    """Raised when no suitable satellite scene could be read for the request."""


def _load_predictor():
    global _predictor
    with _predictor_lock:
        if _predictor is None:
            try:
                from ml.inference.predictor import CheckpointError, FloodPredictor
            except ImportError as error:
                raise FloodModelUnavailableError(
                    "MindSpore is not installed in the backend environment. "
                    "Install backend/requirements-ml.txt."
                ) from error
            try:
                _predictor = FloodPredictor(get_flood_model_checkpoint())
            except CheckpointError as error:
                raise FloodModelUnavailableError(
                    f"{error}. Train a model with ml/README.md or set SIPATAI_MODEL_CHECKPOINT."
                ) from error
    return _predictor


def get_model_status() -> dict[str, Any]:
    """Describe the local MindSpore model without loading it."""
    checkpoint = get_flood_model_checkpoint()
    status: dict[str, Any] = {
        "framework": "MindSpore",
        "architecture": "ResNet-50 U-Net",
        "checkpoint_present": checkpoint.is_file(),
        "ready": False,
        "reason": None,
    }
    try:
        import mindspore

        status["mindspore_version"] = mindspore.__version__
    except ImportError:
        status["reason"] = "MindSpore is not installed in the backend environment."
        return status
    if not checkpoint.is_file():
        status["reason"] = "No trained checkpoint found. Train one with the ml/ pipeline."
        return status
    from ml.inference.predictor import read_model_card

    card = read_model_card(checkpoint)
    validation = [entry for entry in card.get("history", []) if entry.get("best")]
    status.update(
        ready=True,
        label_source=card.get("label_source"),
        validation=validation[-1]["validation"] if validation and "validation" in validation[-1] else None,
        test=card.get("test"),
        trained_epochs=len(card.get("history", [])) or None,
    )
    return status


def _date_ranges(requested: str | None) -> tuple[str, str, str | None]:
    """Return STAC ranges for radar and optical scenes and the radar target datetime."""
    if requested is None:
        end = datetime.now(timezone.utc)
        window = f"{(end - timedelta(days=LATEST_WINDOW_DAYS)).date()}/{end.date()}"
        return window, window, None
    event = Date.fromisoformat(requested)
    radar = timedelta(days=EVENT_RADAR_WINDOW_DAYS)
    optical = timedelta(days=EVENT_OPTICAL_WINDOW_DAYS)
    return (
        f"{event - radar}/{event + radar}",
        f"{event - optical}/{event + optical}",
        f"{event}T00:00:00Z",
    )


def _overlay_png(probability: np.ndarray) -> str:
    flooded = probability >= FLOOD_THRESHOLD
    rgba = np.zeros((*probability.shape, 4), dtype=np.uint8)
    rgba[flooded, :3] = FLOOD_COLOUR
    rgba[flooded, 3] = np.clip(120 + probability[flooded] * 110, 0, 230).astype(np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buffer, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _permanent_water_mask(pc, grid, bbox, radar_target: str | None) -> np.ndarray:
    """Mark open water already present in the dry season (sea, rivers, ponds).

    Training labels exclude this water, so inference applies the same dry-season radar
    reference; otherwise every permanent water body would be reported as a flood.
    """
    from ml.data.features import sar_water_mask

    reference_date = datetime.fromisoformat(radar_target.replace("Z", "+00:00")) if radar_target else datetime.now(timezone.utc)
    year = reference_date.year if reference_date.month >= 4 else reference_date.year - 1
    try:
        items = pc.search_items(pc.SENTINEL_1, bbox, f"{year}-02-01/{year}-03-15")
        vv, vh = pc.read_radar(pc.select_sentinel_1(items), grid)
    except Exception as error:
        raise FloodModelDataError("The dry-season radar reference could not be retrieved right now.") from error
    return sar_water_mask(vv, vh)


def analyze_area(longitude: float, latitude: float, requested_date: str | None) -> dict[str, Any]:
    """Fetch co-registered Sentinel-1/2 data for a tile and run the MindSpore model on it."""
    predictor = _load_predictor()
    from ml.data import planetary_computer as pc

    grid = pc.make_grid(longitude, latitude)
    cache_key = (grid.crs, grid.transform.c, grid.transform.f, requested_date, requested_date or Date.today())
    with _cache_lock:
        if cache_key in _result_cache:
            _result_cache.move_to_end(cache_key)
            return _result_cache[cache_key]

    radar_range, optical_range, radar_target = _date_ranges(requested_date)
    bbox = pc.grid_bbox(grid)
    try:
        radar_items = pc.search_items(pc.SENTINEL_1, bbox, radar_range)
        optical_items = pc.search_items(pc.SENTINEL_2, bbox, optical_range, max_cloud_cover=80)
        scene = pc.read_scene(
            grid,
            pc.select_sentinel_1(radar_items, radar_target),
            pc.select_sentinel_2(optical_items),
        )
    except pc.SceneUnavailableError as error:
        raise FloodModelDataError(str(error)) from error
    except Exception as error:
        raise FloodModelDataError("Satellite data could not be retrieved right now.") from error

    probability = predictor.predict_probability(scene.features)
    permanent_water = _permanent_water_mask(pc, grid, bbox, radar_target)
    probability = np.where(permanent_water, 0.0, probability).astype(np.float32)
    flooded = probability >= FLOOD_THRESHOLD
    pixel_area_km2 = pc.PIXEL_SIZE_METRES**2 / 1_000_000
    clear_fraction = float(scene.optical_clear.mean())
    result = {
        "model": {"framework": "MindSpore", "architecture": "ResNet-50 U-Net"},
        "overlay": {
            "image": _overlay_png(probability),
            "coordinates": [[float(x), float(y)] for x, y in grid.corners],
        },
        "statistics": {
            "flooded_area_km2": round(float(flooded.sum()) * pixel_area_km2, 3),
            "tile_area_km2": round(flooded.size * pixel_area_km2, 3),
            "flooded_fraction": round(float(flooded.mean()), 4),
            "mean_flood_confidence": round(float(probability[flooded].mean()), 3) if flooded.any() else None,
        },
        "observations": {
            "sentinel_1": {"id": scene.sentinel_1_id, "datetime": scene.sentinel_1_datetime},
            "sentinel_2": {
                "id": scene.sentinel_2_id,
                "datetime": scene.sentinel_2_datetime,
                "cloud_cover_percent": round(scene.sentinel_2_cloud_cover, 1),
                "clear_pixel_fraction": round(clear_fraction, 3),
            },
        },
        "warnings": (
            ["Optical imagery over this tile is mostly cloudy; optical channels are unreliable."]
            if clear_fraction < 0.5
            else []
        ),
    }
    with _cache_lock:
        _result_cache[cache_key] = result
        while len(_result_cache) > CACHE_SIZE:
            _result_cache.popitem(last=False)
    return result
