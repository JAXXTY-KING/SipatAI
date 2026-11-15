import json
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import REPOSITORY_ROOT

DATA_DIRECTORY = REPOSITORY_ROOT / "backend" / "data"
SCAN_DATABASE_PATH = DATA_DIRECTORY / "nationwide_scans.sqlite"
OVERLAY_DIRECTORY = DATA_DIRECTORY / "scan_overlays"
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS tile_scans (
    tile_id TEXT PRIMARY KEY,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    province TEXT NOT NULL,
    scanned_at TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT,
    s1_date TEXT,
    s2_date TEXT,
    mode TEXT,
    clear_fraction REAL,
    flooded_km2 REAL,
    flooded_fraction REAL,
    mean_confidence REAL,
    threshold REAL,
    corners TEXT
)
"""
COLUMNS = (
    "tile_id", "latitude", "longitude", "province", "scanned_at", "status", "message", "s1_date", "s2_date",
    "mode", "clear_fraction", "flooded_km2", "flooded_fraction", "mean_confidence", "threshold", "corners",
)


def _connect() -> sqlite3.Connection:
    DATA_DIRECTORY.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(SCAN_DATABASE_PATH)
    connection.execute(SCHEMA)
    return connection


def overlay_path(tile_id: str) -> Path:
    OVERLAY_DIRECTORY.mkdir(parents=True, exist_ok=True)
    return OVERLAY_DIRECTORY / f"{tile_id}.png"


def save_scan(record: dict[str, Any]) -> None:
    """Insert or replace the latest scan of a tile."""
    row = {column: record.get(column) for column in COLUMNS}
    row["scanned_at"] = row["scanned_at"] or datetime.now(timezone.utc).isoformat(timespec="seconds")
    if row["corners"] is not None:
        row["corners"] = json.dumps(row["corners"])
    placeholders = ", ".join("?" for _ in COLUMNS)
    with _lock, closing(_connect()) as connection, connection:
        connection.execute(
            f"INSERT OR REPLACE INTO tile_scans ({', '.join(COLUMNS)}) VALUES ({placeholders})",
            [row[column] for column in COLUMNS],
        )


def recently_scanned(since_iso: str) -> set[str]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT tile_id FROM tile_scans WHERE scanned_at >= ? AND status = 'ok'", (since_iso,)
        ).fetchall()
    return {row[0] for row in rows}


def scan_summary(totals_by_province: dict[str, int]) -> dict[str, Any]:
    """Coverage and flooding totals across all stored tile scans."""
    with closing(_connect()) as connection:
        overall = connection.execute(
            """
            SELECT COUNT(*), SUM(flooded_km2), MAX(scanned_at), MIN(s1_date), MAX(s1_date),
                   SUM(CASE WHEN flooded_fraction >= 0.01 THEN 1 ELSE 0 END),
                   SUM(CASE WHEN mode = 'radar+optical' THEN 1 ELSE 0 END)
            FROM tile_scans WHERE status = 'ok'
            """
        ).fetchone()
        failures = connection.execute("SELECT COUNT(*) FROM tile_scans WHERE status != 'ok'").fetchone()[0]
        provinces = connection.execute(
            """
            SELECT province, COUNT(*), SUM(flooded_km2), SUM(CASE WHEN flooded_fraction >= 0.01 THEN 1 ELSE 0 END)
            FROM tile_scans WHERE status = 'ok' GROUP BY province
            """
        ).fetchall()
    total_tiles = sum(totals_by_province.values())
    return {
        "tiles_total": total_tiles,
        "tiles_scanned": overall[0] or 0,
        "tiles_failed": failures,
        "coverage_fraction": round((overall[0] or 0) / total_tiles, 4) if total_tiles else 0.0,
        "flooded_km2": round(overall[1] or 0.0, 2),
        "tiles_with_flooding": overall[5] or 0,
        "tiles_with_optical": overall[6] or 0,
        "last_scan": overall[2],
        "radar_dates": [overall[3], overall[4]],
        "provinces": sorted(
            (
                {
                    "province": name,
                    "tiles_scanned": count,
                    "tiles_total": totals_by_province.get(name, 0),
                    "flooded_km2": round(flooded or 0.0, 2),
                    "tiles_with_flooding": affected or 0,
                }
                for name, count, flooded, affected in provinces
            ),
            key=lambda item: item["flooded_km2"],
            reverse=True,
        ),
    }


def overlays_in_bbox(west: float, south: float, east: float, north: float, limit: int = 250) -> list[dict[str, Any]]:
    """Scanned tiles with detected flooding that intersect a viewport, most flooded first."""
    with closing(_connect()) as connection:
        rows = connection.execute(
            """
            SELECT tile_id, latitude, longitude, province, s1_date, s2_date, mode, flooded_km2, flooded_fraction, corners
            FROM tile_scans
            WHERE status = 'ok' AND flooded_fraction > 0
              AND longitude BETWEEN ? AND ? AND latitude BETWEEN ? AND ?
            ORDER BY flooded_km2 DESC LIMIT ?
            """,
            (west - 0.06, east + 0.06, south - 0.06, north + 0.06, limit),
        ).fetchall()
    keys = ("tile_id", "latitude", "longitude", "province", "s1_date", "s2_date", "mode", "flooded_km2", "flooded_fraction")
    return [{**dict(zip(keys, row[:9])), "corners": json.loads(row[9])} for row in rows]
