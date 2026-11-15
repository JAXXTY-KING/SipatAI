"""Terrain and flood-history features for flood susceptibility.

Real inputs only: Copernicus DEM GLO-90 elevation (3 arc-second cells, about 90 m) and JRC Global Surface Water
occurrence (Landsat, 1984-2020). Files are downloaded once by ml.susceptibility.download.
"""
import math
from pathlib import Path

import numpy as np
import rasterio
from rasterio.enums import Resampling
from rasterio.merge import merge
from scipy.ndimage import distance_transform_edt, minimum_filter

CACHE = Path("ml/artifacts/susceptibility/cache")
CELL_DEGREES = 3 / 3600
FEATURE_NAMES = ("elevation", "relief_1km", "relief_3km", "slope", "distance_to_permanent_water")
PERMANENT_WATER_OCCURRENCE = 80
TEMPORARY_WATER_RANGE = (3, 60)  # JRC occurrence (%) of land that is water only part of the time
MAX_DISTANCE_METRES = 20_000.0
MARGIN_DEGREES = 0.05  # context around a 1 degree chunk so filters have no edge artefacts


def cell_metres(latitude: float) -> tuple[float, float]:
    """Cell height and width in metres at a latitude."""
    return CELL_DEGREES * 110_574.0, CELL_DEGREES * 111_320.0 * math.cos(math.radians(latitude))


def _merged(folder: str, bounds, nodata: float, fill: float) -> np.ndarray | None:
    west, south, east, north = bounds
    sources = []
    for path in sorted((CACHE / folder).glob("*.tif")):
        dataset = rasterio.open(path)
        left, bottom, right, top = dataset.bounds
        if left < east and right > west and bottom < north and top > south:
            sources.append(dataset)
        else:
            dataset.close()
    if not sources:
        return None
    try:
        array, _ = merge(sources, bounds=bounds, res=CELL_DEGREES, nodata=nodata, resampling=Resampling.nearest)
    finally:
        for dataset in sources:
            dataset.close()
    return np.where(array[0] == nodata, fill, array[0]).astype(np.float32)


def read_chunk(longitude: float, latitude: float) -> tuple[np.ndarray, np.ndarray] | None:
    """Elevation (m, sea = 0) and water occurrence (0-100, NaN where Landsat saw nothing) for one degree square plus margin."""
    bounds = (
        longitude - MARGIN_DEGREES, latitude - MARGIN_DEGREES,
        longitude + 1 + MARGIN_DEGREES, latitude + 1 + MARGIN_DEGREES,
    )
    elevation = _merged("dem", bounds, nodata=-32767.0, fill=0.0)
    if elevation is None:
        return None
    occurrence = _merged("gsw", bounds, nodata=255.0, fill=np.nan)
    if occurrence is None:
        occurrence = np.full(elevation.shape, np.nan, dtype=np.float32)
    rows = min(elevation.shape[0], occurrence.shape[0])
    columns = min(elevation.shape[1], occurrence.shape[1])
    return elevation[:rows, :columns], occurrence[:rows, :columns]


def build_features(elevation: np.ndarray, occurrence: np.ndarray, latitude: float = 10.0) -> np.ndarray:
    """Five terrain channels scaled to about 0-1: elevation, local relief at two radii, slope, water distance."""
    cell_y, cell_x = cell_metres(latitude)
    slope_y, slope_x = np.gradient(elevation, cell_y, cell_x)
    slope = np.degrees(np.arctan(np.hypot(slope_x, slope_y)))
    relief_1km = elevation - minimum_filter(elevation, size=13, mode="nearest")
    relief_3km = elevation - minimum_filter(elevation, size=37, mode="nearest")
    permanent = np.nan_to_num(occurrence, nan=0.0) >= PERMANENT_WATER_OCCURRENCE
    if permanent.any():
        distance = np.minimum(distance_transform_edt(~permanent, sampling=(cell_y, cell_x)), MAX_DISTANCE_METRES)
    else:
        distance = np.full(elevation.shape, MAX_DISTANCE_METRES)
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
