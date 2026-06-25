#!/usr/bin/env python3
"""Regression tests for PDF extraction helpers."""

from __future__ import annotations

import os
import sys
import unittest

from extract_bf8_daily import (
    _date_from_filename,
    _infer_year_from_path,
    _is_bf8_label,
    _lookup_param_row,
    _build_param_lookup,
    extract_bf8,
    extract_bf8_combined,
)


class ExtractionFixTests(unittest.TestCase):
    def test_filename_date_parsing(self) -> None:
        path = (
            "/data/DailyProdReports_FY2023-24/NEW P.D.14.05-12.pdf"
        )
        self.assertEqual(_date_from_filename(path), "5. Dec. 2023")
        self.assertEqual(
            _date_from_filename("/data/DailyProdReports_FY2024-25/NEW P.D.14.22-10.pdf"),
            "22. Oct. 2024",
        )

    def test_fiscal_year_inference(self) -> None:
        path = "/DailyProdReports_FY2023-24/file.pdf"
        self.assertEqual(_infer_year_from_path(path, 4), 2023)
        self.assertEqual(_infer_year_from_path(path, 3), 2024)

    def test_bf8_row_labels(self) -> None:
        self.assertTrue(_is_bf8_label("BF # 8"))
        self.assertTrue(_is_bf8_label("BF # 8 =>"))
        self.assertTrue(_is_bf8_label("BF-8"))
        self.assertFalse(_is_bf8_label("BF # 7"))

    def test_iron_ore_fuzzy_lookup(self) -> None:
        table = [
            [None, "(a)", "IRON ORE RATE", "Kg/THM", "578", "", "630", "245", "207", "399"],
        ]
        lookup = _build_param_lookup(table)
        row = _lookup_param_row(lookup, "IRON ORE RATE")
        self.assertIsNotNone(row)
        self.assertEqual(row[8], "207")

    def test_sample_pdf_extraction(self) -> None:
        sample = "/workspace/sample_report.pdf"
        if not os.path.exists(sample):
            self.skipTest("sample_report.pdf not available")

        record = extract_bf8_combined(sample)
        self.assertEqual(float(record["Production_T"]), 2203)
        self.assertEqual(float(record["Iron_ore_rate_kgTHM"]), 207)
        self.assertEqual(float(record["HM_Si_pct_avg"]), 1.05)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
