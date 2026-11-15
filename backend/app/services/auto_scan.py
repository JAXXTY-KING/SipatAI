"""Optional background satellite scan: keeps scanning Philippine tiles with the MindSpore flood model.

Enabled with SIPATAI_AUTO_SCAN=1. It scans one tile at a time, wettest forecast provinces first,
skips tiles scanned within the last 24 hours, and pauses between rounds. It competes with the API for CPU.
"""
import argparse
import logging
import os
import threading
import time

logger = logging.getLogger("sipatai.auto_scan")
_stop = threading.Event()
_thread: threading.Thread | None = None

BATCH_TILES = 20
PAUSE_SECONDS = 15 * 60


def is_enabled() -> bool:
    return os.getenv("SIPATAI_AUTO_SCAN", "").strip().lower() in {"1", "true", "yes", "on"}


def _run() -> None:
    from app.jobs.scan_philippines import choose_tiles
    from app.services.scan_service import scan_tile

    while not _stop.is_set():
        try:
            arguments = argparse.Namespace(
                provinces=None, force=False, rescan_hours=24.0, order="rainfall", limit=BATCH_TILES,
            )
            tiles = choose_tiles(arguments)
            logger.info("Auto scan: %d tiles in this round.", len(tiles))
            for tile in tiles:
                if _stop.is_set():
                    return
                scan_tile(tile, 14)
        except Exception:
            logger.exception("Auto scan round failed.")
        _stop.wait(PAUSE_SECONDS)


def start() -> bool:
    global _thread
    if not is_enabled() or (_thread and _thread.is_alive()):
        return False
    _stop.clear()
    _thread = threading.Thread(target=_run, name="sipatai-auto-scan", daemon=True)
    _thread.start()
    return True


def stop() -> None:
    _stop.set()
