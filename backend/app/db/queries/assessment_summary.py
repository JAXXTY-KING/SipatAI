from typing import Any

from app.db.session import get_connection

LATEST_ASSESSMENT_SUMMARY_QUERY = """
WITH latest_assessment AS (
    SELECT id, event_name, municipality, model_version, completed_at
    FROM assessment_runs
    WHERE status = 'completed' AND completed_at IS NOT NULL
    ORDER BY completed_at DESC, id DESC
    LIMIT 1
), parcel_groups AS (
    SELECT
        parcel.barangay_name,
        parcel.crop_type,
        SUM(damage.parcel_area_hectares) AS parcel_area_hectares,
        SUM(damage.flooded_area_hectares) AS flooded_area_hectares
    FROM parcel_damage_assessments AS damage
    JOIN farm_parcels AS parcel ON parcel.id = damage.parcel_id
    WHERE damage.assessment_id = (SELECT id FROM latest_assessment)
    GROUP BY parcel.barangay_name, parcel.crop_type
)
SELECT jsonb_build_object(
    'assessment_id', assessment.id,
    'event_name', assessment.event_name,
    'municipality', assessment.municipality,
    'model_version', assessment.model_version,
    'completed_at', assessment.completed_at,
    'status', 'completed',
    'total_affected_hectares', COALESCE((
        SELECT ROUND(SUM(flooded_area_hectares), 1)
        FROM parcel_damage_assessments
        WHERE assessment_id = assessment.id
    ), 0),
    'estimated_damage_php', NULL,
    'affected_barangays', (
        SELECT COUNT(DISTINCT barangay_name)
        FROM parcel_groups
        WHERE flooded_area_hectares > 0
    ),
    'assessments', COALESCE((
        SELECT jsonb_agg(
            jsonb_build_object(
                'barangay', barangay_name,
                'crop', COALESCE(crop_type, 'Not recorded'),
                'affected_hectares', ROUND(flooded_area_hectares, 1),
                'damage_percent', CASE
                    WHEN parcel_area_hectares > 0
                    THEN ROUND(flooded_area_hectares / parcel_area_hectares * 100, 2)
                    ELSE 0
                END,
                'severity', NULL
            )
            ORDER BY barangay_name, crop_type
        )
        FROM parcel_groups
        WHERE flooded_area_hectares > 0
    ), '[]'::jsonb)
)
FROM latest_assessment AS assessment
"""


def get_latest_assessment_summary() -> dict[str, Any] | None:
    """Read metrics for the latest completed database assessment."""
    with get_connection() as connection:
        row = connection.execute(LATEST_ASSESSMENT_SUMMARY_QUERY).fetchone()
    return row[0] if row and row[0] else None
