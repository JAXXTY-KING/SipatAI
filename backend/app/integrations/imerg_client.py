import io
import math
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

GIBS_TILE = (
    "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/IMERG_Precipitation_Rate_30min/default/"
    "{time}/GoogleMapsCompatible_Level6/{z}/{y}/{x}.png"
)
ZOOM = 6
# Web-mercator tiles covering the Philippines at zoom 6 (longitude 116.4-127.6, latitude 3.8-22).
TILE_COLUMNS = range(52, 55)
TILE_ROWS = range(27, 34)
_cache: tuple[float, dict[str, Any]] | None = None
_image_cache: dict[str, bytes] = {}


def _tile_longitude(column: float) -> float:
    return column / 2**ZOOM * 360.0 - 180.0


def _tile_latitude(row: float) -> float:
    return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * row / 2**ZOOM))))


def image_coordinates() -> list[list[float]]:
    west, east = _tile_longitude(TILE_COLUMNS[0]), _tile_longitude(TILE_COLUMNS[-1] + 1)
    north, south = _tile_latitude(TILE_ROWS[0]), _tile_latitude(TILE_ROWS[-1] + 1)
    return [[west, north], [east, north], [east, south], [west, south]]


async def latest_imerg_time() -> dict[str, Any] | None:
    """Probe NASA GIBS for the newest half-hourly IMERG scene (it is published about 4-6 hours late)."""
    global _cache
    if _cache and time.monotonic() - _cache[0] < 600:
        return _cache[1]
    now = datetime.now(timezone.utc) - timedelta(hours=2)
    candidate = now.replace(minute=30 if now.minute >= 30 else 0, second=0, microsecond=0)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            for _ in range(24):
                stamp = candidate.strftime("%Y-%m-%dT%H:%M:%SZ")
                response = await client.head(GIBS_TILE.format(time=stamp, z=4, y=7, x=13))
                if response.status_code == 200:
                    result = {
                        "time": stamp,
                        "age_hours": round((datetime.now(timezone.utc) - candidate).total_seconds() / 3600, 1),
                        "coordinates": image_coordinates(),
                        "source": "NASA GPM IMERG (via NASA GIBS), satellite precipitation rate",
                    }
                    _cache = (time.monotonic(), result)
                    return result
                candidate -= timedelta(minutes=30)
    except httpx.HTTPError:
        return _cache[1] if _cache else None
    return None


async def imerg_image(stamp: str) -> bytes:
    """The real IMERG rain scene over the Philippines, stitched from NASA tiles and feathered so it reads as rain, not blocks."""
    if stamp not in _image_cache:
        columns, rows = len(TILE_COLUMNS), len(TILE_ROWS)
        canvas = Image.new("RGBA", (256 * columns, 256 * rows), (0, 0, 0, 0))
        async with httpx.AsyncClient(timeout=30) as client:
            for column_index, x in enumerate(TILE_COLUMNS):
                for row_index, y in enumerate(TILE_ROWS):
                    response = await client.get(GIBS_TILE.format(time=stamp, z=ZOOM, y=y, x=x))
                    if response.status_code == 200:
                        tile = Image.open(io.BytesIO(response.content)).convert("RGBA")
                        canvas.paste(tile, (256 * column_index, 256 * row_index))
        rgba = np.array(canvas).astype(np.float32)
        alpha = rgba[..., 3:4] / 255.0
        premultiplied = np.concatenate([rgba[..., :3] * alpha, alpha], axis=-1)
        blurred = np.stack([gaussian_filter(premultiplied[..., channel], 3.0) for channel in range(4)], axis=-1)
        soft_alpha = np.clip(blurred[..., 3:4] * 1.35, 0, 1)
        colour = np.where(blurred[..., 3:4] > 1e-3, blurred[..., :3] / np.maximum(blurred[..., 3:4], 1e-3), 0)
        output = np.concatenate([colour, soft_alpha * 255 * 0.9], axis=-1).clip(0, 255).astype(np.uint8)
        buffer = io.BytesIO()
        Image.fromarray(output, mode="RGBA").save(buffer, format="PNG", optimize=True)
        _image_cache.clear()
        _image_cache[stamp] = buffer.getvalue()
    return _image_cache[stamp]

