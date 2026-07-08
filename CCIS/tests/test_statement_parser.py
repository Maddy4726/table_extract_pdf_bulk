#!/usr/bin/env python3
"""Tests for statement PDF/text parsing."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.spend_tracker import load_spend_config
from src.statement_parser import (
    apply_parsed_statements,
    infer_statement_month,
    parse_statement_text,
    parse_statement_pdf,
)


FIXTURES = Path(__file__).parent / "fixtures" / "statements"


class StatementParserTests(unittest.TestCase):
    def test_infer_month_from_period(self) -> None:
        text = "Statement Period: 01/03/2026 to 31/03/2026"
        month = infer_statement_month(text, Path("stmt.pdf"))
        self.assertEqual(month, "2026-03")

    def test_parse_hdfc_labeled_total(self) -> None:
        text = (FIXTURES / "hdfc_sample.txt").read_text(encoding="utf-8")
        parsed = parse_statement_text(text, card_key="hdfc_diners_privilege", source_file="hdfc.pdf")
        assert parsed is not None
        self.assertEqual(parsed.month, "2026-04")
        self.assertEqual(parsed.total_spend_inr, 21190.50)
        self.assertEqual(parsed.method, "labeled_total")

    def test_parse_axis_transaction_fallback(self) -> None:
        text = (FIXTURES / "axis_sample.txt").read_text(encoding="utf-8")
        parsed = parse_statement_text(text, card_key="axis_rewards", source_file="axis.pdf")
        assert parsed is not None
        self.assertEqual(parsed.month, "2026-05")
        self.assertAlmostEqual(parsed.total_spend_inr, 7230.0)

    def test_parse_icici_retail_spend(self) -> None:
        text = (FIXTURES / "icici_sample.txt").read_text(encoding="utf-8")
        parsed = parse_statement_text(text, card_key="icici_rubyx", source_file="icici.pdf")
        assert parsed is not None
        self.assertEqual(parsed.month, "2026-07")
        self.assertEqual(parsed.total_spend_inr, 10400.0)

    def test_apply_updates_spend_config(self) -> None:
        text = (FIXTURES / "axis_sample.txt").read_text(encoding="utf-8")
        parsed = parse_statement_text(text, card_key="axis_rewards", source_file="axis.pdf")
        assert parsed is not None
        with tempfile.TemporaryDirectory() as tmp:
            config_path = Path(tmp) / "spend_tracker.yaml"
            config_path.write_text("period_label: test\nmonths: []\nspends: {}\n", encoding="utf-8")
            from src import spend_tracker as st

            original = st.SPEND_CONFIG_PATH
            st.SPEND_CONFIG_PATH = config_path
            try:
                apply_parsed_statements([parsed])
                data = load_spend_config(config_path)
                self.assertEqual(data["spends"]["axis_rewards"]["2026-05"], 7230.0)
                self.assertIn("2026-05", data["months"])
            finally:
                st.SPEND_CONFIG_PATH = original


if __name__ == "__main__":
    raise SystemExit(unittest.main())
