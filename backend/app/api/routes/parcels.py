from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.db.session import DatabaseNotConfigured, DatabaseUnavailable
from app.services.parcel_map_service import read_parcel_map

router = APIRouter(prefix="/parcels", tags=["parcels"])


@router.get("/map")
def read_parcels_on_map(
    west: float = Query(ge=-180, le=180),
    south: float = Query(ge=-90, le=90),
    east: float = Query(ge=-180, le=180),
    north: float = Query(ge=-90, le=90),
    source_dataset: str | None = Query(default=None, min_length=1, max_length=200),
) -> dict[str, Any]:
    """Return real imported parcels visible in a map viewport."""
    try:
        return read_parcel_map(west, south, east, north, source_dataset)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except DatabaseNotConfigured as error:
        raise HTTPException(
            status_code=503, detail="Parcel database is not configured."
        ) from error
    except DatabaseUnavailable as error:
        raise HTTPException(status_code=503, detail="Parcel database is unavailable.") from error
