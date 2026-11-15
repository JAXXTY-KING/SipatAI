"""Land mask from the real Philippine province boundaries, so flood detections can never appear over the sea.

The boundaries are geoBoundaries ADM2 (frontend/public/data/ph_admin2.geojson). They are buffered by about 200 m
because the published coastline is generalised; anything farther out to sea is dropped.
"""
import numpy as np
from rasterio.features import rasterize
from rasterio.warp import transform_geom
from shapely.geometry import box, mapping

from app.integrations.province_forecast_client import _provinces

COASTAL_BUFFER_DEGREES = 0.002


def land_mask(grid, bbox: tuple[float, float, float, float], shape: tuple[int, int]) -> np.ndarray:
    """True for pixels of a UTM tile grid that lie inside a Philippine province."""
    _, geometries = _provinces()
    area = box(*bbox).buffer(COASTAL_BUFFER_DEGREES * 2)
    shapes = [
        (transform_geom("EPSG:4326", grid.crs, mapping(geometry.buffer(COASTAL_BUFFER_DEGREES))), 1)
        for geometry in geometries
        if geometry.intersects(area)
    ]
    if not shapes:
        return np.zeros(shape, dtype=bool)
    return rasterize(shapes, out_shape=shape, transform=grid.transform, fill=0, dtype="uint8").astype(bool)
