from app.db.session import get_connection

COMPUTE_PARCEL_DAMAGE_QUERY = """
WITH flood_extent AS (
    SELECT ST_UnaryUnion(ST_Collect(geom)) AS geom
    FROM flood_polygons
    WHERE assessment_id = %s
), parcel_measurements AS (
    SELECT
        parcel.id AS parcel_id,
        ST_Area(parcel.geom::geography) / 10000.0 AS parcel_area_hectares,
        CASE
            WHEN ST_Intersects(parcel.geom, flood_extent.geom)
            THEN ST_Area(ST_Intersection(parcel.geom, flood_extent.geom)::geography) / 10000.0
            ELSE 0.0
        END AS flooded_area_hectares
    FROM farm_parcels AS parcel
    CROSS JOIN flood_extent
)
INSERT INTO parcel_damage_assessments (
    assessment_id,
    parcel_id,
    parcel_area_hectares,
    flooded_area_hectares,
    damage_percent,
    severity
)
SELECT
    %s,
    parcel_id,
    parcel_area_hectares,
    LEAST(flooded_area_hectares, parcel_area_hectares),
    LEAST(flooded_area_hectares, parcel_area_hectares) / parcel_area_hectares * 100.0,
    NULL
FROM parcel_measurements
WHERE parcel_area_hectares > 0
ON CONFLICT (assessment_id, parcel_id) DO UPDATE SET
    parcel_area_hectares = EXCLUDED.parcel_area_hectares,
    flooded_area_hectares = EXCLUDED.flooded_area_hectares,
    damage_percent = EXCLUDED.damage_percent,
    severity = EXCLUDED.severity
"""


def compute_parcel_damage(assessment_id: int) -> None:
    """Compute parcel overlap and geodesic hectares in PostGIS for one assessment."""
    with get_connection() as connection:
        connection.execute(COMPUTE_PARCEL_DAMAGE_QUERY, (assessment_id, assessment_id))
