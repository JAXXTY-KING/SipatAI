import json
import math
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from shapely import STRtree
from shapely.geometry import Point, shape
from shapely.ops import unary_union
from shapely.prepared import prep

PROVINCES_PATH = Path(__file__).resolve().parents[3] / "frontend" / "public" / "data" / "ph_admin2.geojson"
TILE_KILOMETRES = 5.12
KILOMETRES_PER_DEGREE = 111.32
COAST_MARGIN_DEGREES = 0.02


class Tile(NamedTuple):
    tile_id: str
    latitude: float
    longitude: float
    province: str


def tile_id_for(latitude: float, longitude: float) -> str:
    return f"{latitude:.3f}_{longitude:.3f}"


@lru_cache(maxsize=1)
def land_tiles() -> tuple[Tile, ...]:
    """Lay a 5.12 km lattice over the Philippines and keep tiles whose centre is on land.

    Land comes from the real province boundaries (geoBoundaries ADM2), widened slightly so
    coastal tiles that are half sea are still scanned.
    """
    collection = json.loads(PROVINCES_PATH.read_text(encoding="utf-8"))
    names = [feature["properties"]["name"] for feature in collection["features"]]
    geometries = [shape(feature["geometry"]).buffer(COAST_MARGIN_DEGREES) for feature in collection["features"]]
    land = prep(unary_union(geometries))
    tree = STRtree(geometries)
    west, south, east, north = unary_union(geometries).bounds

    latitude_step = TILE_KILOMETRES / KILOMETRES_PER_DEGREE
    tiles: list[Tile] = []
    latitude = south + latitude_step / 2
    while latitude < north:
        longitude_step = latitude_step / math.cos(math.radians(latitude))
        longitude = west + longitude_step / 2
        while longitude < east:
            point = Point(longitude, latitude)
            if land.contains(point):
                owner = int(tree.query(point, predicate="intersects")[0])
                tiles.append(Tile(tile_id_for(latitude, longitude), round(latitude, 3), round(longitude, 3), names[owner]))
            longitude += longitude_step
        latitude += latitude_step
    return tuple(tiles)


def tiles_by_province() -> dict[str, list[Tile]]:
    grouped: dict[str, list[Tile]] = {}
    for tile in land_tiles():
        grouped.setdefault(tile.province, []).append(tile)
    return grouped
