import sys

from app.core.config import REPOSITORY_ROOT

sys.path.insert(0, str(REPOSITORY_ROOT))

from ml.data import planetary_computer as pc  # noqa: E402

from app.services.land_mask import land_mask  # noqa: E402


def _share(longitude: float, latitude: float) -> float:
    grid = pc.make_grid(longitude, latitude)
    return float(land_mask(grid, pc.grid_bbox(grid), pc.INPUT_SIZE).mean())


def test_land_mask_is_empty_over_open_sea_and_filled_over_land():
    assert _share(121.5, 12.0) == 0.0  # Sibuyan Sea / Tablas Strait water, no island inside the tile
    assert _share(120.95, 14.0) > 0.9  # inland Cavite/Laguna
