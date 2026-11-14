import argparse
import csv
import math
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np

from ml.data import planetary_computer as pc
from ml.data.features import weak_flood_labels

TILE_KILOMETRES = 5.12
KILOMETRES_PER_DEGREE = 111.32


def tile_centres(bbox: tuple[float, float, float, float], max_tiles: int) -> list[tuple[float, float]]:
    """Lay out non-overlapping tile centres across a bbox, row by row from the south-west."""
    west, south, east, north = bbox
    latitude_step = TILE_KILOMETRES / KILOMETRES_PER_DEGREE
    centres = []
    latitude = south + latitude_step / 2
    while latitude < north:
        longitude_step = latitude_step / math.cos(math.radians(latitude))
        longitude = west + longitude_step / 2
        while longitude < east:
            centres.append((longitude, latitude))
            longitude += longitude_step
        latitude += latitude_step
    return centres[:max_tiles]


def build_tile(
    centre: tuple[float, float],
    flood_radar: list[dict],
    optical: list[dict],
    dry_radar: list[dict],
    flood_date: str | None,
    output_dir: Path,
    index: int,
) -> tuple[str, str, float] | None:
    """Fetch one tile, derive weak labels, and write NumPy image and mask files."""
    grid = pc.make_grid(*centre)
    try:
        scene = pc.read_scene(
            grid,
            pc.select_sentinel_1(flood_radar, flood_date),
            pc.select_sentinel_2(optical),
        )
        reference_vv, reference_vh = pc.read_radar(pc.select_sentinel_1(dry_radar), grid)
    except Exception as error:
        print(f"Tile {index} skipped: {error}")
        return None

    labels = weak_flood_labels(
        scene.vv, scene.vh, scene.ndwi, scene.optical_clear, reference_vv, reference_vh
    ).astype(np.uint8)
    image_name, mask_name = f"tile_{index:04d}_image.npy", f"tile_{index:04d}_mask.npy"
    np.save(output_dir / image_name, scene.features)
    np.save(output_dir / mask_name, labels)
    print(f"Tile {index} written: flooded fraction {labels.mean():.3f}")
    return image_name, mask_name, float(labels.mean())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build 512x512 six-channel tiles and weak flood labels from public Sentinel-1/2 data."
    )
    parser.add_argument("--bbox", type=float, nargs=4, required=True, metavar=("WEST", "SOUTH", "EAST", "NORTH"))
    parser.add_argument("--flood-range", required=True, help="STAC datetime range for the flood scenes, e.g. 2024-07-25/2024-08-05")
    parser.add_argument("--flood-date", help="ISO datetime of the event; the nearest radar scene is used")
    parser.add_argument("--dry-range", required=True, help="STAC datetime range for the dry radar reference")
    parser.add_argument("--optical-range", help="STAC datetime range for optical scenes; defaults to the flood range")
    parser.add_argument("--max-cloud", type=float, default=90.0)
    parser.add_argument("--max-tiles", type=int, default=12)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--output-dir", type=Path, required=True)
    arguments = parser.parse_args()

    bbox = tuple(arguments.bbox)
    centres = tile_centres(bbox, arguments.max_tiles)
    if not centres:
        parser.error("The bbox is smaller than one tile.")
    first_bbox = pc.grid_bbox(pc.make_grid(*centres[0]))
    search_bbox = (
        min(first_bbox[0], bbox[0]), min(first_bbox[1], bbox[1]),
        max(first_bbox[2], bbox[2]), max(first_bbox[3], bbox[3]),
    )
    flood_radar = pc.search_items(pc.SENTINEL_1, search_bbox, arguments.flood_range)
    dry_radar = pc.search_items(pc.SENTINEL_1, search_bbox, arguments.dry_range)
    optical = pc.search_items(
        pc.SENTINEL_2, search_bbox, arguments.optical_range or arguments.flood_range, arguments.max_cloud
    )
    print(f"{len(flood_radar)} flood radar, {len(dry_radar)} dry radar, {len(optical)} optical scenes; {len(centres)} tiles")

    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=arguments.workers) as pool:
        futures = [
            pool.submit(
                build_tile, centre, flood_radar, optical, dry_radar,
                arguments.flood_date, arguments.output_dir, index,
            )
            for index, centre in enumerate(centres)
        ]
        results = [future.result() for future in futures]

    written = [row for row in results if row is not None]
    with (arguments.output_dir / "manifest.csv").open("w", newline="", encoding="utf-8") as manifest:
        writer = csv.writer(manifest)
        writer.writerow(["image_path", "mask_path", "flooded_fraction"])
        writer.writerows(written)
    print(f"Manifest written with {len(written)} tiles.")


if __name__ == "__main__":
    main()
