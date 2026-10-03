from typing import Any

from app.db.queries.damage_map import get_latest_damage_map as get_database_damage_map


def get_damage_map() -> dict[str, Any]:
    """Read flood polygons from the latest completed PostGIS assessment."""
    return get_database_damage_map()
