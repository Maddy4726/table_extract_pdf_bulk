#!/usr/bin/env python3
"""Tests for CCIS."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.analysis import redundancy_matrix, unique_airports_by_card
from src.dashboard import build_dashboard
from src.database import connect
from src.import_data import import_all
from src.lounge_engine import lookup_airport, spend_recommendations
from src.normalize import normalize_city
from src.spend_tracker import build_milestone_rows


class CCISTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.db_path = ROOT / "database" / "test_ccis.db"
        if cls.db_path.exists():
            cls.db_path.unlink()
        cls.conn = import_all(cls.db_path)

    def test_normalize_city_aliases(self) -> None:
        self.assertEqual(normalize_city("Delhi"), "New Delhi")
        self.assertEqual(normalize_city("Bangalore"), "Bengaluru")
        self.assertEqual(normalize_city("Prayagraj"), "Prayagraj")

    def test_raipur_coverage(self) -> None:
        result = lookup_airport(self.conn, "Raipur")
        self.assertTrue(result["found"])
        keys = {card["card_key"] for card in result["cards"]}
        self.assertIn("icici_rubyx", keys)
        self.assertEqual(result["best_card"], "icici_rubyx")

    def test_axis_metro_only(self) -> None:
        result = lookup_airport(self.conn, "Raipur")
        keys = {card["card_key"] for card in result["cards"]}
        self.assertNotIn("axis_rewards", keys)
        delhi = lookup_airport(self.conn, "New Delhi")
        delhi_keys = {card["card_key"] for card in delhi["cards"]}
        self.assertIn("axis_rewards", delhi_keys)

    def test_spend_priority_by_airport_count(self) -> None:
        recs = spend_recommendations(self.conn)
        self.assertGreater(len(recs), 0)
        # ICICI Rubyx has the widest airport set in official lists (incl. Raipur).
        self.assertEqual(recs[0]["card_key"], "icici_rubyx")
        self.assertGreater(recs[0]["airport_count"], recs[1]["airport_count"] - 5)

    def test_build_dashboard(self) -> None:
        output = build_dashboard(self.conn, ROOT / "dashboard" / "test_ccis.xlsx")
        self.assertTrue(output.exists())

    def test_milestone_eligibility(self) -> None:
        rows = build_milestone_rows()
        by_key = {row["card_key"]: row for row in rows}
        self.assertEqual(by_key["axis_rewards"]["lounge_eligible"], "No")
        self.assertEqual(by_key["axis_rewards"]["rolling_3mo_total_inr"], 31250)
        self.assertEqual(by_key["dbs_supercard"]["lounge_eligible"], "Yes (no spend)")
        self.assertEqual(by_key["hdfc_diners_privilege"]["lounge_eligible"], "No")

    def test_dashboard_has_v11_sheets(self) -> None:
        import openpyxl

        output = build_dashboard(self.conn, ROOT / "dashboard" / "test_ccis_v11.xlsx")
        wb = openpyxl.load_workbook(output, read_only=True)
        for name in ("Spend Tracker", "Milestones", "Unique Airports", "Redundancy"):
            self.assertIn(name, wb.sheetnames)
        wb.close()

    def test_unique_airports_analysis(self) -> None:
        rows = unique_airports_by_card(self.conn, vs_baseline=True)
        rubyx = next(row for row in rows if row["card_key"] == "icici_rubyx")
        self.assertIn("Raipur", rubyx["unique_airports"])

    def test_redundancy_matrix(self) -> None:
        keys, matrix = redundancy_matrix(self.conn)
        self.assertEqual(len(keys), len(matrix))
        idx = keys.index("dbs_supercard")
        self.assertEqual(matrix[idx][idx], 100.0)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
