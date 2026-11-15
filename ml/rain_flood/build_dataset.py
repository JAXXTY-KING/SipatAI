"""Training table for the rain-aware flood model, built only from real data.

Rows are 90 m cells inside the human-labelled Sen1Floods11 chips (11 real flood events on 5 continents):
  - label: flooded (1) or dry land (0) from the hand-labelled Sentinel-1/2 water mask; permanent water is excluded
  - terrain: the same five Copernicus DEM / JRC water-history features as the flood-prone model
  - rain: real ERA5 reanalysis rain (Open-Meteo archive) in the 72 hours up to the satellite pass
    ml\\.venv\\Scripts\\python.exe -m ml.rain_flood.build_dataset
"""
import math
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, timedelta
from pathlib import Path

import httpx
import numpy as np
import rasterio
from rasterio.warp import transform_bounds

from ml.data.sen1floods11 import CHIP_URL, SPLITS, read_chip_names
from ml.susceptibility import download as terrain_download
from ml.susceptibility import features as terrain

OUTPUT = Path("ml/artifacts/rain_flood")
# Satellite pass dates published with the Sen1Floods11 flood events.
EVENT_DATES = {
    "Bolivia": date(2018, 2, 15), "Ghana": date(2018, 9, 18), "India": date(2016, 8, 12), "Mekong": date(2018, 8, 5),
    "Nigeria": date(2018, 9, 21), "Pakistan": date(2017, 6, 28), "Paraguay": date(2018, 10, 31),
    "Somalia": date(2018, 5, 7), "Spain": date(2019, 9, 18), "Sri-Lanka": date(2017, 5, 30), "USA": date(2019, 5, 22),
}
BLOCK = 9  # 9 x 9 ten-metre pixels = one 90 m cell
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"


def read_label(chip: str):
    url = CHIP_URL.format(kind="LabelHand", name=f"{chip}_LabelHand.tif")
    for _ in range(4):
        try:
            response = httpx.get(url, timeout=120.0)
            response.raise_for_status()
            with rasterio.MemoryFile(response.content) as memory, memory.open() as source:
                return source.read(1).astype(np.int8), transform_bounds(source.crs, "EPSG:4326", *source.bounds)
        except httpx.HTTPError:
            continue
    return None


def chip_cells(chip: str):
    """Block the 10 m label to 90 m cells: water label, centre longitude and latitude."""
    loaded = read_label(chip)
    if loaded is None:
        return None
    label, (west, south, east, north) = loaded
    size = label.shape[0] // BLOCK
    blocks = label[: size * BLOCK, : size * BLOCK].reshape(size, BLOCK, size, BLOCK).transpose(0, 2, 1, 3).reshape(size, size, -1)
    valid = (blocks >= 0).mean(axis=2)
    water = (blocks == 1).sum(axis=2) / np.maximum((blocks >= 0).sum(axis=2), 1)
    keep = valid >= 0.6
    rows, columns = np.nonzero(keep)
    longitudes = west + (columns + 0.5) / size * (east - west)
    latitudes = north - (rows + 0.5) / size * (north - south)
    return water[keep] >= 0.5, longitudes, latitudes


def ensure_terrain_files(tiles: set[tuple[int, int]]) -> None:
    items: dict[str, tuple] = {}
    for lon, lat in tiles:
        bbox = (lon + 0.01, lat + 0.01, lon + 0.99, lat + 0.99)
        for item in terrain_download.search(terrain_download.DEM, bbox):
            items[item["id"]] = (terrain_download.DEM, item, "data", terrain_download.CACHE / "dem")
        for item in terrain_download.search(terrain_download.GSW, bbox):
            items[item["id"]] = (terrain_download.GSW, item, "occurrence", terrain_download.CACHE / "gsw")
    print(f"{len(items)} terrain files for {len(tiles)} tiles", flush=True)
    with ThreadPoolExecutor(max_workers=10) as pool:
        for future in as_completed([pool.submit(terrain_download.download, *job) for job in items.values()]):
            future.result()


def terrain_features(longitudes: np.ndarray, latitudes: np.ndarray):
    """Terrain feature rows (n, 5) plus a mask of cells that are usable (land, not permanent water)."""
    features = np.zeros((len(longitudes), 5), dtype=np.float32)
    usable = np.zeros(len(longitudes), dtype=bool)
    tile_ids = np.stack([np.floor(longitudes), np.floor(latitudes)], axis=1).astype(int)
    for lon, lat in {tuple(row) for row in tile_ids}:
        chunk = terrain.read_chunk(lon, lat)
        if chunk is None:
            continue
        elevation, occurrence = chunk
        stack = terrain.build_features(elevation, occurrence, lat + 0.5)
        selected = np.nonzero((tile_ids[:, 0] == lon) & (tile_ids[:, 1] == lat))[0]
        north = lat + 1 + terrain.MARGIN_DEGREES
        west = lon - terrain.MARGIN_DEGREES
        rows = np.clip(((north - latitudes[selected]) / terrain.CELL_DEGREES).astype(int), 0, stack.shape[1] - 1)
        columns = np.clip(((longitudes[selected] - west) / terrain.CELL_DEGREES).astype(int), 0, stack.shape[2] - 1)
        features[selected] = stack[:, rows, columns].T
        water = np.nan_to_num(occurrence[rows, columns], nan=0.0) >= terrain.PERMANENT_WATER_OCCURRENCE
        usable[selected] = ~water & (elevation[rows, columns] > 0.5)
    return features, usable


def event_rain(points: list[tuple[float, float]], day: date) -> dict[tuple[float, float], tuple[float, float]]:
    """Wettest single day and 3-day total (mm) in the 72 h up to the pass, per 0.25 degree ERA5 point."""
    rain: dict[tuple[float, float], tuple[float, float]] = {}
    for start in range(0, len(points), 40):
        batch = points[start : start + 40]
        for _ in range(6):
            try:
                response = httpx.get(ARCHIVE, params={
                    "latitude": ",".join(str(p[0]) for p in batch), "longitude": ",".join(str(p[1]) for p in batch),
                    "start_date": (day - timedelta(days=2)).isoformat(), "end_date": day.isoformat(),
                    "daily": "precipitation_sum", "timezone": "UTC",
                }, timeout=60.0)
                response.raise_for_status()
                break
            except httpx.HTTPError:
                continue
        else:
            raise RuntimeError("Open-Meteo archive unavailable")
        payload = response.json()
        for point, item in zip(batch, payload if isinstance(payload, list) else [payload]):
            values = [value or 0.0 for value in item["daily"]["precipitation_sum"]]
            rain[point] = (max(values), sum(values))
    return rain


def main() -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    names = sorted({name for split in SPLITS for name in read_chip_names(split)})
    print(f"{len(names)} labelled chips", flush=True)
    chips: dict[str, tuple] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {pool.submit(chip_cells, name): name for name in names}
        for done, future in enumerate(as_completed(futures), start=1):
            if (result := future.result()) is not None:
                chips[futures[future]] = result
            if done % 50 == 0:
                print(f"labels {done}/{len(names)}", flush=True)
    labels = np.concatenate([chips[name][0] for name in chips])
    longitudes = np.concatenate([chips[name][1] for name in chips])
    latitudes = np.concatenate([chips[name][2] for name in chips])
    events = np.concatenate([[name.split("_")[0]] * len(chips[name][0]) for name in chips])
    print(f"{len(labels)} cells, {labels.mean():.3f} water share", flush=True)

    tiles = {(int(math.floor(lon)), int(math.floor(lat))) for lon, lat in zip(longitudes[::50], latitudes[::50])}
    ensure_terrain_files(tiles)
    features, usable = terrain_features(longitudes, latitudes)

    rain = np.zeros((len(labels), 2), dtype=np.float32)
    for event, day in EVENT_DATES.items():
        selected = events == event
        if not selected.any():
            continue
        snapped = np.round(np.stack([latitudes[selected], longitudes[selected]], axis=1) * 4) / 4
        unique = sorted({(float(a), float(b)) for a, b in snapped})
        lookup = event_rain(unique, day)
        rain[selected] = np.array([lookup[(float(a), float(b))] for a, b in snapped], dtype=np.float32)
        print(f"{event}: {len(unique)} ERA5 points, mean 72 h rain {rain[selected, 1].mean():.1f} mm", flush=True)

    np.savez_compressed(
        OUTPUT / "dataset.npz", features=features[usable], rain=rain[usable], label=labels[usable].astype(np.int8),
        event=events[usable], longitude=longitudes[usable].astype(np.float32), latitude=latitudes[usable].astype(np.float32),
    )
    print(f"saved {int(usable.sum())} usable cells, flooded share {labels[usable].mean():.3f}", flush=True)


if __name__ == "__main__":
    main()
