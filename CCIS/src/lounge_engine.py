"""Lounge lookup and spend-priority recommendations."""

from __future__ import annotations

import sqlite3
from typing import Any

from src.import_data import airport_coverage_summary, card_airport_counts, load_portfolio_config
from src.normalize import normalize_city

SPEND_PRIORITY_ORDER = [
    "hdfc_diners_privilege",
    "icici_rubyx",
    "au_spont",
    "axis_rewards",
]

FREE_CARDS = ("dbs_supercard", "indusind_tiger")


def lookup_airport(conn: sqlite3.Connection, airport_query: str) -> dict[str, Any]:
    city = normalize_city(airport_query)
    rows = conn.execute(
        """
        SELECT c.card_key, c.card_name, c.lounge_spend_required, c.lounge_spend_inr,
               c.lounge_visits_per_quarter, a.lounge_name, a.terminal, a.terminal_type
        FROM card_lounge_access a
        JOIN cards c ON c.card_key = a.card_key
        WHERE a.city = ?
        ORDER BY c.lounge_spend_required ASC,
                 CASE WHEN c.spend_priority_rank IS NULL THEN 1 ELSE 0 END,
                 c.spend_priority_rank,
                 c.card_name
        """,
        (city,),
    ).fetchall()

    if not rows:
        fuzzy = conn.execute(
            """
            SELECT DISTINCT city FROM card_lounge_access
            WHERE lower(city) LIKE ?
            """,
            (f"%{airport_query.lower()}%",),
        ).fetchall()
        return {
            "airport": city,
            "found": False,
            "suggestions": [r["city"] for r in fuzzy],
            "cards": [],
        }

    cards: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = row["card_key"]
        if key not in cards:
            cards[key] = {
                "card_key": key,
                "card_name": row["card_name"],
                "spend_required": bool(row["lounge_spend_required"]),
                "spend_threshold_inr": row["lounge_spend_inr"],
                "visits_per_quarter": row["lounge_visits_per_quarter"],
                "lounges": [],
            }
        cards[key]["lounges"].append(
            {
                "name": row["lounge_name"],
                "terminal": row["terminal"],
                "type": row["terminal_type"],
            }
        )

    ordered = sorted(
        cards.values(),
        key=lambda item: (
            item["spend_required"],
            SPEND_PRIORITY_ORDER.index(item["card_key"])
            if item["card_key"] in SPEND_PRIORITY_ORDER
            else 99,
        ),
    )
    best = ordered[0] if ordered else None
    best_free = next((c for c in ordered if not c["spend_required"]), None)

    return {
        "airport": city,
        "found": True,
        "best_card": best["card_key"] if best else None,
        "best_free_card": best_free["card_key"] if best_free else None,
        "cards": ordered,
    }


def spend_recommendations(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    """Rank spend-qualified cards for maximizing unique airport coverage."""
    config = load_portfolio_config()
    counts = card_airport_counts(conn)
    matrix = airport_coverage_summary(conn)
    baseline = {
        normalize_city(row["airport"])
        for row in matrix
        if row.get("dbs_supercard") == "Yes" or row.get("indusind_tiger") == "Yes"
    }

    recs: list[dict[str, Any]] = []
    for card in config["cards"]:
        key = card["key"]
        if key in FREE_CARDS or not card.get("lounge_spend_required"):
            continue
        card_airports = {
            normalize_city(row["airport"])
            for row in matrix
            if row.get(key) == "Yes"
        }
        incremental = sorted(card_airports - baseline)
        recs.append(
            {
                "card_key": key,
                "card_name": card["name"],
                "airport_count": counts.get(key, 0),
                "incremental_airports": len(incremental),
                "incremental_list": incremental,
                "spend_inr": card.get("lounge_spend_inr"),
                "spend_window_months": card.get("lounge_spend_window_months"),
                "priority_rank": card.get("spend_priority_rank"),
            }
        )

    recs.sort(
        key=lambda item: (
            -item["airport_count"],
            -item["incremental_airports"],
            item["priority_rank"] if item["priority_rank"] is not None else 99,
        )
    )
    return recs
