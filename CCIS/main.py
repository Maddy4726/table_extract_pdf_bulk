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
from src.import_data import airport_coverage_summary, card_airport_counts, import_all, load_portfolio_config
from src.lounge_engine import lookup_airport, spend_recommendations
from src.spend_tracker import (
    build_milestone_rows,
    load_spend_config,
    set_card_month_spend,
    set_card_rolling_spend,
    sync_spends_to_db,
)
from src.statement_parser import format_import_report, import_statements


def cmd_build(args: argparse.Namespace) -> int:
    if args.import_statements:
        report = import_statements()
        print(format_import_report(report))
        print()
    conn = import_all()
    output = build_dashboard(conn)
    counts = card_airport_counts(conn)
    print(f"Database -> {DEFAULT_DB}")
    print(f"Dashboard -> {output}")
    print("Domestic airport coverage by card:")
    for key, count in sorted(counts.items(), key=lambda item: -item[1]):
        print(f"  {key:24} {count:3} airports")
    print("\nLounge milestones:")
    for row in build_milestone_rows():
        if row["lounge_target_inr"]:
            print(
                f"  {row['card_name']:28} "
                f"₹{row['rolling_3mo_total_inr']:,.0f} / ₹{row['lounge_target_inr']:,.0f} "
                f"→ {row['lounge_eligible']}"
            )
        else:
            print(f"  {row['card_name']:28} {row['lounge_eligible']}")
    return 0


def cmd_milestones(_: argparse.Namespace) -> int:
    rows = build_milestone_rows()
    print(f"Period: {load_spend_config().get('period_label', '')}\n")
    for row in rows:
        if row["lounge_target_inr"]:
            remaining = row["remaining_inr"] or 0
            print(
                f"{row['card_name']}\n"
                f"  Spend:   ₹{row['rolling_3mo_total_inr']:,.0f} / ₹{row['lounge_target_inr']:,.0f} "
                f"({row['pct_to_lounge']}%)\n"
                f"  Left:    ₹{remaining:,.0f}\n"
                f"  Lounge:  {row['lounge_eligible']}\n"
            )
        else:
            print(f"{row['card_name']}\n  Lounge:  {row['lounge_eligible']}\n")
    return 0


def cmd_spend_set(args: argparse.Namespace) -> int:
    portfolio = load_portfolio_config()
    valid_keys = {card["key"] for card in portfolio["cards"]}
    if args.card not in valid_keys:
        print(f"Unknown card '{args.card}'. Valid keys: {', '.join(sorted(valid_keys))}", file=sys.stderr)
        return 1

    if args.month:
        set_card_month_spend(args.card, args.month, args.amount)
        print(f"Updated {args.card} {args.month} → ₹{args.amount:,.0f}")
    else:
        set_card_rolling_spend(args.card, args.amount)
        print(f"Updated {args.card} rolling total → ₹{args.amount:,.0f} (applied to last month in config)")

    conn = connect()
    sync_spends_to_db(conn)
    build_dashboard(conn)
    print("Dashboard refreshed.")
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


def cmd_statements_import(args: argparse.Namespace) -> int:
    report = import_statements()
    print(format_import_report(report))
    if args.rebuild and report.parsed:
        conn = connect()
        sync_spends_to_db(conn)
        output = build_dashboard(conn)
        print(f"\nDashboard refreshed -> {output}")
    return 1 if report.errors else 0


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
    build.add_argument(
        "--import-statements",
        action="store_true",
        help="Parse statement PDFs from statements/ before rebuilding",
    )
    build.set_defaults(func=cmd_build)

    milestones = sub.add_parser("milestones", help="Show lounge spend progress")
    milestones.set_defaults(func=cmd_milestones)

    spend = sub.add_parser("spend", help="Update monthly spend in config/spend_tracker.yaml")
    spend_sub = spend.add_subparsers(dest="spend_command", required=True)
    spend_set = spend_sub.add_parser("set", help="Set spend for a card")
    spend_set.add_argument("card", help="Card key, e.g. axis_rewards")
    spend_set.add_argument("amount", type=float, help="Amount in INR")
    spend_set.add_argument("--month", help="Calendar month YYYY-MM; omit to set rolling total")
    spend_set.set_defaults(func=cmd_spend_set)

    coverage = sub.add_parser("coverage", help="Show spend priority for maximum airport coverage")
    coverage.set_defaults(func=cmd_coverage)

    lounge = sub.add_parser("lounge", help="Look up lounge access at an airport")
    lounge.add_argument("airport", help="Airport city name, e.g. Raipur or Delhi")
    lounge.set_defaults(func=cmd_lounge)

    statements = sub.add_parser("statements", help="Import monthly spend from statement PDFs")
    statements_sub = statements.add_subparsers(dest="statements_command", required=True)
    statements_import = statements_sub.add_parser("import", help="Parse PDFs under statements/")
    statements_import.add_argument(
        "--rebuild",
        action="store_true",
        help="Refresh SQLite spend data and Excel dashboard after import",
    )
    statements_import.set_defaults(func=cmd_statements_import)

    matrix = sub.add_parser("matrix", help="Print airport × card coverage matrix")
    matrix.add_argument("--json", action="store_true")
    matrix.set_defaults(func=cmd_matrix)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
