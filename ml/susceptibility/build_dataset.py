"""Sample real terrain and water-history training pixels from tiles spread over every province.

Run from the repository root:
    ml\\.venv\\Scripts\\python.exe -m ml.susceptibility.build_dataset --tiles-per-province 2
"""
import argparse
import json
import random
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from shapely.geometry import Point, shape

from ml.susceptibility import features as terrain

PROVINCES_PATH = Path("frontend/public/data/ph_admin2.geojson")
PIXELS_PER_CLASS = 6000


def sample_points(per_province: int, seed: int) -> list[tuple[str, float, float]]:
    """Random land points inside each real province boundary (deterministic)."""
    generator = random.Random(seed)
    points = []
    for feature in json.loads(PROVINCES_PATH.read_text(encoding="utf-8"))["features"]:
        geometry = shape(feature["geometry"])
        west, south, east, north = geometry.bounds
        count = per_province if geometry.area > 0.01 else 1
        found = 0
        for _ in range(2000):
            point = Point(generator.uniform(west, east), generator.uniform(south, north))
            if geometry.contains(point):
                points.append((feature["properties"]["name"], point.y, point.x))
                found += 1
                if found == count:
                    break
    return points


def build_tile(index: int, province: str, latitude: float, longitude: float, output: Path) -> str:
    target = output / f"{index:04d}.npz"
    if target.is_file():
        return "cached"
    try:
        grid = terrain.make_terrain_grid(longitude, latitude)
        elevation = terrain.read_elevation(grid)
        occurrence = terrain.read_water_occurrence(grid)
    except Exception as error:
        return f"skipped: {type(error).__name__}"
    features = terrain.build_features(elevation, occurrence)
    labels = terrain.history_labels(occurrence, elevation)
    generator = np.random.default_rng(index)
    chosen = []
    for value in (0, 1):
        rows, columns = np.nonzero(labels == value)
        if len(rows) == 0:
            continue
        picks = generator.choice(len(rows), size=min(PIXELS_PER_CLASS, len(rows)), replace=False)
        chosen.append((rows[picks], columns[picks]))
    if not chosen:
        return "skipped: no labelled pixels"
    rows = np.concatenate([item[0] for item in chosen])
    columns = np.concatenate([item[1] for item in chosen])
    np.savez_compressed(
        target,
        x=features[:, rows, columns].T,
        y=labels[rows, columns],
        province=province,
        latitude=latitude,
        longitude=longitude,
        positive_share=float((labels == 1).sum() / max((labels >= 0).sum(), 1)),
    )
    return "ok"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tiles-per-province", type=int, default=2)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--output-dir", type=Path, default=Path("ml/artifacts/susceptibility/tiles"))
    arguments = parser.parse_args()
    arguments.output_dir.mkdir(parents=True, exist_ok=True)

    points = sample_points(arguments.tiles_per_province, arguments.seed)
    print(f"{len(points)} tiles over {len({p[0] for p in points})} provinces", flush=True)
    outcomes: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=arguments.workers) as pool:
        futures = [pool.submit(build_tile, index, *point, arguments.output_dir) for index, point in enumerate(points)]
        for done, future in enumerate(futures, start=1):
            outcome = future.result()
            outcomes[outcome] = outcomes.get(outcome, 0) + 1
            if done % 10 == 0:
                print(f"[{done}/{len(points)}] {outcomes}", flush=True)
    print(f"Done: {outcomes}", flush=True)


if __name__ == "__main__":
    main()
