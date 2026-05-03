"""SQLite persistence layer for car park readings."""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "carpark.db"


def init_db() -> None:
    """Create the readings table if it does not already exist."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS readings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            raw_count REAL NOT NULL,
            occupancy REAL NOT NULL
        )
        """
    )
    conn.commit()
    conn.close()


def insert_reading(timestamp: str, raw_count: float, occupancy: float) -> None:
    """Insert a new reading row into the database."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute(
        "INSERT INTO readings (timestamp, raw_count, occupancy) VALUES (?, ?, ?)",
        (timestamp, raw_count, occupancy),
    )
    conn.commit()
    conn.close()


def get_latest_reading() -> dict | None:
    """Return the most recent reading as a dict, or None if no rows exist."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT timestamp, raw_count, occupancy FROM readings ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if row is None:
        return None
    return {"timestamp": row[0], "raw_count": row[1], "occupancy": row[2]}
