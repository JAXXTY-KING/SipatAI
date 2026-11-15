"""Scan Philippine land tiles with the MindSpore flood model, newest Sentinel-1 pass first.

Examples (run from the backend folder with the backend virtual environment):
    python -m app.jobs.scan_philippines --limit 40
    python -m app.jobs.scan_philippines --provinces Pampanga Bulacan --workers 4
    python -m app.jobs.scan_philippines --order rainfall --limit 200
"""
import argparse
import asyncio
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from app.db.scan_store import recently_scanned, scan_summary
from app.services.nationwide_grid import land_tiles, tiles_by_province
from app.services.scan_service import scan_tile


def rainfall_priority() -> dict[str, float]:
    """Real forecast peak 24 h rainfall per province, used to scan the wettest provinces first."""
    from app.integrations.province_forecast_client import get_province_forecast

    forecast = asyncio.run(get_province_forecast())
    return {feature["properties"]["name"]: feature["properties"]["rainfall_24h_mm"] for feature in forecast["features"]}


def choose_tiles(arguments: argparse.Namespace):
    tiles = list(land_tiles())
    if arguments.provinces:
        wanted = {name.lower() for name in arguments.provinces}
        tiles = [tile for tile in tiles if tile.province.lower() in wanted]
    if not arguments.force:
        since = (datetime.now(timezone.utc) - timedelta(hours=arguments.rescan_hours)).isoformat(timespec="seconds")
        done = recently_scanned(since)
        tiles = [tile for tile in tiles if tile.tile_id not in done]
    if arguments.order == "rainfall":
        try:
            rain = rainfall_priority()
            tiles.sort(key=lambda tile: -rain.get(tile.province, 0.0))
        except Exception as error:
            print(f"Rainfall priority unavailable ({error}); using random order.")
            random.shuffle(tiles)
    else:
        random.shuffle(tiles)
    return tiles[: arguments.limit] if arguments.limit else tiles


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, default=0, help="Maximum tiles to scan (0 = all remaining).")
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--provinces", nargs="*", help="Only scan these provinces.")
    parser.add_argument("--order", choices=("rainfall", "random"), default="rainfall")
    parser.add_argument("--window-days", type=int, default=14, help="Look for a Sentinel-1 pass this many days back.")
    parser.add_argument("--rescan-hours", type=float, default=24.0, help="Skip tiles scanned more recently than this.")
    parser.add_argument("--force", action="store_true", help="Rescan even recently scanned tiles.")
    arguments = parser.parse_args()

    tiles = choose_tiles(arguments)
    print(f"{len(tiles)} tiles to scan of {len(land_tiles())} Philippine land tiles.", flush=True)
    started = time.time()
    counts = {"ok": 0, "no_data": 0, "error": 0}
    flooded_km2 = 0.0
    with ThreadPoolExecutor(max_workers=arguments.workers) as pool:
        futures = [pool.submit(scan_tile, tile, arguments.window_days) for tile in tiles]
        for done, future in enumerate(as_completed(futures), start=1):
            record = future.result()
            counts[record["status"]] += 1
            flooded_km2 += record.get("flooded_km2") or 0.0
            if done % 10 == 0 or record["status"] == "error":
                rate = done / max(time.time() - started, 1)
                print(
                    f"[{done}/{len(tiles)}] {record['province']} {record['status']} "
                    f"{record.get('flooded_km2', '')} km2 | ok {counts['ok']} no_data {counts['no_data']} "
                    f"error {counts['error']} | {rate * 60:.1f} tiles/min {record.get('message') or ''}",
                    flush=True,
                )
    summary = scan_summary({name: len(group) for name, group in tiles_by_province().items()})
    print(
        f"Done in {(time.time() - started) / 60:.1f} min. Coverage {summary['coverage_fraction'] * 100:.2f}% "
        f"({summary['tiles_scanned']}/{summary['tiles_total']} tiles), {summary['flooded_km2']} km2 flooded detected.",
        flush=True,
    )


if __name__ == "__main__":
    main()
