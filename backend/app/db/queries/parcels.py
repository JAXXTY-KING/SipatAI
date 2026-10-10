from collections.abc import Iterable
from typing import Any

from app.db.session import get_connection

INSERT_PARCEL_QUERY = """
INSERT INTO farm_parcels (
    source_dataset,
    source_parcel_id,
    barangay_name,
    crop_type,
    source_crs,
    source_attribution,
    geom
)
VALUES (%s, %s, %s, %s, %s, %s, ST_Multi(ST_GeomFromText(%s, 4326)))
ON CONFLICT (source_dataset, source_parcel_id) DO NOTHING
RETURNING id
"""

UPDATE_PARCEL_QUERY = """
UPDATE farm_parcels
SET barangay_name = %s,
    crop_type = %s,
    source_crs = %s,
    source_attribution = %s,
    geom = ST_Multi(ST_GeomFromText(%s, 4326))
WHERE source_dataset = %s AND source_parcel_id = %s
RETURNING id
"""

EXISTING_PARCEL_QUERY = """
SELECT 1
FROM farm_parcels
WHERE source_dataset = %s AND source_parcel_id = %s
"""

VERIFY_PARCELS_QUERY = """
WITH selected_parcels AS (
    SELECT source_dataset, source_parcel_id, source_attribution, geom
    FROM farm_parcels
    WHERE (CAST(%s AS TEXT) IS NULL OR source_dataset = %s)
), source_counts AS (
    SELECT source_dataset, COUNT(*) AS parcel_count
    FROM selected_parcels
    GROUP BY source_dataset
), source_count_json AS (
    SELECT COALESCE(
        jsonb_object_agg(source_dataset, parcel_count),
        '{}'::jsonb
    ) AS counts
    FROM source_counts
), duplicate_ids AS (
    SELECT COUNT(*) AS duplicate_count
    FROM (
        SELECT source_dataset, source_parcel_id
        FROM selected_parcels
        GROUP BY source_dataset, source_parcel_id
        HAVING COUNT(*) > 1
    ) AS duplicates
)
SELECT
    COUNT(*) AS total_count,
    COALESCE(
        jsonb_agg(DISTINCT ST_SRID(geom)),
        '[]'::jsonb
    ) AS srids,
    ST_Extent(geom)::TEXT AS extent,
    COALESCE(
        SUM(CASE WHEN geom IS NULL OR ST_IsEmpty(geom) THEN 1 ELSE 0 END),
        0
    ) AS empty_count,
    COALESCE(
        SUM(CASE WHEN geom IS NOT NULL AND NOT ST_IsValid(geom) THEN 1 ELSE 0 END),
        0
    ) AS invalid_count,
    duplicate_ids.duplicate_count,
    source_count_json.counts,
    COALESCE(
        SUM(CASE
            WHEN source_attribution IS NULL OR BTRIM(source_attribution) = ''
            THEN 1
            ELSE 0
        END),
        0
    ) AS missing_attribution_count,
    CASE
        WHEN CAST(%s AS TEXT) IS NULL THEN NULL
        ELSE COALESCE(SUM(
            CASE
                WHEN NOT ST_Covers(ST_GeomFromText(%s, 4326), geom) THEN 1
                ELSE 0
            END
        ), 0)
    END AS outside_study_area_count
FROM selected_parcels
CROSS JOIN duplicate_ids
CROSS JOIN source_count_json
GROUP BY duplicate_ids.duplicate_count, source_count_json.counts
"""

PARCEL_MAP_MAX_FEATURES = 2500

PARCEL_MAP_QUERY = """
WITH visible_parcels AS (
    SELECT
        source_dataset,
        source_parcel_id,
        barangay_name,
        crop_type,
        source_attribution,
        geom
    FROM farm_parcels
    WHERE ST_Intersects(
        geom,
        ST_MakeEnvelope(%s, %s, %s, %s, 4326)
    )
      AND (%s IS NULL OR source_dataset = %s)
    ORDER BY source_dataset, source_parcel_id
    LIMIT %s
)
SELECT jsonb_build_object(
    'type', 'FeatureCollection',
    'features', CASE
        WHEN COUNT(*) > %s THEN '[]'::jsonb
        ELSE COALESCE(
            jsonb_agg(
                jsonb_build_object(
                    'type', 'Feature',
                    'geometry', ST_AsGeoJSON(geom)::jsonb,
                    'properties', jsonb_build_object(
                        'source_dataset', source_dataset,
                        'source_attribution', source_attribution,
                        'parcel_id', source_parcel_id,
                        'barangay', barangay_name,
                        'crop', crop_type
                    )
                )
                ORDER BY source_dataset, source_parcel_id
            ),
            '[]'::jsonb
        )
    END,
    'matched_count', COUNT(*),
    'truncated', COUNT(*) > %s,
    'source_datasets', COALESCE(
        (SELECT jsonb_agg(source_dataset ORDER BY source_dataset)
         FROM (SELECT DISTINCT source_dataset FROM visible_parcels) AS sources),
        '[]'::jsonb
    )
)
FROM visible_parcels
"""


def import_parcels(
    records: Iterable[dict[str, Any]],
    source_dataset: str,
    update_existing: bool = False,
    dry_run: bool = False,
) -> dict[str, int]:
    """Import validated parcels atomically, skipping existing IDs by default."""
    counts = {"inserted": 0, "updated": 0, "skipped": 0}

    with get_connection() as connection:
        for record in records:
            parameters = (
                source_dataset,
                record["source_parcel_id"],
            )
            exists = connection.execute(EXISTING_PARCEL_QUERY, parameters).fetchone()

            if dry_run:
                if exists:
                    counts["updated" if update_existing else "skipped"] += 1
                else:
                    counts["inserted"] += 1
                continue

            if exists:
                if not update_existing:
                    counts["skipped"] += 1
                    continue

                updated = connection.execute(
                    UPDATE_PARCEL_QUERY,
                    (
                        record["barangay_name"],
                        record["crop_type"],
                        record["source_crs"],
                        record["source_attribution"],
                        record["geometry_wkt"],
                        source_dataset,
                        record["source_parcel_id"],
                    ),
                ).fetchone()
                if updated is None:
                    counts["skipped"] += 1
                else:
                    counts["updated"] += 1
                continue

            inserted = connection.execute(
                INSERT_PARCEL_QUERY,
                (
                    source_dataset,
                    record["source_parcel_id"],
                    record["barangay_name"],
                    record["crop_type"],
                    record["source_crs"],
                    record["source_attribution"],
                    record["geometry_wkt"],
                ),
            ).fetchone()
            if inserted is not None:
                counts["inserted"] += 1
            elif update_existing:
                updated = connection.execute(
                    UPDATE_PARCEL_QUERY,
                    (
                        record["barangay_name"],
                        record["crop_type"],
                        record["source_crs"],
                        record["source_attribution"],
                        record["geometry_wkt"],
                        source_dataset,
                        record["source_parcel_id"],
                    ),
                ).fetchone()
                counts["updated" if updated else "skipped"] += 1
            else:
                counts["skipped"] += 1

    return counts


def verify_parcels(
    source_dataset: str | None = None,
    study_area_wkt: str | None = None,
) -> dict[str, Any]:
    """Return read-only parcel integrity and coverage statistics."""
    with get_connection() as connection:
        row = connection.execute(
            VERIFY_PARCELS_QUERY,
            (
                source_dataset,
                source_dataset,
                study_area_wkt,
                study_area_wkt,
            ),
        ).fetchone()

    if row is None:
        raise RuntimeError("Parcel verification did not return a result.")

    columns = (
        "total_count",
        "srids",
        "extent",
        "empty_count",
        "invalid_count",
        "duplicate_id_count",
        "counts_by_source",
        "missing_attribution_count",
        "outside_study_area_count",
    )
    return dict(zip(columns, row, strict=True))


def get_parcel_map(
    west: float,
    south: float,
    east: float,
    north: float,
    source_dataset: str | None = None,
) -> dict[str, Any]:
    """Return parcels intersecting a map viewport, capped to bound response size."""
    with get_connection() as connection:
        row = connection.execute(
            PARCEL_MAP_QUERY,
            (
                west,
                south,
                east,
                north,
                source_dataset,
                source_dataset,
                PARCEL_MAP_MAX_FEATURES + 1,
                PARCEL_MAP_MAX_FEATURES,
                PARCEL_MAP_MAX_FEATURES,
            ),
        ).fetchone()

    if row is None or not row[0]:
        raise RuntimeError("Parcel map query did not return a result.")
    return row[0]
