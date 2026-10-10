import tempfile
import unittest
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch

import fiona
from fiona.crs import CRS as FionaCRS
from shapely.geometry import Polygon

from app.db.session import DatabaseUnavailable
from app.db.queries.parcels import (
    EXISTING_PARCEL_QUERY,
    INSERT_PARCEL_QUERY,
    UPDATE_PARCEL_QUERY,
    import_parcels,
)
from app.services.parcel_import_service import (
    ImportOptions,
    import_dataset,
    inspect_dataset,
)


def polygon_coordinates(offset: float = 0.0) -> list[list[list[float]]]:
    return [[
        [121.0 + offset, 14.0],
        [121.001 + offset, 14.0],
        [121.001 + offset, 14.001],
        [121.0 + offset, 14.001],
        [121.0 + offset, 14.0],
    ]]


class ParcelImportTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.dataset_path = (
            Path(self.temporary_directory.name) / "test_parcels.geojson"
        )
        self.options = ImportOptions(
            path=self.dataset_path,
            source_dataset="test-fixture",
            source_attribution="Artificial unit-test geometry only",
            parcel_id_field="lot_code",
            barangay_field="barangay",
            crop_field="crop",
        )

    def tearDown(self) -> None:
        self.temporary_directory.cleanup()

    def write_dataset(self, features: list[dict]) -> None:
        schema = {
            "geometry": "Unknown",
            "properties": {
                "lot_code": "str",
                "barangay": "str",
                "crop": "str",
            },
        }
        with fiona.open(
            self.dataset_path,
            "w",
            driver="GeoJSON",
            schema=schema,
            crs=FionaCRS.from_epsg(4326),
        ) as collection:
            for feature in features:
                collection.write(feature)

    @staticmethod
    def feature(
        parcel_id: str | None,
        geometry: dict | None,
        barangay: str = "Test Barangay",
        crop: str | None = "Test crop",
    ) -> dict:
        return {
            "type": "Feature",
            "geometry": geometry,
            "properties": {
                "lot_code": parcel_id,
                "barangay": barangay,
                "crop": crop,
            },
        }

    @staticmethod
    def polygon_geometry(offset: float = 0.0) -> dict:
        return {
            "type": "Polygon",
            "coordinates": polygon_coordinates(offset),
        }

    def test_inspection_reports_source_metadata(self) -> None:
        self.write_dataset([self.feature("A-1", self.polygon_geometry())])

        inspection = inspect_dataset(self.dataset_path)

        self.assertEqual(inspection.source_crs, "EPSG:4326")
        self.assertEqual(inspection.feature_count, 1)
        self.assertEqual(inspection.geometry_types, {"Polygon": 1})
        self.assertIn("lot_code", inspection.fields)
        self.assertEqual(
            inspection.extent_source_crs,
            (121.0, 14.0, 121.001, 14.001),
        )
        self.assertEqual(inspection.extent_epsg4326, inspection.extent_source_crs)

    def test_geopackage_layer_is_supported(self) -> None:
        geopackage_path = Path(self.temporary_directory.name) / "parcels.gpkg"
        with fiona.open(
            geopackage_path,
            "w",
            driver="GPKG",
            layer="farm_lots",
            schema={
                "geometry": "Polygon",
                "properties": {"lot_code": "str", "barangay": "str", "crop": "str"},
            },
            crs=FionaCRS.from_epsg(4326),
        ) as collection:
            collection.write({
                "geometry": self.polygon_geometry(),
                "properties": {"lot_code": "G-1", "barangay": "Test", "crop": None},
            })

        inspection = inspect_dataset(geopackage_path, layer="farm_lots")

        self.assertEqual(inspection.feature_count, 1)
        self.assertEqual(inspection.layer, "farm_lots")

    def test_valid_polygon_and_multipolygon_are_accepted(self) -> None:
        multipolygon = {
            "type": "MultiPolygon",
            "coordinates": [polygon_coordinates(), polygon_coordinates(0.01)],
        }
        self.write_dataset([
            self.feature("A-1", self.polygon_geometry()),
            self.feature("A-2", multipolygon),
        ])
        imported_records = []

        with patch(
            "app.services.parcel_import_service.import_parcel_records",
            side_effect=lambda records, *args, **kwargs: (
                imported_records.extend(records) or
                {"inserted": 2, "updated": 0, "skipped": 0}
            ),
        ):
            summary = import_dataset(self.options)

        self.assertEqual(summary.accepted, 2)
        self.assertEqual(summary.inserted, 2)
        self.assertTrue(
            all(
                record["source_attribution"]
                == "Artificial unit-test geometry only"
                for record in imported_records
            )
        )
        self.assertTrue(
            all(
                record["geometry_wkt"].startswith("MULTIPOLYGON")
                for record in imported_records
            )
        )

    def test_missing_and_duplicate_identifiers_are_rejected(self) -> None:
        self.write_dataset([
            self.feature(None, self.polygon_geometry()),
            self.feature("DUP", self.polygon_geometry()),
            self.feature("DUP", self.polygon_geometry(0.01)),
        ])

        summary = import_dataset(self.options, validate_only=True)

        self.assertEqual(summary.records_read, 3)
        self.assertEqual(summary.accepted, 0)
        self.assertEqual(summary.rejection_reasons["missing_parcel_id"], 1)
        self.assertEqual(summary.rejection_reasons["duplicate_parcel_id_in_input"], 2)

    def test_invalid_and_empty_geometry_are_rejected(self) -> None:
        invalid_polygon = {
            "type": "Polygon",
            "coordinates": [[
                [121.0, 14.0],
                [121.001, 14.001],
                [121.0, 14.001],
                [121.001, 14.0],
                [121.0, 14.0],
            ]],
        }
        self.write_dataset([
            self.feature("INVALID", invalid_polygon),
            self.feature("EMPTY", {"type": "Polygon", "coordinates": []}),
        ])

        summary = import_dataset(self.options, validate_only=True)

        self.assertEqual(summary.accepted, 0)
        self.assertEqual(summary.rejection_reasons["invalid_geometry"], 1)
        self.assertEqual(summary.rejection_reasons["empty_geometry"], 1)

    def test_field_mapping_is_required_and_crop_is_optional(self) -> None:
        self.write_dataset([self.feature("A-1", self.polygon_geometry(), crop=None)])
        records = []

        with patch(
            "app.services.parcel_import_service.import_parcel_records",
            side_effect=lambda items, *args, **kwargs: (
                records.extend(items) or
                {"inserted": 1, "updated": 0, "skipped": 0}
            ),
        ):
            summary = import_dataset(self.options)

        self.assertEqual(summary.accepted, 1)
        self.assertEqual(summary.unmapped_fields, [])
        self.assertIsNone(records[0]["crop_type"])
        with self.assertRaisesRegex(ValueError, "Mapped field"):
            import_dataset(
                ImportOptions(
                    path=self.dataset_path,
                    source_dataset="test-fixture",
                    source_attribution="Artificial unit-test geometry only",
                    parcel_id_field="missing_id",
                    barangay_field="barangay",
                ),
                validate_only=True,
            )

    def test_missing_source_crs_requires_explicit_override(self) -> None:
        shapefile_path = Path(self.temporary_directory.name) / "missing_crs.shp"
        with fiona.open(
            shapefile_path,
            "w",
            driver="ESRI Shapefile",
            schema={
                "geometry": "Polygon",
                "properties": {"lot_code": "str", "barangay": "str", "crop": "str"},
            },
        ) as collection:
            collection.write({
                "geometry": self.polygon_geometry(),
                "properties": {"lot_code": "A-1", "barangay": "Test", "crop": None},
            })
        with self.assertRaisesRegex(ValueError, "no CRS metadata"):
            inspect_dataset(shapefile_path)
        self.assertEqual(
            inspect_dataset(shapefile_path, source_crs="EPSG:4326").source_crs,
            "EPSG:4326",
        )

    def test_crs_transformation_is_explicit_and_retained(self) -> None:
        projected = Polygon([
            (500000, 1500000),
            (500100, 1500000),
            (500100, 1500100),
            (500000, 1500100),
            (500000, 1500000),
        ])
        with fiona.open(
            self.dataset_path,
            "w",
            driver="GeoJSON",
            schema={
                "geometry": "Polygon",
                "properties": {"lot_code": "str", "barangay": "str", "crop": "str"},
            },
            crs=FionaCRS.from_epsg(32651),
        ) as collection:
            collection.write({
                "geometry": projected.__geo_interface__,
                "properties": {"lot_code": "P-1", "barangay": "Test", "crop": None},
            })
        records = []

        with patch(
            "app.services.parcel_import_service.import_parcel_records",
            side_effect=lambda items, *args, **kwargs: (
                records.extend(items) or
                {"inserted": 1, "updated": 0, "skipped": 0}
            ),
        ):
            summary = import_dataset(self.options)

        self.assertEqual(summary.accepted, 1)
        self.assertEqual(records[0]["source_crs"], "EPSG:32651")
        self.assertIn("MULTIPOLYGON", records[0]["geometry_wkt"])
        self.assertIn("123", records[0]["geometry_wkt"])
        inspection = inspect_dataset(self.dataset_path)
        self.assertGreater(inspection.extent_epsg4326[0], 120)
        self.assertLess(inspection.extent_epsg4326[0], 123)

    def test_study_area_rejects_parcels_outside_boundary(self) -> None:
        boundary_path = Path(self.temporary_directory.name) / "boundary.geojson"
        self.write_dataset([
            self.feature("A-1", self.polygon_geometry()),
            self.feature("OUTSIDE", self.polygon_geometry(-1)),
        ])
        with fiona.open(
            boundary_path,
            "w",
            driver="GeoJSON",
            schema={"geometry": "Polygon", "properties": {"name": "str"}},
            crs=FionaCRS.from_epsg(4326),
        ) as collection:
            collection.write({
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [[
                        [121.0005, 13.9], [121.1, 13.9], [121.1, 14.1],
                        [121.0005, 14.1], [121.0005, 13.9],
                    ]],
                },
                "properties": {"name": "Outside"},
            })

        summary = import_dataset(
            ImportOptions(
                **{
                    **self.options.__dict__,
                    "study_area_path": boundary_path,
                }
            ),
            validate_only=True,
        )

        self.assertEqual(summary.accepted, 0)
        self.assertEqual(summary.records_read, 1)
        self.assertEqual(summary.rejection_reasons["outside_study_area"], 1)

    def test_repeat_import_and_dry_run_are_passed_to_database_layer(self) -> None:
        self.write_dataset([self.feature("A-1", self.polygon_geometry())])
        database_import = Mock(
            side_effect=[
                {"inserted": 1, "updated": 0, "skipped": 0},
                {"inserted": 0, "updated": 0, "skipped": 1},
                {"inserted": 0, "updated": 0, "skipped": 0},
            ]
        )
        with patch(
            "app.services.parcel_import_service.import_parcel_records",
            database_import,
        ):
            first = import_dataset(self.options)
            repeated = import_dataset(self.options)
            dry_run = import_dataset(self.options, dry_run=True)

        self.assertEqual(first.inserted, 1)
        self.assertEqual(repeated.skipped, 1)
        self.assertTrue(database_import.call_args.kwargs["dry_run"])
        self.assertEqual(dry_run.inserted, 0)

    def test_database_import_is_idempotent_and_dry_run_does_not_write(self) -> None:
        records = [{
            "source_parcel_id": "A-1",
            "barangay_name": "Test Barangay",
            "crop_type": None,
            "source_crs": "EPSG:4326",
            "source_attribution": "Artificial unit-test geometry only",
            "geometry_wkt": "MULTIPOLYGON EMPTY",
        }]
        connection = _MemoryConnection()

        with patch(
            "app.db.queries.parcels.get_connection",
            _connection_context(connection),
        ):
            first = import_parcels(records, "test-fixture")
            repeated = import_parcels(records, "test-fixture")
            before_dry_run = deepcopy(connection.parcels)
            dry_run = import_parcels(records, "test-fixture", dry_run=True)

        self.assertEqual(first["inserted"], 1)
        self.assertEqual(repeated["skipped"], 1)
        self.assertEqual(dry_run["skipped"], 1)
        self.assertEqual(connection.parcels, before_dry_run)

    def test_database_update_requires_explicit_option(self) -> None:
        record = {
            "source_parcel_id": "A-1",
            "barangay_name": "Updated Barangay",
            "crop_type": "Updated crop",
            "source_crs": "EPSG:32651",
            "source_attribution": "Artificial unit-test geometry only",
            "geometry_wkt": "MULTIPOLYGON EMPTY",
        }
        connection = _MemoryConnection()
        with patch(
            "app.db.queries.parcels.get_connection",
            _connection_context(connection),
        ):
            import_parcels([record], "test-fixture")
            skipped = import_parcels([record], "test-fixture")
            updated = import_parcels(
                [record],
                "test-fixture",
                update_existing=True,
            )

        self.assertEqual(skipped["skipped"], 1)
        self.assertEqual(updated["updated"], 1)
        self.assertEqual(
            connection.parcels[("test-fixture", "A-1")]["barangay_name"],
            "Updated Barangay",
        )

    def test_database_failure_rolls_back_prior_inserts(self) -> None:
        connection = _MemoryConnection(fail_on_insert_number=2)
        records = [
            {
                "source_parcel_id": parcel_id,
                "barangay_name": "Test Barangay",
                "crop_type": None,
                "source_crs": "EPSG:4326",
                "source_attribution": "Artificial unit-test geometry only",
                "geometry_wkt": "MULTIPOLYGON EMPTY",
            }
            for parcel_id in ("A-1", "A-2")
        ]
        with patch(
            "app.db.queries.parcels.get_connection",
            _connection_context(connection),
        ):
            with self.assertRaises(DatabaseUnavailable):
                import_parcels(records, "test-fixture")

        self.assertEqual(connection.parcels, {})
        self.assertTrue(connection.rolled_back)

    def test_database_failure_is_reported(self) -> None:
        self.write_dataset([self.feature("A-1", self.polygon_geometry())])
        with patch(
            "app.services.parcel_import_service.import_parcel_records",
            side_effect=DatabaseUnavailable("GaussDB request failed."),
        ):
            with self.assertRaises(DatabaseUnavailable):
                import_dataset(self.options)


class _MemoryResult:
    def __init__(self, row: tuple | None) -> None:
        self.row = row

    def fetchone(self) -> tuple | None:
        return self.row


class _MemoryConnection:
    def __init__(self, fail_on_insert_number: int | None = None) -> None:
        self.parcels: dict[tuple[str, str], dict] = {}
        self.fail_on_insert_number = fail_on_insert_number
        self.insert_count = 0
        self.rolled_back = False
        self._snapshot: dict[tuple[str, str], dict] | None = None

    def __enter__(self) -> "_MemoryConnection":
        self._snapshot = deepcopy(self.parcels)
        return self

    def __exit__(self, error_type, error, traceback) -> bool:
        if error_type is not None:
            self.parcels = self._snapshot or {}
            self.rolled_back = True
        return False

    def execute(self, query: str, parameters: tuple) -> _MemoryResult:
        if query == EXISTING_PARCEL_QUERY:
            return _MemoryResult((1,) if parameters in self.parcels else None)
        if query == INSERT_PARCEL_QUERY:
            self.insert_count += 1
            if self.insert_count == self.fail_on_insert_number:
                raise DatabaseUnavailable("Simulated database failure.")
            key = (parameters[0], parameters[1])
            if key in self.parcels:
                return _MemoryResult(None)
            self.parcels[key] = {
                "barangay_name": parameters[2],
                "source_attribution": parameters[5],
            }
            return _MemoryResult((1,))
        if query == UPDATE_PARCEL_QUERY:
            key = (parameters[5], parameters[6])
            if key not in self.parcels:
                return _MemoryResult(None)
            self.parcels[key] = {
                "barangay_name": parameters[0],
                "source_attribution": parameters[3],
            }
            return _MemoryResult((1,))
        raise AssertionError("Unexpected database query.")


def _connection_context(connection: _MemoryConnection):
    @contextmanager
    def managed_connection():
        try:
            with connection as active_connection:
                yield active_connection
        except DatabaseUnavailable:
            raise

    return managed_connection


if __name__ == "__main__":
    unittest.main()
