#!/usr/bin/env python3
"""Credit Card Intelligence System (CCIS) — CLI entry point."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from src.dashboard import build_dashboard
from src.database import DEFAULT_DB, connect
from src.import_data import airport_coverage_summary, card_airport_counts, import_all
from src.lounge_engine import lookup_airport, spend_recommendations


def cmd_build(_: argparse.Namespace) -> int:
    conn = import_all()
    output = build_dashboard(conn)
    counts = card_airport_counts(conn)
    print(f"Database -> {DEFAULT_DB}")
    print(f"Dashboard -> {output}")
    print("Domestic airport coverage by card:")
    for key, count in sorted(counts.items(), key=lambda item: -item[1]):
        print(f"  {key:24} {count:3} airports")
    return 0


def cmd_coverage(_: argparse.Namespace) -> int:
    conn = connect()
    recs = spend_recommendations(conn)
    print("Spend-qualified cards ranked by total domestic airport coverage:\n")
    for rec in recs:
        print(
            f"{rec['priority_rank'] or '-'}. {rec['card_name']}: "
            f"{rec['airport_count']} airports total, "
            f"+{rec['incremental_airports']} beyond DBS/Tiger only"
        )
        if rec["incremental_list"]:
            print(f"   Unique adds: {', '.join(rec['incremental_list'][:12])}")
            if len(rec["incremental_list"]) > 12:
                print(f"   ... and {len(rec['incremental_list']) - 12} more")
        print(f"   Spend target: ₹{rec['spend_inr']:,} / {rec['spend_window_months']} month(s)\n")
    return 0


def cmd_lounge(args: argparse.Namespace) -> int:
    conn = connect()
    result = lookup_airport(conn, args.airport)
    if not result["found"]:
        print(f"No lounge data for '{args.airport}'.")
        if result["suggestions"]:
            print("Did you mean:", ", ".join(result["suggestions"]))
        return 1
    print(f"Airport: {result['airport']}")
    print(f"Best card (overall): {result['best_card']}")
    print(f"Best free card: {result['best_free_card']}\n")
    for card in result["cards"]:
        spend = (
            f"spend ₹{card['spend_threshold_inr']:,} required"
            if card["spend_required"]
            else "no spend required"
        )
        print(f"- {card['card_name']} ({spend})")
        for lounge in card["lounges"][:5]:
            print(f"    • {lounge['name']} | {lounge['terminal']} | {lounge['type']}")
        if len(card["lounges"]) > 5:
            print(f"    • ... {len(card['lounges']) - 5} more lounges")
    return 0


def cmd_matrix(args: argparse.Namespace) -> int:
    conn = connect()
    rows = airport_coverage_summary(conn)
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    cards = [key for key in rows[0].keys() if key not in ("airport", "best_free", "best_spend")] if rows else []
    header = f"{'Airport':<18}" + "".join(f"{c[:8]:>10}" for c in cards) + f"{'Best':>14}"
    print(header)
    for row in rows:
        line = f"{row['airport']:<18}"
        for card in cards:
            mark = "✓" if row.get(card) == "Yes" else ""
            line += f"{mark:>10}"
        line += f"{row.get('best_spend',''):>14}"
        print(line)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Credit Card Intelligence System (CCIS)")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Import lounge data and generate Excel dashboard")
    build.set_defaults(func=cmd_build)

    coverage = sub.add_parser("coverage", help="Show spend priority for maximum airport coverage")
    coverage.set_defaults(func=cmd_coverage)

    lounge = sub.add_parser("lounge", help="Look up lounge access at an airport")
    lounge.add_argument("airport", help="Airport city name, e.g. Raipur or Delhi")
    lounge.set_defaults(func=cmd_lounge)

    matrix = sub.add_parser("matrix", help="Print airport × card coverage matrix")
    matrix.add_argument("--json", action="store_true")
    matrix.set_defaults(func=cmd_matrix)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
