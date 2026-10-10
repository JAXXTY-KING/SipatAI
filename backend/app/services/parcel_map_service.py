from typing import Any

from app.db.queries.parcels import get_parcel_map as query_parcel_map


def read_parcel_map(
    west: float,
    south: float,
    east: float,
    north: float,
    source_dataset: str | None = None,
) -> dict[str, Any]:
    """Return parcel features for a validated map viewport."""
    if west >= east or south >= north:
        raise ValueError("Map bounds must have west < east and south < north.")
    return query_parcel_map(west, south, east, north, source_dataset)
