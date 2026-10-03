from fastapi import APIRouter, HTTPException

from app.db.session import DatabaseNotConfigured, DatabaseUnavailable
from app.services.damage_service import get_damage_map

router = APIRouter(prefix="/damage-map", tags=["assessment"])


@router.get("")
def read_damage_map() -> dict[str, object]:
    """Return flood polygons from the latest completed assessment."""
    try:
        return get_damage_map()
    except DatabaseNotConfigured as error:
        raise HTTPException(status_code=503, detail="Assessment database is not configured.") from error
    except DatabaseUnavailable as error:
        raise HTTPException(status_code=503, detail="Assessment database is unavailable.") from error
