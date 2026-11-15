"""Build training data and the nationwide susceptibility map from the locally cached terrain files.

    ml\\.venv\\Scripts\\python.exe -m ml.susceptibility.national train-data
    ml\\.venv\\Scripts\\python.exe -m ml.susceptibility.train
    ml\\.venv\\Scripts\\python.exe -m ml.susceptibility.national score
"""
import argparse
import io
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy.ndimage import gaussian_filter

from ml.susceptibility import features as terrain

OUTPUT = Path("ml/artifacts/susceptibility")
MARGIN_CELLS = round(terrain.MARGIN_DEGREES / terrain.CELL_DEGREES)
CORE = round(1 / terrain.CELL_DEGREES)
PIXELS_PER_CLASS = 4000
MODERATE, HIGH = 0.5, 0.75


def land_chunks() -> list[tuple[int, int]]:
    """South-west corners of the 1 degree squares that have elevation data."""
    corners = set()
    for path in (terrain.CACHE / "dem").glob("*.tif"):
        name = path.stem  # Copernicus_DSM_COG_30_N14_00_E120_00_DEM
        parts = name.split("_")
        north = int(parts[4][1:]) * (1 if parts[4][0] == "N" else -1)
        east = int(parts[6][1:]) * (1 if parts[6][0] == "E" else -1)
        corners.add((east, north))
    return sorted(corners)


def training_data() -> None:
    folder = OUTPUT / "tiles"
    folder.mkdir(parents=True, exist_ok=True)
    generator = np.random.default_rng(3)
    for longitude, latitude in land_chunks():
        target = folder / f"{longitude}_{latitude}.npz"
        chunk = terrain.read_chunk(longitude, latitude)
        if chunk is None or target.is_file():
            continue
        elevation, occurrence = chunk
        features = terrain.build_features(elevation, occurrence, latitude + 0.5)
        labels = terrain.history_labels(occurrence, elevation)
        labels[:MARGIN_CELLS] = labels[-MARGIN_CELLS:] = -1
        labels[:, :MARGIN_CELLS] = labels[:, -MARGIN_CELLS:] = -1
        picked = []
        for value in (0, 1):
            rows, columns = np.nonzero(labels == value)
            if len(rows):
                choice = generator.choice(len(rows), size=min(PIXELS_PER_CLASS, len(rows)), replace=False)
                picked.append((rows[choice], columns[choice]))
        if not picked:
            continue
        rows, columns = np.concatenate([p[0] for p in picked]), np.concatenate([p[1] for p in picked])
        np.savez_compressed(target, x=features[:, rows, columns].T, y=labels[rows, columns], province=f"{longitude}E_{latitude}N")
        print(f"chunk {longitude}E {latitude}N: {len(rows)} pixels", flush=True)


def colour_overlay(score: np.ndarray) -> bytes:
    """Smooth, readable colours: transparent below moderate, then yellow -> orange -> red -> crimson."""
    smooth = gaussian_filter(score, sigma=1.2)  # about 100 m, removes single-cell noise
    stops = np.array([0.35, 0.5, 0.65, 0.8, 1.0])
    palette = np.array([[254, 240, 138], [253, 186, 80], [249, 115, 22], [220, 38, 38], [127, 29, 29]], dtype=np.float32)
    rgba = np.zeros((*score.shape, 4), dtype=np.uint8)
    for channel in range(3):
        rgba[..., channel] = np.interp(smooth, stops, palette[:, channel])
    rgba[..., 3] = np.interp(smooth, [0.35, 0.5, 0.75, 1.0], [0, 90, 170, 215]).astype(np.uint8)
    rgba[..., 3] = np.where(score > 0, rgba[..., 3], 0)
    buffer = io.BytesIO()
    Image.fromarray(rgba, mode="RGBA").save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def score_nationwide() -> None:
    import mindspore as ms

    from ml.susceptibility.model import load_susceptibility_net

    ms.set_device("CPU")
    ms.set_context(mode=ms.PYNATIVE_MODE)
    network = load_susceptibility_net(OUTPUT / "susceptibility.ckpt")
    folder = OUTPUT / "national"
    folder.mkdir(parents=True, exist_ok=True)
    index = []
    for longitude, latitude in land_chunks():
        chunk = terrain.read_chunk(longitude, latitude)
        if chunk is None:
            continue
        elevation, occurrence = chunk
        features = terrain.build_features(elevation, occurrence, latitude + 0.5)
        core = (slice(MARGIN_CELLS, MARGIN_CELLS + CORE),) * 2
        flat = np.ascontiguousarray(features[(slice(None), *core)].reshape(features.shape[0], -1).T)
        logits = np.concatenate(
            [network(ms.Tensor(flat[i : i + 131072], ms.float32)).asnumpy()[:, 0] for i in range(0, len(flat), 131072)]
        )
        score = (1 / (1 + np.exp(-logits))).reshape(CORE, CORE).astype(np.float32)
        land = (elevation[core] > 0.5) & (np.nan_to_num(occurrence[core], nan=0.0) < terrain.PERMANENT_WATER_OCCURRENCE)
        score = np.where(land, score, 0.0)
        if not land.any():
            continue
        name = f"{longitude}E_{latitude}N"
        (folder / f"{name}.png").write_bytes(colour_overlay(score))
        np.save(folder / f"{name}.npy", (score * 255).astype(np.uint8))
        cell_km2 = (terrain.CELL_DEGREES * 110.574) * (terrain.CELL_DEGREES * 111.32 * np.cos(np.radians(latitude + 0.5)))
        index.append({
            "id": name, "west": longitude, "south": latitude, "east": longitude + 1, "north": latitude + 1,
            "land_km2": round(float(land.sum() * cell_km2), 1),
            "high_km2": round(float((score >= HIGH).sum() * cell_km2), 1),
            "moderate_km2": round(float(((score >= MODERATE) & (score < HIGH)).sum() * cell_km2), 1),
        })
        print(f"scored {name}: high {index[-1]['high_km2']} km2 of {index[-1]['land_km2']} km2", flush=True)
    (folder / "index.json").write_text(json.dumps(index), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("train-data", "score"))
    action = parser.parse_args().action
    training_data() if action == "train-data" else score_nationwide()


if __name__ == "__main__":
    main()
