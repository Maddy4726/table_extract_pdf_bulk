"""SQLite persistence for CCIS."""

from __future__ import annotations

import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "database" / "ccis.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS cards (
    card_key TEXT PRIMARY KEY,
    bank TEXT NOT NULL,
    card_name TEXT NOT NULL,
    network TEXT,
    status TEXT,
    annual_fee_inr REAL,
    fee_waiver_spend_inr REAL,
    lounge_visits_per_quarter INTEGER,
    lounge_spend_required INTEGER,
    lounge_spend_inr REAL,
    lounge_spend_window_months INTEGER,
    lounge_priority TEXT,
    spend_priority_rank INTEGER,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS lounges (
    lounge_id INTEGER PRIMARY KEY AUTOINCREMENT,
    city TEXT NOT NULL,
    lounge_name TEXT,
    terminal TEXT,
    terminal_type TEXT,
    source TEXT
);

CREATE TABLE IF NOT EXISTS card_lounge_access (
    card_key TEXT NOT NULL,
    city TEXT NOT NULL,
    lounge_name TEXT,
    terminal TEXT,
    terminal_type TEXT,
    source TEXT,
    PRIMARY KEY (card_key, city, lounge_name, terminal)
);

CREATE TABLE IF NOT EXISTS spend_tracker (
    card_key TEXT PRIMARY KEY,
    current_spend_inr REAL DEFAULT 0,
    target_spend_inr REAL,
    period_label TEXT,
    lounge_eligible INTEGER DEFAULT 0
);
"""


def connect(db_path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(db_path or DEFAULT_DB)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn
