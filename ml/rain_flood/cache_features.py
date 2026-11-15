"""Cache the five terrain features of every Philippine one-degree chunk (8-bit) so forecasts can be scored in seconds.

    ml\\.venv\\Scripts\\python.exe -m ml.rain_flood.cache_features
"""
import json
from pathlib import Path

import numpy as np

from ml.susceptibility import features as terrain
from ml.susceptibility.national import CORE, MARGIN_CELLS, OUTPUT

FOLDER = OUTPUT / "national"


def main() -> None:
    for chunk in json.loads((FOLDER / "index.json").read_text(encoding="utf-8")):
        target = FOLDER / f"{chunk['id']}.feat.npy"
        if target.is_file():
            continue
        data = terrain.read_chunk(chunk["west"], chunk["south"])
        if data is None:
            continue
        elevation, occurrence = data
        stack = terrain.build_features(elevation, occurrence, chunk["south"] + 0.5)
        core = stack[:, MARGIN_CELLS : MARGIN_CELLS + CORE, MARGIN_CELLS : MARGIN_CELLS + CORE]
        np.save(target, np.round(np.clip(core, 0, 1) * 255).astype(np.uint8))
        print(f"cached {chunk['id']}", flush=True)


if __name__ == "__main__":
    main()
