import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from app.db.session import DatabaseNotConfigured, DatabaseUnavailable
from app.services.parcel_import_service import (
    ImportOptions,
    import_dataset,
    inspect_dataset,
    verify_dataset,
)


def _add_source_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="GeoJSON, Shapefile, or GeoPackage path.",
    )
    parser.add_argument(
        "--layer",
        help="Vector layer name, required for multi-layer datasets.",
    )
    parser.add_argument(
        "--source-crs",
        help="Explicit source CRS override, for example EPSG:32651.",
    )


def _add_study_area_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--study-area",
        type=Path,
        help="Optional vector boundary file.",
    )
    parser.add_argument(
        "--study-area-layer",
        help="Layer name for a multi-layer boundary dataset.",
    )
    parser.add_argument(
        "--study-area-crs",
        help="CRS override for a boundary with missing CRS metadata.",
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect, validate, import, or verify authorized farm parcel data."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    inspect_parser = commands.add_parser(
        "inspect",
        help="Report source metadata without database access.",
    )
    _add_source_arguments(inspect_parser)

    validate_parser = commands.add_parser(
        "validate",
        help="Validate parcel records without database access.",
    )
    _add_source_arguments(validate_parser)
    validate_parser.add_argument("--source-dataset", required=True)
    validate_parser.add_argument("--parcel-id-field", required=True)
    validate_parser.add_argument("--barangay-field", required=True)
    validate_parser.add_argument("--crop-field")
    _add_study_area_arguments(validate_parser)

    import_parser = commands.add_parser(
        "import",
        help="Validate and import into farm_parcels.",
    )
    _add_source_arguments(import_parser)
    import_parser.add_argument("--source-dataset", required=True)
    import_parser.add_argument(
        "--source-attribution",
        required=True,
        help="Provider, source URL, and license/terms for the imported data.",
    )
    import_parser.add_argument("--parcel-id-field", required=True)
    import_parser.add_argument("--barangay-field", required=True)
    import_parser.add_argument("--crop-field")
    import_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Check database conflicts without writing.",
    )
    import_parser.add_argument(
        "--update-existing",
        action="store_true",
        help="Explicitly replace stored fields and geometry for matching source IDs.",
    )
    _add_study_area_arguments(import_parser)

    verify_parser = commands.add_parser(
        "verify",
        help="Report database parcel integrity and coverage.",
    )
    verify_parser.add_argument("--source-dataset")
    _add_study_area_arguments(verify_parser)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "inspect":
            result = asdict(inspect_dataset(args.input, args.layer, args.source_crs))
        elif args.command in {"validate", "import"}:
            options = ImportOptions(
                path=args.input,
                source_dataset=args.source_dataset,
                source_attribution=getattr(args, "source_attribution", ""),
                parcel_id_field=args.parcel_id_field,
                barangay_field=args.barangay_field,
                crop_field=args.crop_field,
                source_crs=args.source_crs,
                layer=args.layer,
                study_area_path=args.study_area,
                study_area_layer=args.study_area_layer,
                study_area_crs=args.study_area_crs,
            )
            summary = import_dataset(
                options,
                validate_only=args.command == "validate",
                dry_run=getattr(args, "dry_run", False),
                update_existing=getattr(args, "update_existing", False),
            )
            result = summary.as_dict()
        else:
            result = verify_dataset(
                args.source_dataset,
                args.study_area,
                args.study_area_layer,
                args.study_area_crs,
            )
        print(json.dumps(result, indent=2, default=str))
        return 0
    except (DatabaseNotConfigured, DatabaseUnavailable, ValueError, RuntimeError) as error:
        print(f"Parcel {args.command} failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
