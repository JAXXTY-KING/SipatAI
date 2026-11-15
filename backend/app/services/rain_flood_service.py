"""Rain-driven flood forecast from the MindSpore RainFloodNet, drawn at 90 m on the real terrain.

Inputs per 90 m cell: five terrain features (Copernicus DEM, JRC water history) and the real forecast rain
(wettest 24 h and 72 h total from Open-Meteo). The network was trained on 11 real flood events (Sen1Floods11 labels,
ERA5 rain) and tested on events it had never seen; see ml/artifacts/rain_flood/model_card.json.
"""
import io
import json
import threading
from functools import lru_cache
from typing import Any

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter, zoom

from app.core.config import REPOSITORY_ROOT
from app.services.susceptibility_service import NATIONAL_DIRECTORY, SusceptibilityUnavailableError, _scores, chunk_png
from app.services.weather_fields import _interpolate

DIRECTORY = REPOSITORY_ROOT / "ml" / "artifacts" / "rain_flood"
UPLIFT_MIN, UPLIFT_RAMP = 0.04, 0.08  # probability a cell must gain from rain before it is drawn, and how fast it fades in
MIN_RAIN_MM, RAIN_RAMP_MM = 10.0, 20.0  # forecast wettest-24 h rain below which nothing is drawn, and the fade-in range
DEFAULT_THRESHOLDS = {"advisory": 0.51, "watch": 0.65, "warning": 0.8}
COLOURS = {"advisory": (240, 201, 58), "watch": (238, 138, 43), "warning": (200, 62, 62), "extreme": (127, 29, 29)}
_lock = threading.Lock()
_cache: dict[tuple[str, str], bytes] = {}


def _card() -> dict[str, Any] | None:
    path = DIRECTORY / "model_card.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def thresholds() -> dict[str, float]:
    levels = (_card() or {}).get("levels", {})
    return {name: levels.get(name, {}).get("threshold", DEFAULT_THRESHOLDS[name]) for name in DEFAULT_THRESHOLDS}


def get_status() -> dict[str, Any]:
    card = _card()
    cached = len(list(NATIONAL_DIRECTORY.glob("*.feat.npy"))) if NATIONAL_DIRECTORY.is_dir() else 0
    if card is None or not (DIRECTORY / "rain_flood.ckpt").is_file():
        return {"framework": "MindSpore", "ready": False, "reason": "The rain flood model has not been trained yet."}
    auc = card["heldout_event_auc"]
    return {
        "framework": "MindSpore",
        "ready": cached > 0,
        "model": card["model"],
        "events": len(card["events"]),
        "cells": card["cells"],
        "rain_auc": auc["terrain_and_rain"]["mean"],
        "terrain_only_auc": auc["terrain_only"]["mean"],
        "levels": card["levels"],
        "rain_response": card["rain_response"],
        "chunks_cached": cached,
        "note": card["note"],
    }


@lru_cache(maxsize=1)
def _network():
    import mindspore as ms

    from ml.rain_flood.model import load_rain_flood_net

    ms.set_device("CPU")
    ms.set_context(mode=ms.PYNATIVE_MODE)
    return load_rain_flood_net(DIRECTORY / "rain_flood.ckpt")


def _probability(features: np.ndarray, wettest_day: np.ndarray, total_72h: np.ndarray) -> np.ndarray:
    import mindspore as ms

    from ml.rain_flood.model import encode_rain

    x = np.concatenate([features, encode_rain(wettest_day, total_72h)], axis=1)
    network = _network()
    with _lock:
        logits = np.concatenate([network(ms.Tensor(x[i : i + 131072], ms.float32)).asnumpy()[:, 0] for i in range(0, len(x), 131072)])
    return 1.0 / (1.0 + np.exp(-logits))


def _rain_grid(samples: list[dict[str, Any]], key: str, west: int, south: int, size: int) -> np.ndarray:
    coarse = 48
    longitudes = west + (np.arange(coarse) + 0.5) / coarse
    latitudes = south + 1 - (np.arange(coarse) + 0.5) / coarse
    values, _ = _interpolate(samples, key, *np.meshgrid(longitudes, latitudes))
    return zoom(values, size / coarse, order=1)[:size, :size].astype(np.float32)


def forecast_probability(chunk_id: str, samples: list[dict[str, Any]]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Flood probability (0-1) per 90 m cell with the forecast rain, with no rain, the land mask and the wettest-day rain."""
    path = NATIONAL_DIRECTORY / f"{chunk_id}.feat.npy"
    if not path.is_file():
        raise SusceptibilityUnavailableError("Terrain features for this chunk are not cached yet.")
    scores = _scores(chunk_id)
    land = scores > 0
    features = np.load(path)
    size = land.shape[0]
    west, south = (int(part[:-1]) for part in chunk_id.split("_"))
    wettest = _rain_grid(samples, _rain_key(samples, "24h"), west, south, size)
    total = _rain_grid(samples, _rain_key(samples, "72h"), west, south, size)
    probability = np.zeros(land.shape, dtype=np.float32)
    dry = np.zeros(land.shape, dtype=np.float32)
    rows, columns = np.nonzero(land)
    cells = features[:, rows, columns].T.astype(np.float32) / 255.0
    probability[rows, columns] = _probability(cells, wettest[rows, columns], total[rows, columns])
    no_rain = np.zeros(len(rows), dtype=np.float32)
    dry[rows, columns] = _probability(cells, no_rain, no_rain)
    return probability, dry, land, wettest


def point_prediction(longitude: float, latitude: float, samples: list[dict[str, Any]]) -> dict[str, Any]:
    """The rain model's verdict for the 90 m cell at a point (and the highest in the surrounding 1 km)."""
    west, south = int(np.floor(longitude)), int(np.floor(latitude))
    chunk_id = f"{west}E_{south}N"
    probability, dry, land, wettest = forecast_probability(chunk_id, samples)
    size = land.shape[0]
    cell = 3 / 3600
    row = min(size - 1, int((south + 1 - latitude) / cell))
    column = min(size - 1, int((longitude - west) / cell))
    window = (slice(max(0, row - 5), row + 6), slice(max(0, column - 5), column + 6))
    nearby = float(probability[window][land[window]].max()) if land[window].any() else 0.0
    here = float(probability[row, column])
    limits = thresholds()
    rain_drives = bool(wettest[row, column] >= MIN_RAIN_MM and probability[row, column] - dry[row, column] >= UPLIFT_MIN)
    level = "none"
    if rain_drives:
        level = next((name for name in ("warning", "watch", "advisory") if nearby >= limits[name]), "none")
    return {"probability_here": round(here, 3), "probability_nearby": round(nearby, 3), "level": level,
            "wettest_24h_mm": round(float(wettest[row, column]), 1), "on_land": bool(land[row, column])}


def _rain_key(samples: list[dict[str, Any]], name: str) -> str:
    """The last-72-hours-plus-next-24-hours rain the network was trained on; older cached samples fall back to the forecast."""
    model_key = f"model_rain_{name}_mm"
    return model_key if samples and model_key in samples[0] else f"rainfall_{name}_mm"


def _peak_rain(chunk_id: str, samples: list[dict[str, Any]]) -> float:
    west, south = (int(part[:-1]) for part in chunk_id.split("_"))
    return float(_rain_grid(samples, _rain_key(samples, "24h"), west, south, 48).max())


def _empty_png() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(buffer, format="PNG")
    return buffer.getvalue()


def render_forecast(chunk_id: str, samples: list[dict[str, Any]], fetched_at: str) -> bytes:
    key = (chunk_id, fetched_at)
    if key not in _cache:
        chunk_png(chunk_id)
        if _peak_rain(chunk_id, samples) < MIN_RAIN_MM:
            _cache[key] = _empty_png()  # nothing is drawn under light rain, so skip the model entirely
            return _cache[key]
        probability, dry, land, wettest = forecast_probability(chunk_id, samples)
        smooth = gaussian_filter(probability, 1.4)
        # The network only ever saw flood events, so it is drawn only where it adds flooding on top of dry conditions
        # and where the forecast rain is heavy enough to matter (under 10 mm a day nothing is drawn).
        uplift = np.clip((gaussian_filter(probability - dry, 1.4) - UPLIFT_MIN) / UPLIFT_RAMP, 0, 1)
        uplift *= np.clip((gaussian_filter(wettest, 8.0) - MIN_RAIN_MM) / RAIN_RAMP_MM, 0, 1)
        limits = thresholds()
        advisory, watch, warning = limits["advisory"], limits["watch"], limits["warning"]
        stops = [advisory * 0.8, advisory, watch, warning, min(1.0, warning + 0.12)]
        palette = np.array([COLOURS["advisory"], COLOURS["advisory"], COLOURS["watch"], COLOURS["warning"], COLOURS["extreme"]], dtype=np.float32)
        rgba = np.zeros((*smooth.shape, 4), dtype=np.uint8)
        for channel in range(3):
            rgba[..., channel] = np.interp(smooth, stops, palette[:, channel])
        rgba[..., 3] = np.interp(smooth, stops, [0, 135, 175, 210, 235]) * uplift
        rgba[~land, 3] = 0
        buffer = io.BytesIO()
        Image.fromarray(rgba, mode="RGBA").save(buffer, format="PNG", optimize=True)
        for stale in [item for item in _cache if item[1] != fetched_at]:
            del _cache[stale]
        _cache[key] = buffer.getvalue()
    return _cache[key]
