from typing import Any

from app.db.session import get_connection

LATEST_DAMAGE_MAP_QUERY = """
SELECT jsonb_build_object(
    'type', 'FeatureCollection',
    'features', COALESCE(
        jsonb_agg(
            jsonb_build_object(
                'type', 'Feature',
                'geometry', ST_AsGeoJSON(parcel.geom)::jsonb,
                'properties', jsonb_build_object(
                    'parcel_id', parcel.source_parcel_id,
                    'barangay', parcel.barangay_name,
                    'crop', parcel.crop_type,
                    'affected_hectares', damage.flooded_area_hectares,
                    'damage_percent', damage.damage_percent,
                    'severity', damage.severity
                )
            )
            ORDER BY parcel.source_parcel_id
        ),
        '[]'::jsonb
    )
)
FROM parcel_damage_assessments AS damage
JOIN farm_parcels AS parcel ON parcel.id = damage.parcel_id
JOIN assessment_runs AS assessment ON assessment.id = damage.assessment_id
WHERE assessment.id = (
    SELECT id
    FROM assessment_runs
    WHERE status = 'completed' AND completed_at IS NOT NULL
    ORDER BY completed_at DESC, id DESC
    LIMIT 1
)
"""


def get_latest_damage_map() -> dict[str, Any]:
    """Read the latest completed assessment as GeoJSON from PostGIS."""
    with get_connection() as connection:
        row = connection.execute(LATEST_DAMAGE_MAP_QUERY).fetchone()

    return row[0] if row and row[0] else {"type": "FeatureCollection", "features": []}
