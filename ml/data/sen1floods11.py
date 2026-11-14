import argparse
import csv
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
import numpy as np
import rasterio

from ml.data.features import build_feature_stack

BASE_URL = "https://storage.googleapis.com/sen1floods11/v1.1"
SPLIT_URL = BASE_URL + "/splits/flood_handlabeled/flood_{split}_data.csv"
CHIP_URL = BASE_URL + "/data/flood_events/HandLabeled/{kind}/{name}"
SPLITS = ("train", "valid", "test", "bolivia")
# Sentinel-2 band positions in the 13-band Sen1Floods11 chips: B3, B4, B8
GREEN_BAND, RED_BAND, NIR_BAND = 3, 4, 8
REFLECTANCE_SCALE = 10000.0


def read_chip_names(split: str) -> list[str]:
    """Return chip identifiers (e.g. Ghana_103272) for an official split."""
    response = httpx.get(SPLIT_URL.format(split=split), timeout=60.0)
    response.raise_for_status()
    return [row[0].removesuffix("_S1Hand.tif") for row in csv.reader(response.text.splitlines()) if row]


def _read(kind: str, chip: str, indexes: list[int] | None = None) -> np.ndarray:
    """Download one GeoTIFF whole (far faster than many range reads) and read it in memory."""
    url = CHIP_URL.format(kind=kind, name=f"{chip}_{kind}.tif")
    for attempt in range(3):
        try:
            response = httpx.get(url, timeout=120.0)
            response.raise_for_status()
            break
        except httpx.HTTPError:
            if attempt == 2:
                raise
    with rasterio.MemoryFile(response.content) as memory, memory.open() as source:
        return source.read(indexes) if indexes else source.read()


def build_chip(chip: str, output_dir: Path) -> tuple[str, str, float] | None:
    """Convert one hand-labelled chip to the six model channels and a mask (-1 = no data)."""
    image_name, mask_name = f"{chip}_image.npy", f"{chip}_mask.npy"
    try:
        radar_db = _read("S1Hand", chip).astype(np.float32)
        optical = _read("S2Hand", chip, [GREEN_BAND, RED_BAND, NIR_BAND]).astype(np.float32) / REFLECTANCE_SCALE
        label = _read("LabelHand", chip)[0].astype(np.int8)
    except Exception as error:
        print(f"{chip} skipped: {error}")
        return None

    linear = np.power(10.0, radar_db / 10.0)
    features = build_feature_stack(linear[0], linear[1], optical[1], optical[2], optical[0])
    np.save(output_dir / image_name, features)
    np.save(output_dir / mask_name, label)
    valid = label >= 0
    return image_name, mask_name, float((label == 1).sum() / max(valid.sum(), 1))


def build_split(split: str, root: Path, workers: int) -> None:
    output_dir = root / split
    output_dir.mkdir(parents=True, exist_ok=True)
    chips = read_chip_names(split)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = [row for row in pool.map(lambda chip: build_chip(chip, output_dir), chips) if row]
    with (output_dir / "manifest.csv").open("w", newline="", encoding="utf-8") as manifest:
        writer = csv.writer(manifest)
        writer.writerow(["image_path", "mask_path", "water_fraction"])
        writer.writerows(rows)
    print(f"{split}: {len(rows)}/{len(chips)} chips written to {output_dir}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download Sen1Floods11 hand-labelled chips as model tiles.")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--splits", nargs="+", choices=SPLITS, default=list(SPLITS))
    parser.add_argument("--workers", type=int, default=8)
    arguments = parser.parse_args()
    for split in arguments.splits:
        build_split(split, arguments.output_dir, arguments.workers)


if __name__ == "__main__":
    main()
