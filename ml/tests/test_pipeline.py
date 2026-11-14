import numpy as np

from ml.data.build_tiles import tile_centres
from ml.data.features import build_feature_stack, weak_flood_labels
from ml.data.planetary_computer import grid_bbox, make_grid


def _uniform(value: float) -> np.ndarray:
    return np.full((16, 16), value, dtype=np.float32)


def test_feature_stack_follows_configured_channel_order():
    stack = build_feature_stack(_uniform(0.1), _uniform(0.02), _uniform(0.1), _uniform(0.4), _uniform(0.2))
    assert stack.shape == (6, 16, 16)
    assert stack.dtype == np.float32
    assert np.allclose(stack[2], (0.4 - 0.1) / 0.5, atol=1e-4)  # NDVI
    assert np.allclose(stack[3], (0.2 - 0.4) / 0.6, atol=1e-4)  # NDWI
    assert np.allclose(stack[4], 0.1) and np.allclose(stack[5], 0.4)


def test_weak_labels_remove_permanent_water_and_require_optical_agreement():
    dark_vv, dark_vh = _uniform(0.005), _uniform(0.0005)
    bright = _uniform(0.2)
    ndwi_water, ndwi_land = _uniform(0.4), _uniform(-0.3)
    clear = np.ones((16, 16), dtype=bool)

    flooded = weak_flood_labels(dark_vv, dark_vh, ndwi_water, clear, bright, bright)
    assert flooded.all()
    assert not weak_flood_labels(dark_vv, dark_vh, ndwi_land, clear).any()
    assert not weak_flood_labels(dark_vv, dark_vh, ndwi_water, clear, dark_vv, dark_vh).any()
    assert weak_flood_labels(dark_vv, dark_vh, ndwi_land, ~clear).all()


def test_grid_is_512_pixels_at_ten_metres_around_the_point():
    grid = make_grid(120.85, 15.10)
    west, south, east, north = grid_bbox(grid)
    assert grid.crs == "EPSG:32651"
    assert west < 120.85 < east and south < 15.10 < north
    assert abs((north - south) * 111.32 - 5.12) < 0.1


def test_tile_centres_cover_bbox_without_overlap():
    centres = tile_centres((120.75, 14.95, 120.95, 15.20), max_tiles=100)
    assert 15 <= len(centres) <= 30
    assert len(tile_centres((120.75, 14.95, 120.95, 15.20), max_tiles=3)) == 3
