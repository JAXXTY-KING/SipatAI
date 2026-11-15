"""Re-apply the land mask to scans stored before it existed, without re-reading any satellite data.

Each stored overlay is the model's flood layer for one 5 km tile; and the tile's flooded area is recomputed from what remains (overlay pixels x 100 m2).
    python -m app.jobs.remask_scans
"""
import io

import numpy as np
from PIL import Image

from app.db import scan_store
from app.services.land_mask import land_mask


def main() -> None:
    from ml.data import planetary_computer as pc

    connection = scan_store._connect()
    rows = connection.execute("SELECT tile_id, longitude, latitude, corners FROM tile_scans WHERE status = 'ok'").fetchall()
    pixel_km2 = pc.PIXEL_SIZE_METRES**2 / 1_000_000
    for tile_id, longitude, latitude, _corners in rows:
        path = scan_store.overlay_path(tile_id)
        if not path.is_file():
            continue
        grid = pc.make_grid(longitude, latitude)
        bbox = pc.grid_bbox(grid)
        image = np.array(Image.open(path).convert("RGBA"))
        land = land_mask(grid, bbox, image.shape[:2])
        before = int((image[..., 3] > 0).sum())
        image[~land, 3] = 0
        after = int((image[..., 3] > 0).sum())
        buffer = io.BytesIO()
        Image.fromarray(image, mode="RGBA").save(buffer, format="PNG", optimize=True)
        path.write_bytes(buffer.getvalue())
        connection.execute(
            "UPDATE tile_scans SET flooded_km2 = ?, flooded_fraction = ? WHERE tile_id = ?",
            (round(after * pixel_km2, 3), round(after / image[..., 3].size, 4), tile_id),
        )
        print(f"{tile_id}: {before} -> {after} flooded pixels", flush=True)
    connection.commit()


if __name__ == "__main__":
    main()
