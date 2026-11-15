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
from app.db.assessment_store import save_assessment
from app.integrations.ftw_fields_client import (
    AVAILABLE_YEARS,
    FieldBoundaryError,
    field_year_for,
    fetch_fields,
)
from app.services.field_assessment_service import assess_fields

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

FLOOD_THRESHOLD = 0.5
FLOOD_COLOUR = (37, 99, 235)
CROPLAND_FLOOD_COLOUR = (234, 88, 12)
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

    def with_f1(metrics: dict) -> dict:
        precision, recall = metrics["precision"], metrics["recall"]
        return {**metrics, "f1": round(2 * precision * recall / (precision + recall), 4) if precision + recall else 0.0}

    def per_mode(split: str) -> dict | None:
        modes = (card.get("test") or {}).get(split)
        return {mode: with_f1(metrics) for mode, metrics in modes.items()} if modes else None

    status.update(
        ready=True,
        label_source=card.get("label_source"),
        validation=validation[-1]["validation"] if validation and "validation" in validation[-1] else None,
        test_metrics=per_mode("test"),
        unseen_event_metrics=per_mode("bolivia"),
        decision_thresholds=card.get("decision_thresholds"),
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


def _decision_threshold(optical_clear_fraction: float | None = None) -> float:
    """Flood decision threshold from the model card, chosen on validation data for each input mode.

    Scenes with mostly clear optical imagery use the radar+optical threshold; cloudy scenes rely on
    radar alone and use the radar-only threshold.
    """
    from ml.inference.predictor import read_model_card

    card = read_model_card(get_flood_model_checkpoint())
    thresholds = card.get("decision_thresholds")
    if thresholds:
        mostly_clear = optical_clear_fraction is not None and optical_clear_fraction >= 0.5
        value = thresholds.get("radar_optical" if mostly_clear else "radar_only")
    else:
        value = card.get("decision_threshold", FLOOD_THRESHOLD)
    return float(value) if value is not None and 0.0 < float(value) < 1.0 else FLOOD_THRESHOLD


def _overlay_png(probability: np.ndarray, cropland: np.ndarray | None = None, threshold: float = FLOOD_THRESHOLD) -> str:
    """Draw flooded pixels in blue (orange on cropland) with softened edges.

    Only the transparency is smoothed; the flooded/not-flooded decision at each pixel is unchanged.
    """
    from scipy.ndimage import gaussian_filter

    flooded = probability >= threshold
    rgba = np.zeros((*probability.shape, 4), dtype=np.uint8)
    rgba[..., :3] = FLOOD_COLOUR
    if cropland is not None:
        rgba[cropland, :3] = CROPLAND_FLOOD_COLOUR
    strength = np.clip(0.55 + (probability - threshold) / max(1 - threshold, 1e-6) * 0.45, 0.55, 1.0)
    soft = gaussian_filter(np.where(flooded, strength, 0.0), sigma=0.8)
    alpha = np.where(flooded, np.maximum(soft, 0.55), soft * 0.9)
    rgba[..., 3] = np.clip(alpha * 215, 0, 215).astype(np.uint8)
    buffer = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buffer, format="PNG", optimize=True)
    return "data:image/png;base64," + base64.b64encode(buffer.getvalue()).decode("ascii")


def _cropland_statistics(flooded: np.ndarray, cropland: np.ndarray | None, pixel_area_km2: float) -> dict[str, Any] | None:
    """Summarise flooding on ESA WorldCover cropland; None when land cover was unavailable."""
    if cropland is None:
        return None
    cropland_pixels = int(cropland.sum())
    flooded_pixels = int((flooded & cropland).sum())
    return {
        "cropland_area_km2": round(cropland_pixels * pixel_area_km2, 3),
        "flooded_cropland_km2": round(flooded_pixels * pixel_area_km2, 3),
        "flooded_share_of_cropland": round(flooded_pixels / cropland_pixels, 4) if cropland_pixels else None,
        "land_cover_source": "ESA WorldCover 2021 v200, class 40 (cropland), 10 m",
    }


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
            pc.select_sentinel_2(optical_items) if optical_items else None,
        )
    except pc.SceneUnavailableError as error:
        raise FloodModelDataError(str(error)) from error
    except Exception as error:
        raise FloodModelDataError("Satellite data could not be retrieved right now.") from error

    probability = predictor.predict_probability(scene.features)
    permanent_water = _permanent_water_mask(pc, grid, bbox, radar_target)
    probability = np.where(permanent_water, 0.0, probability).astype(np.float32)
    threshold = _decision_threshold(float(scene.optical_clear.mean()))
    flooded = probability >= threshold
    try:
        cropland = pc.read_cropland(grid)
    except Exception:
        cropland = None
    pixel_area_km2 = pc.PIXEL_SIZE_METRES**2 / 1_000_000
    clear_fraction = float(scene.optical_clear.mean())
    warnings = []
    if not scene.sentinel_2_id:
        warnings.append("No usable optical scene was found, so only radar was used (less accurate, but not affected by cloud).")
    elif clear_fraction < 0.5:
        warnings.append("Optical imagery over this tile is mostly cloudy; the model relied mainly on radar there.")
    if cropland is None:
        warnings.append("Land cover was unavailable, so flooded cropland could not be calculated.")

    field_year = field_year_for(int(requested_date[:4]) if requested_date else None)
    field_collection, field_summary = None, None
    try:
        field_result = assess_fields(
            fetch_fields(bbox, field_year), flooded, grid.crs, grid.transform, field_year
        )
        field_collection, field_summary = field_result["geojson"], field_result["summary"]
        if requested_date and int(requested_date[:4]) not in AVAILABLE_YEARS:
            warnings.append(f"Field boundaries are from {field_year}, the closest available mapping year to the event.")
        if field_summary["fields_analysed"] == 0:
            warnings.append("No mapped farm fields were found in this tile.")
    except FieldBoundaryError:
        warnings.append("Field boundaries could not be retrieved, so per-field results are unavailable.")

    result = {
        "model": {"framework": "MindSpore", "architecture": "ResNet-50 U-Net"},
        "overlay": {
            "image": _overlay_png(probability, cropland, threshold),
            "coordinates": [[float(x), float(y)] for x, y in grid.corners],
        },
        "statistics": {
            "flooded_area_km2": round(float(flooded.sum()) * pixel_area_km2, 3),
            "tile_area_km2": round(flooded.size * pixel_area_km2, 3),
            "flooded_fraction": round(float(flooded.mean()), 4),
            "mean_flood_confidence": round(float(probability[flooded].mean()), 3) if flooded.any() else None,
        },
        "cropland": _cropland_statistics(flooded, cropland, pixel_area_km2),
        "fields": field_collection,
        "field_summary": field_summary,
        "observations": {
            "sentinel_1": {"id": scene.sentinel_1_id, "datetime": scene.sentinel_1_datetime},
            "sentinel_2": {
                "id": scene.sentinel_2_id,
                "datetime": scene.sentinel_2_datetime,
                "used": bool(scene.sentinel_2_id),
                "cloud_cover_percent": round(scene.sentinel_2_cloud_cover, 1) if scene.sentinel_2_id else None,
                "clear_pixel_fraction": round(clear_fraction, 3),
            },
        },
        "warnings": warnings,
    }
    saved = {key: result[key] for key in ("model", "statistics", "cropland", "field_summary", "observations", "warnings")}
    saved["decision_threshold"] = threshold
    result["assessment_id"] = save_assessment(latitude, longitude, requested_date, saved)

    with _cache_lock:
        _result_cache[cache_key] = result
        while len(_result_cache) > CACHE_SIZE:
            _result_cache.popitem(last=False)
    return result
