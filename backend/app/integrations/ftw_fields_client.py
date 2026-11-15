import threading
from collections import OrderedDict
from dataclasses import dataclass

import duckdb

FTW_PHILIPPINES_URL = (
    "https://data.source.coop/ftw/global-data/predictions/vectors/alpha/"
    "results-by-admin-conf/admin:country_code=PH/Philippines.parquet"
)
AVAILABLE_YEARS = (2024, 2025)
MIN_CONFIDENCE = 50.0
CACHE_SIZE = 8

_cache: OrderedDict[tuple, list["FieldPolygon"]] = OrderedDict()
_cache_lock = threading.Lock()


class FieldBoundaryError(RuntimeError):
    """Raised when the Fields of The World boundary dataset cannot be read."""


@dataclass(frozen=True)
class FieldPolygon:
    field_id: str
    wkb: bytes
    confidence: float
    area_m2: float


def field_year_for(event_year: int | None) -> int:
    """Pick the FTW prediction year closest to the event; the latest year when no event date is given."""
    if event_year is None:
        return AVAILABLE_YEARS[-1]
    return min(AVAILABLE_YEARS, key=lambda year: abs(year - event_year))


def fetch_fields(bbox: tuple[float, float, float, float], year: int) -> list[FieldPolygon]:
    """Read agricultural field polygons intersecting a WGS 84 bbox from the public FTW GeoParquet.

    Only the byte ranges needed for the bbox are downloaded. Polygons are remote-sensing
    field units predicted from Sentinel-2, not legal parcels.
    """
    west, south, east, north = bbox
    key = tuple(round(value, 5) for value in bbox) + (year,)
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]

    try:
        connection = duckdb.connect()
        try:
            connection.execute("INSTALL spatial; LOAD spatial; INSTALL httpfs; LOAD httpfs;")
            rows = connection.execute(
                f"""
                SELECT id, ST_AsWKB(geometry), confidence, "metrics:area"
                FROM read_parquet('{FTW_PHILIPPINES_URL}')
                WHERE bbox.xmin <= ? AND bbox.xmax >= ? AND bbox.ymin <= ? AND bbox.ymax >= ?
                  AND EXTRACT(year FROM "determination:datetime") = ?
                  AND confidence >= ?
                """,
                [east, west, north, south, year, MIN_CONFIDENCE],
            ).fetchall()
        finally:
            connection.close()
    except Exception as error:
        raise FieldBoundaryError("Field boundaries could not be read from Fields of The World.") from error

    fields = [
        FieldPolygon(str(row[0]), bytes(row[1]), float(row[2]), float(row[3]))
        for row in rows
        if row[1] is not None
    ]
    with _cache_lock:
        _cache[key] = fields
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return fields
