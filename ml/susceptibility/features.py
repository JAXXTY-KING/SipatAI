"""Terrain and flood-history features for flood susceptibility, from public Planetary Computer data.

Real inputs only: Copernicus DEM GLO-30 elevation and JRC Global Surface Water occurrence
(Landsat, 1984-2020). Tiles are 512 x 512 pixels at 30 m, about 15.4 km square.
"""
import httpx
import numpy as np
from rasterio.enums import Resampling
from scipy.ndimage import distance_transform_edt, minimum_filter

from ml.configs.model_config import INPUT_SIZE
from ml.data import planetary_computer as pc

DEM = "cop-dem-glo-30"
GSW = "jrc-gsw"
PIXEL_METRES = 30.0
FEATURE_NAMES = ("elevation", "relief_1km", "relief_3km", "slope", "distance_to_permanent_water")
PERMANENT_WATER_OCCURRENCE = 80
TEMPORARY_WATER_RANGE = (3, 60)  # JRC occurrence (%) of land that is water only part of the time
MAX_DISTANCE_METRES = 15_000.0


def make_terrain_grid(longitude: float, latitude: float) -> pc.Grid:
    return pc.make_grid(longitude, latitude, PIXEL_METRES)


def _items(collection: str, bbox) -> list[dict]:
    body = {"collections": [collection], "bbox": list(bbox), "limit": 12}
    response = httpx.post(pc.STAC_SEARCH_URL, json=body, timeout=45.0)
    response.raise_for_status()
    return response.json()["features"]


def read_elevation(grid: pc.Grid) -> np.ndarray:
    """Elevation in metres on the grid (sea is 0). DEM tiles are 1 degree, so neighbours are merged."""
    elevation = np.full(INPUT_SIZE, np.nan, dtype=np.float32)
    for item in _items(DEM, pc.grid_bbox(grid)):
        band = pc._read_band(DEM, item["assets"]["data"]["href"], grid, Resampling.bilinear)
        elevation = np.where(np.isfinite(band), band, elevation)
    if not np.isfinite(elevation).mean() > 0.9:
        raise pc.SceneUnavailableError("Elevation data does not cover this area.")
    return np.nan_to_num(elevation, nan=0.0)


def read_water_occurrence(grid: pc.Grid) -> np.ndarray:
    """JRC share of valid observations (0-100) in which each pixel was water; NaN where unobserved."""
    occurrence = np.full(INPUT_SIZE, np.nan, dtype=np.float32)
    for item in _items(GSW, pc.grid_bbox(grid)):
        band = pc._read_band(GSW, item["assets"]["occurrence"]["href"], grid, Resampling.nearest, nodata=255)
        occurrence = np.where(np.isfinite(band), band, occurrence)
    return occurrence


def build_features(elevation: np.ndarray, occurrence: np.ndarray) -> np.ndarray:
    """Five terrain channels scaled to about 0-1: elevation, local relief at two radii, slope, water distance."""
    slope_y, slope_x = np.gradient(elevation, PIXEL_METRES)
    slope = np.degrees(np.arctan(np.hypot(slope_x, slope_y)))
    relief_1km = elevation - minimum_filter(elevation, size=33, mode="nearest")
    relief_3km = elevation - minimum_filter(elevation, size=101, mode="nearest")
    permanent = np.nan_to_num(occurrence, nan=0.0) >= PERMANENT_WATER_OCCURRENCE
    if permanent.any():
        distance = np.minimum(distance_transform_edt(~permanent) * PIXEL_METRES, MAX_DISTANCE_METRES)
    else:
        distance = np.full(INPUT_SIZE, MAX_DISTANCE_METRES)
    return np.stack(
        (
            np.log1p(np.clip(elevation, 0, 3000)) / np.log1p(3000),
            np.clip(relief_1km, 0, 100) / 100,
            np.clip(relief_3km, 0, 300) / 300,
            np.clip(slope, 0, 45) / 45,
            np.log1p(distance) / np.log1p(MAX_DISTANCE_METRES),
        )
    ).astype(np.float32)


def history_labels(occurrence: np.ndarray, elevation: np.ndarray) -> np.ndarray:
    """1 = land that Landsat saw underwater only part of the time, 0 = never water, -1 = ignore."""
    low, high = TEMPORARY_WATER_RANGE
    observed = np.isfinite(occurrence)
    value = np.nan_to_num(occurrence, nan=0.0)
    labels = np.full(occurrence.shape, -1, dtype=np.int8)
    labels[observed & (value <= 1) & (elevation > 0.5)] = 0
    labels[observed & (value >= low) & (value < high)] = 1
    return labels
