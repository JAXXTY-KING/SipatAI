import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.transform import Affine
from rasterio.vrt import WarpedVRT
from rasterio.warp import transform as transform_coordinates

from ml.configs.model_config import INPUT_SIZE
from ml.data.features import build_feature_stack, normalised_difference

STAC_SEARCH_URL = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
TOKEN_URL = "https://planetarycomputer.microsoft.com/api/sas/v1/token/{collection}"
SENTINEL_1 = "sentinel-1-rtc"
SENTINEL_2 = "sentinel-2-l2a"
WORLDCOVER = "esa-worldcover"
WORLDCOVER_CROPLAND = 40
PIXEL_SIZE_METRES = 10.0
CLEAR_SCL_CLASSES = (4, 5, 6, 7)
MIN_VALID_FRACTION = 0.9

_token_lock = threading.Lock()
_tokens: dict[str, tuple[str, float]] = {}


class SceneUnavailableError(RuntimeError):
    """Raised when no suitable Sentinel scene covers the requested area."""


@dataclass(frozen=True)
class Grid:
    """A 512 by 512 pixel, 10 metre UTM grid centred on a longitude/latitude."""

    crs: str
    transform: Affine
    corners: tuple[tuple[float, float], ...]


@dataclass(frozen=True)
class SceneStack:
    features: np.ndarray
    vv: np.ndarray
    vh: np.ndarray
    ndwi: np.ndarray
    optical_clear: np.ndarray
    grid: Grid
    sentinel_1_id: str
    sentinel_1_datetime: str
    sentinel_2_id: str
    sentinel_2_datetime: str
    sentinel_2_cloud_cover: float


def make_grid(longitude: float, latitude: float) -> Grid:
    """Build the model tile grid around a point; one tile covers about 5.12 km square."""
    zone = int((longitude + 180.0) // 6.0) + 1
    crs = f"EPSG:{(32600 if latitude >= 0 else 32700) + zone}"
    (x,), (y,) = transform_coordinates("EPSG:4326", crs, [longitude], [latitude])
    height, width = INPUT_SIZE
    left = round(x / PIXEL_SIZE_METRES) * PIXEL_SIZE_METRES - width * PIXEL_SIZE_METRES / 2
    top = round(y / PIXEL_SIZE_METRES) * PIXEL_SIZE_METRES + height * PIXEL_SIZE_METRES / 2
    right = left + width * PIXEL_SIZE_METRES
    bottom = top - height * PIXEL_SIZE_METRES
    xs, ys = transform_coordinates(crs, "EPSG:4326", [left, right, right, left], [top, top, bottom, bottom])
    return Grid(
        crs=crs,
        transform=Affine(PIXEL_SIZE_METRES, 0, left, 0, -PIXEL_SIZE_METRES, top),
        corners=tuple(zip(xs, ys)),
    )


def grid_bbox(grid: Grid) -> tuple[float, float, float, float]:
    longitudes = [corner[0] for corner in grid.corners]
    latitudes = [corner[1] for corner in grid.corners]
    return min(longitudes), min(latitudes), max(longitudes), max(latitudes)


def search_items(
    collection: str,
    bbox: tuple[float, float, float, float],
    date_range: str,
    max_cloud_cover: float | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """Search the public STAC catalogue and return items covering the bbox, newest first."""
    body: dict[str, Any] = {
        "collections": [collection],
        "bbox": list(bbox),
        "datetime": date_range,
        "limit": limit,
        "sortby": [{"field": "datetime", "direction": "desc"}],
    }
    if max_cloud_cover is not None:
        body["query"] = {"eo:cloud_cover": {"lt": max_cloud_cover}}
    response = httpx.post(STAC_SEARCH_URL, json=body, timeout=45.0)
    response.raise_for_status()
    return [item for item in response.json().get("features", []) if _covers(item, bbox)]


def _covers(item: dict[str, Any], bbox: tuple[float, float, float, float]) -> bool:
    west, south, east, north = item["bbox"]
    return west <= bbox[0] and south <= bbox[1] and east >= bbox[2] and north >= bbox[3]


def _signed_href(collection: str, href: str) -> str:
    with _token_lock:
        cached = _tokens.get(collection)
        if cached is None or cached[1] - time.time() < 120:
            response = httpx.get(TOKEN_URL.format(collection=collection), timeout=30.0)
            response.raise_for_status()
            payload = response.json()
            expiry = datetime.fromisoformat(payload["msft:expiry"].replace("Z", "+00:00")).timestamp()
            cached = (payload["token"], expiry)
            _tokens[collection] = cached
    return f"{href}?{cached[0]}"


def _read_band(collection: str, href: str, grid: Grid, resampling: Resampling) -> np.ndarray:
    """Read one asset onto the model grid; invalid pixels become NaN."""
    height, width = INPUT_SIZE
    with rasterio.Env(
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
        CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif,.tiff",
        GDAL_HTTP_MAX_RETRY="3",
        GDAL_HTTP_RETRY_DELAY="1",
    ):
        with rasterio.open(_signed_href(collection, href)) as source:
            source_nodata = source.nodata
            with WarpedVRT(
                source,
                crs=grid.crs,
                transform=grid.transform,
                width=width,
                height=height,
                resampling=resampling,
                src_nodata=source_nodata,
                nodata=source_nodata if source_nodata is not None else 0,
            ) as virtual:
                values = virtual.read(1, masked=True)
    return np.ma.filled(values.astype(np.float32), np.nan)


def _reflectance_scale(item: dict[str, Any]) -> tuple[float, float]:
    """Return (scale, offset) converting Sentinel-2 L2A digital numbers to reflectance."""
    baseline = str(item["properties"].get("s2:processing_baseline", "0"))
    return 0.0001, (-0.1 if float(baseline) >= 4.0 else 0.0)


def select_sentinel_2(items: list[dict[str, Any]]) -> dict[str, Any]:
    """Pick the clearest recent scene; ties keep the newest scene."""
    if not items:
        raise SceneUnavailableError("No Sentinel-2 scene covers this area in the requested period.")
    return min(items, key=lambda item: item["properties"].get("eo:cloud_cover", 100.0))


def select_sentinel_1(items: list[dict[str, Any]], target: str | None = None) -> dict[str, Any]:
    """Pick the newest radar scene, or the one closest to a target ISO datetime."""
    if not items:
        raise SceneUnavailableError("No Sentinel-1 radar scene covers this area in the requested period.")
    if target is None:
        return items[0]
    target_time = datetime.fromisoformat(target.replace("Z", "+00:00")).timestamp()
    return min(
        items,
        key=lambda item: abs(
            datetime.fromisoformat(item["properties"]["datetime"].replace("Z", "+00:00")).timestamp() - target_time
        ),
    )


def read_cropland(grid: Grid) -> np.ndarray | None:
    """Return a boolean cropland mask from ESA WorldCover 2021 (class 40), or None if unavailable."""
    body = {"collections": [WORLDCOVER], "bbox": list(grid_bbox(grid)), "limit": 10}
    response = httpx.post(STAC_SEARCH_URL, json=body, timeout=45.0)
    response.raise_for_status()
    items = [
        item for item in response.json().get("features", [])
        if item["properties"].get("esa_worldcover:product_version") == "2.0.0" and _covers(item, grid_bbox(grid))
    ]
    if not items:
        return None
    classes = _read_band(WORLDCOVER, items[0]["assets"]["map"]["href"], grid, Resampling.nearest)
    if np.isfinite(classes).mean() < MIN_VALID_FRACTION:
        return None
    return np.nan_to_num(classes, nan=0.0) == WORLDCOVER_CROPLAND


def read_radar(item: dict[str, Any], grid: Grid) -> tuple[np.ndarray, np.ndarray]:
    """Read linear VV and VH backscatter for a Sentinel-1 RTC item."""
    with ThreadPoolExecutor(max_workers=2) as pool:
        vv_future = pool.submit(_read_band, SENTINEL_1, item["assets"]["vv"]["href"], grid, Resampling.bilinear)
        vh_future = pool.submit(_read_band, SENTINEL_1, item["assets"]["vh"]["href"], grid, Resampling.bilinear)
        vv, vh = vv_future.result(), vh_future.result()
    if np.isfinite(vv).mean() < MIN_VALID_FRACTION or np.isfinite(vh).mean() < MIN_VALID_FRACTION:
        raise SceneUnavailableError("The Sentinel-1 scene has no usable radar data over this tile.")
    return vv, vh


def read_scene(
    grid: Grid,
    sentinel_1_item: dict[str, Any],
    sentinel_2_item: dict[str, Any],
) -> SceneStack:
    """Read a co-registered radar and optical tile and build the six model channels."""
    scale, offset = _reflectance_scale(sentinel_2_item)
    assets = sentinel_2_item["assets"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        radar_future = pool.submit(read_radar, sentinel_1_item, grid)
        optical = {
            name: pool.submit(_read_band, SENTINEL_2, assets[name]["href"], grid, Resampling.nearest)
            for name in ("B03", "B04", "B08", "SCL")
        }
        vv, vh = radar_future.result()
        green, red, nir, scene_class = (optical[name].result() for name in ("B03", "B04", "B08", "SCL"))

    green, red, nir = (band * scale + offset for band in (green, red, nir))
    optical_clear = np.isin(np.nan_to_num(scene_class, nan=0.0), CLEAR_SCL_CLASSES)
    ndwi = np.where(optical_clear, normalised_difference(np.nan_to_num(green), np.nan_to_num(nir)), 0.0)
    return SceneStack(
        features=build_feature_stack(vv, vh, red, nir, green),
        vv=vv,
        vh=vh,
        ndwi=ndwi.astype(np.float32),
        optical_clear=optical_clear,
        grid=grid,
        sentinel_1_id=sentinel_1_item["id"],
        sentinel_1_datetime=sentinel_1_item["properties"]["datetime"],
        sentinel_2_id=sentinel_2_item["id"],
        sentinel_2_datetime=sentinel_2_item["properties"]["datetime"],
        sentinel_2_cloud_cover=float(sentinel_2_item["properties"].get("eo:cloud_cover", 100.0)),
    )
