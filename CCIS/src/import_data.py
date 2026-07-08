"""Load portfolio config and lounge data into SQLite."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import yaml

from src.database import DEFAULT_DB, connect
from src.lounge_data import CARD_LOUNGE_SOURCES, lounges_to_airports
from src.normalize import normalize_city

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config" / "portfolio.yaml"


def load_portfolio_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or CONFIG_PATH
    with config_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def import_all(db_path: Path | str | None = None, config_path: Path | None = None) -> sqlite3.Connection:
    config = load_portfolio_config(config_path)
    conn = connect(db_path)

    conn.execute("DELETE FROM cards")
    conn.execute("DELETE FROM lounges")
    conn.execute("DELETE FROM card_lounge_access")
    conn.execute("DELETE FROM spend_tracker")

    for card in config["cards"]:
        conn.execute(
            """
            INSERT INTO cards (
                card_key, bank, card_name, network, status, annual_fee_inr,
                fee_waiver_spend_inr, lounge_visits_per_quarter, lounge_spend_required,
                lounge_spend_inr, lounge_spend_window_months, lounge_priority,
                spend_priority_rank, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                card["key"],
                card["bank"],
                card["name"],
                card.get("network"),
                card.get("status", "active"),
                card.get("annual_fee_inr"),
                card.get("fee_waiver_spend_inr"),
                card.get("lounge_visits_per_quarter"),
                1 if card.get("lounge_spend_required") else 0,
                card.get("lounge_spend_inr"),
                card.get("lounge_spend_window_months"),
                card.get("lounge_priority"),
                card.get("spend_priority_rank"),
                card.get("notes"),
            ),
        )
        conn.execute(
            """
            INSERT INTO spend_tracker (card_key, current_spend_inr, target_spend_inr, period_label)
            VALUES (?, 0, ?, 'current_quarter')
            """,
            (card["key"], card.get("lounge_spend_inr")),
        )

    seen_lounges: set[tuple[str, str, str, str]] = set()
    for card_key, entries in CARD_LOUNGE_SOURCES.items():
        if not entries:
            continue
        if isinstance(entries[0], str):
            for city_name in entries:
                city = normalize_city(city_name)
                conn.execute(
                    """
                    INSERT OR IGNORE INTO card_lounge_access
                    (card_key, city, lounge_name, terminal, terminal_type, source)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (card_key, city, "(any eligible lounge)", "", "Domestic", "official_list"),
                )
            continue

        for city_raw, lounge_name, terminal, terminal_type in entries:
            city = normalize_city(city_raw)
            key = (city, lounge_name, terminal, terminal_type)
            if key not in seen_lounges:
                conn.execute(
                    """
                    INSERT INTO lounges (city, lounge_name, terminal, terminal_type, source)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (city, lounge_name, terminal, terminal_type, "official_list"),
                )
                seen_lounges.add(key)
            conn.execute(
                """
                INSERT OR IGNORE INTO card_lounge_access
                (card_key, city, lounge_name, terminal, terminal_type, source)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (card_key, city, lounge_name, terminal, terminal_type, "official_list"),
            )

    conn.commit()
    from src.spend_tracker import sync_spends_to_db

    sync_spends_to_db(conn, portfolio=config)
    return conn


def airport_coverage_summary(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    cards = [row["card_key"] for row in conn.execute("SELECT card_key FROM cards ORDER BY card_key")]
    airports = sorted(
        {
            normalize_city(row["city"])
            for row in conn.execute("SELECT DISTINCT city FROM card_lounge_access")
        }
    )
    rows: list[dict[str, Any]] = []
    for airport in airports:
        covered = {
            row["card_key"]
            for row in conn.execute(
                "SELECT card_key FROM card_lounge_access WHERE city = ?",
                (airport,),
            )
        }
        row = {"airport": airport}
        for card in cards:
            row[card] = "Yes" if card in covered else ""
        free_cards = [c for c in ("dbs_supercard", "indusind_tiger") if c in covered]
        spend_cards = [
            c
            for c in cards
            if c in covered and c not in ("dbs_supercard", "indusind_tiger")
        ]
        row["best_free"] = free_cards[0] if free_cards else ""
        row["best_spend"] = spend_cards[0] if spend_cards else row["best_free"]
        rows.append(row)
    return rows


def card_airport_counts(conn: sqlite3.Connection) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in conn.execute(
        "SELECT card_key, COUNT(DISTINCT city) AS n FROM card_lounge_access GROUP BY card_key"
    ):
        counts[row["card_key"]] = row["n"]
    return counts
