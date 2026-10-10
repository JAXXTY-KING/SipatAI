import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from app.db.queries.parcels import (
    PARCEL_MAP_MAX_FEATURES,
    PARCEL_MAP_QUERY,
    get_parcel_map,
)
from app.db.session import DatabaseNotConfigured
from app.services.parcel_map_service import read_parcel_map


class _MapResult:
    def fetchone(self):
        return ({
            "type": "FeatureCollection",
            "features": [],
            "matched_count": 0,
            "truncated": False,
            "source_datasets": [],
        },)


class _MapConnection:
    def __init__(self):
        self.query = None
        self.parameters = None

    def __enter__(self):
        return self

    def __exit__(self, error_type, error, traceback):
        return False

    def execute(self, query, parameters):
        self.query = query
        self.parameters = parameters
        return _MapResult()


def _connection_context(connection):
    @contextmanager
    def managed_connection():
        with connection as active_connection:
            yield active_connection

    return managed_connection


class ParcelMapTests(unittest.TestCase):
    def test_map_query_is_bounded_to_viewport_and_feature_limit(self):
        connection = _MapConnection()
        with patch(
            "app.db.queries.parcels.get_connection",
            _connection_context(connection),
        ):
            result = get_parcel_map(120, 13, 122, 15, "authorized-v1")

        self.assertEqual(result["type"], "FeatureCollection")
        self.assertEqual(connection.query, PARCEL_MAP_QUERY)
        self.assertIn("'source_attribution', source_attribution", PARCEL_MAP_QUERY)
        self.assertEqual(
            connection.parameters,
            (
                120,
                13,
                122,
                15,
                "authorized-v1",
                "authorized-v1",
                PARCEL_MAP_MAX_FEATURES + 1,
                PARCEL_MAP_MAX_FEATURES,
                PARCEL_MAP_MAX_FEATURES,
            ),
        )

    def test_invalid_bounds_are_rejected_before_database_access(self):
        with patch("app.services.parcel_map_service.query_parcel_map") as query:
            with self.assertRaisesRegex(ValueError, "Map bounds"):
                read_parcel_map(122, 13, 120, 15)

        query.assert_not_called()

    def test_import_requires_source_attribution(self):
        from app.services.parcel_import_service import (
            ImportOptions,
            import_dataset,
        )

        with patch(
            "app.services.parcel_import_service.inspect_dataset",
        ), patch(
            "app.services.parcel_import_service.import_parcel_records",
        ) as database_import:
            options = ImportOptions(
                path=Path("unused.geojson"),
                source_dataset="source",
                parcel_id_field="id",
                barangay_field="barangay",
            )
            with self.assertRaisesRegex(ValueError, "Source attribution is required"):
                import_dataset(options)

        database_import.assert_not_called()

    def test_route_reports_missing_database_as_service_unavailable(self):
        from app.api.routes.parcels import read_parcels_on_map

        with patch(
            "app.api.routes.parcels.read_parcel_map",
            side_effect=DatabaseNotConfigured("Not configured"),
        ):
            with self.assertRaises(HTTPException) as raised:
                read_parcels_on_map(west=120, south=13, east=122, north=15)

        self.assertEqual(raised.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
