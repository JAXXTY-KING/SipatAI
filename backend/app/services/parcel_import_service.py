from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import fiona
from pyproj import CRS, Transformer
from shapely.errors import GEOSException
from pyproj.exceptions import CRSError, ProjError
from shapely.geometry import MultiPolygon, shape
from shapely.ops import transform, unary_union

from app.db.queries.parcels import import_parcels as import_parcel_records
from app.db.queries.parcels import verify_parcels as query_verify_parcels

TARGET_CRS = CRS.from_epsg(4326)


@dataclass
class DatasetInspection:
    """Metadata gathered from a vector dataset without modifying it."""

    path: str
    layer: str | None
    source_crs: str
    feature_count: int
    geometry_types: dict[str, int]
    fields: dict[str, str]
    extent_source_crs: tuple[float, float, float, float] | None
    extent_epsg4326: tuple[float, float, float, float] | None


@dataclass
class ImportSummary:
    """Counts and rejection reasons for one parcel import attempt."""

    records_read: int = 0
    accepted: int = 0
    inserted: int = 0
    updated: int = 0
    skipped: int = 0
    rejected: int = 0
    unmapped_fields: list[str] = field(default_factory=list)
    rejection_reasons: Counter[str] = field(default_factory=Counter)

    def reject(self, reason: str) -> None:
        self.rejected += 1
        self.rejection_reasons[reason] += 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "records_read": self.records_read,
            "accepted": self.accepted,
            "inserted": self.inserted,
            "updated": self.updated,
            "skipped": self.skipped,
            "rejected": self.rejected,
            "unmapped_fields": self.unmapped_fields,
            "rejection_reasons": dict(sorted(self.rejection_reasons.items())),
        }


@dataclass(frozen=True)
class ImportOptions:
    """Explicit source and field settings for a parcel dataset."""

    path: Path
    source_dataset: str
    parcel_id_field: str
    barangay_field: str
    source_attribution: str = ""
    crop_field: str | None = None
    source_crs: str | None = None
    layer: str | None = None
    study_area_path: Path | None = None
    study_area_layer: str | None = None
    study_area_crs: str | None = None


@contextmanager
def _open_vector(path: Path, layer: str | None = None) -> Iterator[Any]:
    if not path.exists():
        raise ValueError(f"Dataset path does not exist: {path}")
    try:
        with fiona.open(path, layer=layer) as collection:
            yield collection
    except (fiona.errors.FionaError, OSError) as error:
        raise ValueError(f"Could not read vector dataset {path}: {error}") from error


def _get_crs(collection: Any, override: str | None, label: str) -> CRS:
    configured_crs = override or collection.crs_wkt or collection.crs
    if not configured_crs:
        raise ValueError(
            f"{label} has no CRS metadata. Provide an explicit CRS override; "
            "coordinates will not be assumed."
        )
    try:
        return CRS.from_user_input(configured_crs)
    except CRSError as error:
        raise ValueError(f"Invalid {label} CRS: {configured_crs}") from error


def _make_transformer(source_crs: CRS, label: str) -> Transformer:
    try:
        return Transformer.from_crs(source_crs, TARGET_CRS, always_xy=True)
    except ProjError as error:
        raise ValueError(f"Could not transform {label} to EPSG:4326.") from error


def _merge_extent(
    extent: tuple[float, float, float, float] | None,
    bounds: tuple[float, float, float, float],
) -> tuple[float, float, float, float]:
    if extent is None:
        return bounds
    return (
        min(extent[0], bounds[0]),
        min(extent[1], bounds[1]),
        max(extent[2], bounds[2]),
        max(extent[3], bounds[3]),
    )


def inspect_dataset(
    path: Path,
    layer: str | None = None,
    source_crs: str | None = None,
) -> DatasetInspection:
    """Inspect CRS, fields, geometry types, feature count, and extent."""
    with _open_vector(path, layer) as collection:
        crs = _get_crs(collection, source_crs, "Source dataset")
        transformer = _make_transformer(crs, "source geometry")
        geometry_types: Counter[str] = Counter()
        feature_count = 0
        extent_source_crs: tuple[float, float, float, float] | None = None
        extent_epsg4326: tuple[float, float, float, float] | None = None

        for feature in collection:
            feature_count += 1
            geometry = feature.get("geometry")
            geometry_type = (
                geometry.get("type", "No geometry")
                if geometry
                else "No geometry"
            )
            geometry_types[geometry_type] += 1
            if geometry:
                try:
                    source_geometry = shape(geometry)
                    target_geometry = transform(
                        transformer.transform,
                        source_geometry,
                    )
                except (GEOSException, ProjError, TypeError, ValueError) as error:
                    raise ValueError(
                        f"Feature {feature_count} has geometry that cannot be inspected."
                    ) from error
                if not source_geometry.is_empty:
                    extent_source_crs = _merge_extent(
                        extent_source_crs,
                        source_geometry.bounds,
                    )
                if not target_geometry.is_empty:
                    extent_epsg4326 = _merge_extent(
                        extent_epsg4326,
                        target_geometry.bounds,
                    )

        fields = {
            name: str(field_type)
            for name, field_type in collection.schema["properties"].items()
        }

    return DatasetInspection(
        path=str(path),
        layer=layer,
        source_crs=crs.to_string(),
        feature_count=feature_count,
        geometry_types=dict(sorted(geometry_types.items())),
        fields=fields,
        extent_source_crs=extent_source_crs,
        extent_epsg4326=extent_epsg4326,
    )


def _normalize_parcel_id(value: Any) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    normalized = str(value).strip()
    return normalized or None


def _filter_features(
    collection: Any,
    study_area: Any | None,
    source_crs: CRS,
) -> Iterator[Any]:
    if study_area is None:
        yield from collection
        return

    try:
        source_transformer = Transformer.from_crs(
            TARGET_CRS,
            source_crs,
            always_xy=True,
        )
        source_study_area = transform(
            source_transformer.transform,
            study_area,
        )
    except (GEOSException, ProjError, ValueError) as error:
        raise ValueError(
            "Could not transform study-area boundary to source CRS."
        ) from error
    if source_study_area.is_empty or not source_study_area.is_valid:
        raise ValueError("Study-area boundary is invalid in source CRS.")
    yield from collection.filter(mask=source_study_area.__geo_interface__)


def _read_feature_ids(
    options: ImportOptions,
    study_area: Any | None,
    source_crs: CRS,
) -> Counter[str]:
    ids: Counter[str] = Counter()
    with _open_vector(options.path, options.layer) as collection:
        for feature in _filter_features(collection, study_area, source_crs):
            properties = feature.get("properties") or {}
            identifier = _normalize_parcel_id(
                properties.get(options.parcel_id_field)
            )
            if identifier is not None:
                ids[identifier] += 1

    return ids


def _source_metadata(options: ImportOptions) -> tuple[CRS, dict[str, str]]:
    with _open_vector(options.path, options.layer) as collection:
        crs = _get_crs(collection, options.source_crs, "Source dataset")
        fields = {
            name: str(field_type)
            for name, field_type in collection.schema["properties"].items()
        }
    required_fields = [options.parcel_id_field, options.barangay_field]
    if options.crop_field:
        required_fields.append(options.crop_field)
    missing_fields = [name for name in required_fields if name not in fields]
    if missing_fields:
        raise ValueError(
            "Mapped field(s) do not exist in the dataset: "
            + ", ".join(missing_fields)
        )
    return crs, fields


def _load_study_area(
    path: Path | None,
    layer: str | None,
    crs_override: str | None,
) -> Any | None:
    if path is None:
        return None
    geometries = []
    with _open_vector(path, layer) as collection:
        crs = _get_crs(collection, crs_override, "Study-area dataset")
        transformer = _make_transformer(crs, "study-area geometry")
        for feature in collection:
            if feature.get("geometry"):
                try:
                    geometry = shape(feature["geometry"])
                    if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
                        raise ValueError("Study-area features must be polygonal.")
                    if geometry.has_z:
                        raise ValueError(
                            "Study-area features must be two-dimensional."
                        )
                    geometry = transform(transformer.transform, geometry)
                except (GEOSException, ProjError, ValueError) as error:
                    raise ValueError(
                        "Could not transform study-area geometry."
                    ) from error
                if geometry.is_empty or not geometry.is_valid:
                    raise ValueError(
                        "Study-area data contains invalid or empty geometry."
                    )
                geometries.append(geometry)

    if not geometries:
        raise ValueError("Study-area dataset contains no usable geometries.")
    return unary_union(geometries)


def _validated_records(
    options: ImportOptions,
    duplicate_ids: set[str],
    source_crs: CRS,
    study_area: Any | None,
    summary: ImportSummary,
) -> Iterator[dict[str, Any]]:
    transformer = _make_transformer(source_crs, "parcel geometry")
    with _open_vector(options.path, options.layer) as collection:
        for feature in _filter_features(collection, study_area, source_crs):
            summary.records_read += 1
            properties = feature.get("properties") or {}
            identifier_value = properties.get(options.parcel_id_field)
            if identifier_value is None:
                summary.reject("missing_parcel_id")
                continue

            parcel_id = _normalize_parcel_id(identifier_value)
            if parcel_id is None:
                summary.reject("invalid_parcel_id")
                continue

            if parcel_id in duplicate_ids:
                summary.reject("duplicate_parcel_id_in_input")
                continue

            barangay_value = properties.get(options.barangay_field)
            if barangay_value is None or not str(barangay_value).strip():
                summary.reject("missing_barangay")
                continue

            raw_geometry = feature.get("geometry")
            if not raw_geometry:
                summary.reject("missing_geometry")
                continue

            try:
                geometry = shape(raw_geometry)
            except (GEOSException, TypeError, ValueError):
                summary.reject("unsupported_geometry")
                continue
            if geometry.is_empty:
                summary.reject("empty_geometry")
                continue
            if geometry.geom_type not in {"Polygon", "MultiPolygon"}:
                summary.reject("unsupported_geometry")
                continue
            if geometry.has_z:
                summary.reject("three_dimensional_geometry")
                continue
            if not geometry.is_valid:
                summary.reject("invalid_geometry")
                continue

            try:
                geometry = transform(transformer.transform, geometry)
            except (GEOSException, ProjError, ValueError):
                summary.reject("crs_transformation_failed")
                continue
            if geometry.is_empty or not geometry.is_valid:
                summary.reject("invalid_geometry_after_reprojection")
                continue
            if geometry.geom_type == "Polygon":
                geometry = MultiPolygon([geometry])

            if study_area is not None and not study_area.covers(geometry):
                summary.reject("outside_study_area")
                continue

            crop_value = (
                properties.get(options.crop_field)
                if options.crop_field
                else None
            )
            summary.accepted += 1
            yield {
                "source_parcel_id": parcel_id,
                "barangay_name": str(barangay_value).strip(),
                "crop_type": (
                    str(crop_value).strip()
                    if crop_value is not None and str(crop_value).strip()
                    else None
                ),
                "source_crs": source_crs.to_string(),
                "source_attribution": options.source_attribution.strip(),
                "geometry_wkt": geometry.wkt,
            }


def import_dataset(
    options: ImportOptions,
    *,
    validate_only: bool = False,
    dry_run: bool = False,
    update_existing: bool = False,
) -> ImportSummary:
    """Validate and, unless requested otherwise, import a vector parcel source."""
    if not options.source_dataset.strip():
        raise ValueError("A non-empty source dataset name is required.")
    if not validate_only and not options.source_attribution.strip():
        raise ValueError(
            "Source attribution is required for database import. "
            "Include the provider, source URL, and license or terms."
        )
    if validate_only and dry_run:
        raise ValueError("Choose either validation-only or database dry-run mode.")

    source_crs, fields = _source_metadata(options)
    study_area = _load_study_area(
        options.study_area_path,
        options.study_area_layer,
        options.study_area_crs,
    )
    duplicate_counts = _read_feature_ids(options, study_area, source_crs)
    duplicate_ids = {
        identifier
        for identifier, count in duplicate_counts.items()
        if count > 1
    }
    summary = ImportSummary()
    mapped_fields = {
        options.parcel_id_field,
        options.barangay_field,
    }
    if options.crop_field:
        mapped_fields.add(options.crop_field)
    summary.unmapped_fields = sorted(set(fields) - mapped_fields)
    records = _validated_records(
        options,
        duplicate_ids,
        source_crs,
        study_area,
        summary,
    )

    if validate_only:
        for _ in records:
            pass
        return summary

    database_counts = import_parcel_records(
        records,
        options.source_dataset.strip(),
        update_existing=update_existing,
        dry_run=dry_run,
    )
    summary.inserted = database_counts["inserted"]
    summary.updated = database_counts["updated"]
    summary.skipped = database_counts["skipped"]
    return summary


def verify_dataset(
    source_dataset: str | None = None,
    study_area_path: Path | None = None,
    study_area_layer: str | None = None,
    study_area_crs: str | None = None,
) -> dict[str, Any]:
    """Verify loaded parcels, optionally against a local study-area boundary."""
    study_area_wkt = None
    if study_area_path is not None:
        study_area = _load_study_area(
            study_area_path,
            study_area_layer,
            study_area_crs,
        )
        study_area_wkt = study_area.wkt
    return query_verify_parcels(source_dataset, study_area_wkt)
