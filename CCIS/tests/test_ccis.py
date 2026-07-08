#!/usr/bin/env python3
"""Tests for CCIS."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.dashboard import build_dashboard
from src.database import connect
from src.import_data import import_all
from src.lounge_engine import lookup_airport, spend_recommendations
from src.normalize import normalize_city


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


if __name__ == "__main__":
    raise SystemExit(unittest.main())
