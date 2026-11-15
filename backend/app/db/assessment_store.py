import json
import sqlite3
import threading
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import REPOSITORY_ROOT

DATABASE_PATH = REPOSITORY_ROOT / "backend" / "data" / "satellite_assessments.sqlite"
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS satellite_assessments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    latitude REAL NOT NULL,
    longitude REAL NOT NULL,
    event_date TEXT,
    payload TEXT NOT NULL
)
"""


class AssessmentRecordNotFound(LookupError):
    """Raised when a saved satellite assessment does not exist."""


def _connect() -> sqlite3.Connection:
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH)
    connection.execute(SCHEMA)
    return connection


def save_assessment(latitude: float, longitude: float, event_date: str | None, summary: dict[str, Any]) -> int:
    """Persist the measured numbers of one MindSpore analysis (not the overlay image or polygons)."""
    with _lock, closing(_connect()) as connection, connection:
        cursor = connection.execute(
            "INSERT INTO satellite_assessments (created_at, latitude, longitude, event_date, payload) VALUES (?, ?, ?, ?, ?)",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"), latitude, longitude, event_date, json.dumps(summary)),
        )
        return int(cursor.lastrowid)


def _row_to_record(row: tuple) -> dict[str, Any]:
    return {
        "id": row[0],
        "created_at": row[1],
        "latitude": row[2],
        "longitude": row[3],
        "event_date": row[4],
        **json.loads(row[5]),
    }


def list_assessments(limit: int = 50) -> list[dict[str, Any]]:
    with closing(_connect()) as connection:
        rows = connection.execute(
            "SELECT id, created_at, latitude, longitude, event_date, payload FROM satellite_assessments ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [_row_to_record(row) for row in rows]


def get_assessment(assessment_id: int) -> dict[str, Any]:
    with closing(_connect()) as connection:
        row = connection.execute(
            "SELECT id, created_at, latitude, longitude, event_date, payload FROM satellite_assessments WHERE id = ?",
            (assessment_id,),
        ).fetchone()
    if row is None:
        raise AssessmentRecordNotFound(f"Satellite assessment {assessment_id} was not found.")
    return _row_to_record(row)
