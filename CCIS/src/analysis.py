"""Airport coverage analysis: unique airports and redundancy."""

from __future__ import annotations

import sqlite3
from typing import Any

from src.import_data import card_airport_counts
from src.normalize import normalize_city

FREE_BASELINE_CARDS = ("dbs_supercard", "indusind_tiger")


def card_airport_sets(conn: sqlite3.Connection) -> dict[str, set[str]]:
    sets: dict[str, set[str]] = {}
    for row in conn.execute("SELECT DISTINCT card_key FROM card_lounge_access ORDER BY card_key"):
        key = row["card_key"]
        airports = {
            normalize_city(r["city"])
            for r in conn.execute(
                "SELECT DISTINCT city FROM card_lounge_access WHERE card_key = ?",
                (key,),
            )
        }
        sets[key] = airports
    return sets


def baseline_airports(airport_sets: dict[str, set[str]]) -> set[str]:
    baseline: set[str] = set()
    for key in FREE_BASELINE_CARDS:
        baseline |= airport_sets.get(key, set())
    return baseline


def unique_airports_by_card(
    conn: sqlite3.Connection,
    *,
    vs_baseline: bool = True,
) -> list[dict[str, Any]]:
    """Airports each card covers that others (or DBS+Tiger) do not."""
    airport_sets = card_airport_sets(conn)
    baseline = baseline_airports(airport_sets) if vs_baseline else set()
    all_other: dict[str, set[str]] = {}
    for key, airports in airport_sets.items():
        all_other[key] = set().union(*(a for k, a in airport_sets.items() if k != key))

    rows: list[dict[str, Any]] = []
    for key, airports in sorted(airport_sets.items()):
        if vs_baseline:
            unique = sorted(airports - baseline)
            label = "beyond DBS + Tiger"
        else:
            unique = sorted(airports - all_other[key])
            label = "not covered by any other card"
        rows.append(
            {
                "card_key": key,
                "total_airports": len(airports),
                "unique_airports_count": len(unique),
                "unique_vs": label,
                "unique_airports": ", ".join(unique) if unique else "(none)",
            }
        )
    return rows


def redundancy_matrix(conn: sqlite3.Connection) -> tuple[list[str], list[list[Any]]]:
    """
    Return card keys and square matrix where cell[i][j] is
    % of row card's airports also covered by column card.
    """
    airport_sets = card_airport_sets(conn)
    keys = sorted(airport_sets)
    matrix: list[list[Any]] = []
    for row_key in keys:
        row_set = airport_sets[row_key]
        row: list[Any] = []
        if not row_set:
            matrix.append([0.0 if k != row_key else 100.0 for k in keys])
            continue
        for col_key in keys:
            col_set = airport_sets[col_key]
            overlap = len(row_set & col_set)
            row.append(round(100.0 * overlap / len(row_set), 1))
        matrix.append(row)
    return keys, matrix
