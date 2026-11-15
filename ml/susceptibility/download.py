"""Download the public terrain and water-history files covering the Philippines once, to local disk.

Sources (Microsoft Planetary Computer, anonymous): Copernicus DEM GLO-90 and JRC Global Surface Water.
    ml\\.venv\\Scripts\\python.exe -m ml.susceptibility.download
"""
import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx
from shapely.geometry import box, shape
from shapely.ops import unary_union

from ml.data import planetary_computer as pc

CACHE = Path("ml/artifacts/susceptibility/cache")
PROVINCES = Path("frontend/public/data/ph_admin2.geojson")
DEM = "cop-dem-glo-90"
GSW = "jrc-gsw"


def land():
    features = json.loads(PROVINCES.read_text(encoding="utf-8"))["features"]
    return unary_union([shape(feature["geometry"]) for feature in features]).buffer(0.05)


def search(collection: str, bbox, limit: int = 1000) -> list[dict]:
    response = httpx.post(pc.STAC_SEARCH_URL, json={"collections": [collection], "bbox": list(bbox), "limit": limit}, timeout=90.0)
    response.raise_for_status()
    return response.json()["features"]


def download(collection: str, item: dict, asset: str, folder: Path) -> str:
    target = folder / f"{item['id']}.tif"
    if target.is_file():
        return "cached"
    folder.mkdir(parents=True, exist_ok=True)
    part = target.with_suffix(".part")
    for attempt in range(4):
        try:
            with httpx.stream("GET", pc._signed_href(collection, item["assets"][asset]["href"]), timeout=300.0, follow_redirects=True) as response:
                response.raise_for_status()
                with part.open("wb") as handle:
                    for block in response.iter_bytes(1 << 20):
                        handle.write(block)
            shutil.move(part, target)
            return "ok"
        except httpx.HTTPError:
            time.sleep(2 * (attempt + 1))
    return "failed"


def main() -> None:
    footprint = land()
    west, south, east, north = footprint.bounds
    dem_items = [item for item in search(DEM, (west, south, east, north)) if box(*item["bbox"]).intersects(footprint)]
    gsw_items = [item for item in search(GSW, (west, south, east, north)) if box(*item["bbox"]).intersects(footprint)]
    print(f"{len(dem_items)} DEM tiles, {len(gsw_items)} water-history tiles", flush=True)
    jobs = [(GSW, item, "occurrence", CACHE / "gsw") for item in gsw_items] + [(DEM, item, "data", CACHE / "dem") for item in dem_items]
    counts: dict[str, int] = {}
    with ThreadPoolExecutor(max_workers=10) as pool:
        futures = [pool.submit(download, *job) for job in jobs]
        for done, future in enumerate(as_completed(futures), start=1):
            outcome = future.result()
            counts[outcome] = counts.get(outcome, 0) + 1
            if done % 10 == 0 or done == len(jobs):
                print(f"[{done}/{len(jobs)}] {counts}", flush=True)


if __name__ == "__main__":
    main()
