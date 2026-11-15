import io
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

import numpy as np

from app.core.config import REPOSITORY_ROOT
from app.db.scan_store import overlay_path, save_scan
from app.services import flood_model_service as model_service
from app.services.nationwide_grid import Tile

if str(REPOSITORY_ROOT) not in sys.path:
    sys.path.insert(0, str(REPOSITORY_ROOT))

OPTICAL_WINDOW_DAYS = 6
MAX_OPTICAL_CLOUD_PERCENT = 30.0


def _newest_radar_item(pc, bbox, window_days: int, until: datetime):
    start = until - timedelta(days=window_days)
    items = pc.search_items(pc.SENTINEL_1, bbox, f"{start.date()}/{until.date()}")
    if not items:
        raise pc.SceneUnavailableError(f"No Sentinel-1 scene in the last {window_days} days.")
    return items[0]


def _matching_optical_item(pc, bbox, radar_item) -> dict[str, Any] | None:
    """Clearest Sentinel-2 scene close in time to the radar pass, or None so radar alone is used."""
    radar_time = datetime.fromisoformat(radar_item["properties"]["datetime"].replace("Z", "+00:00"))
    window = timedelta(days=OPTICAL_WINDOW_DAYS)
    items = pc.search_items(
        pc.SENTINEL_2, bbox, f"{(radar_time - window).date()}/{(radar_time + window).date()}",
        max_cloud_cover=MAX_OPTICAL_CLOUD_PERCENT,
    )
    return pc.select_sentinel_2(items) if items else None


def _permanent_water(pc, tile: Tile, grid, bbox, radar_datetime: str) -> np.ndarray:
    """Dry-season open water for a tile; it does not change between scans, so it is cached on disk."""
    cache = overlay_path(tile.tile_id).parent.parent / "static_water" / f"{tile.tile_id}.npy"
    if cache.is_file():
        return np.unpackbits(np.load(cache)).reshape(pc.INPUT_SIZE).astype(bool)
    mask = model_service._permanent_water_mask(pc, grid, bbox, radar_datetime)
    cache.parent.mkdir(parents=True, exist_ok=True)
    np.save(cache, np.packbits(mask.astype(np.uint8)))
    return mask


def scan_tile(tile: Tile, window_days: int = 14, until: datetime | None = None) -> dict[str, Any]:
    """Run the MindSpore flood model on the newest Sentinel-1 pass over one tile and store the result.

    Optical imagery is used only when a clear Sentinel-2 scene exists near the radar date; otherwise
    the model runs on radar alone, which is less accurate but works under cloud.
    """
    from ml.data import planetary_computer as pc

    until = until or datetime.now(timezone.utc)
    record: dict[str, Any] = {
        "tile_id": tile.tile_id, "latitude": tile.latitude, "longitude": tile.longitude, "province": tile.province,
    }
    try:
        predictor = model_service._load_predictor()
        grid = pc.make_grid(tile.longitude, tile.latitude)
        bbox = pc.grid_bbox(grid)
        radar_item = _newest_radar_item(pc, bbox, window_days, until)
        optical_item = _matching_optical_item(pc, bbox, radar_item)
        scene = pc.read_scene(grid, radar_item, optical_item)
        probability = predictor.predict_probability(scene.features)
        permanent = _permanent_water(pc, tile, grid, bbox, radar_item["properties"]["datetime"])
        probability = np.where(permanent, 0.0, probability).astype(np.float32)
        threshold = model_service._decision_threshold(float(scene.optical_clear.mean()))
        flooded = probability >= threshold
        pixel_km2 = pc.PIXEL_SIZE_METRES**2 / 1_000_000

        png = model_service._overlay_png(probability, None, threshold).split(",", 1)[1]
        import base64

        overlay_path(tile.tile_id).write_bytes(base64.b64decode(png))
        record.update(
            status="ok", message=None,
            s1_date=scene.sentinel_1_datetime[:10],
            s2_date=scene.sentinel_2_datetime[:10] or None,
            mode="radar+optical" if optical_item else "radar-only",
            clear_fraction=round(float(scene.optical_clear.mean()), 3),
            flooded_km2=round(float(flooded.sum()) * pixel_km2, 3),
            flooded_fraction=round(float(flooded.mean()), 4),
            mean_confidence=round(float(probability[flooded].mean()), 3) if flooded.any() else None,
            threshold=threshold,
            corners=[[float(x), float(y)] for x, y in grid.corners],
        )
    except pc.SceneUnavailableError as error:
        record.update(status="no_data", message=str(error))
    except Exception as error:  # a failed tile must not stop a nationwide run
        record.update(status="error", message=f"{type(error).__name__}: {error}"[:300])
    save_scan(record)
    return record
