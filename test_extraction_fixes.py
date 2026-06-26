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
from extract_hot_metal_slag import extract_hot_metal_slag
from extract_skip_iron_ore import extract_skip_iron_ore
from extract_pellet_analysis import extract_pellet_analysis


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

    def test_iron_rate_alias_pdf(self) -> None:
        sample = "/home/ubuntu/.cursor/projects/workspace/uploads/NEW_P.D.14.25-07_4f8e.pdf"
        if not os.path.exists(sample):
            self.skipTest("NEW_P.D.14.25-07 sample not available")

        record = extract_bf8(sample)
        self.assertEqual(float(record["Iron_ore_rate_kgTHM"]), 414)
        self.assertEqual(float(record["QuartzRate_kgTHM"]), 0)

    def test_sample_pdf_extraction(self) -> None:
        sample = "/workspace/sample_report.pdf"
        if not os.path.exists(sample):
            self.skipTest("sample_report.pdf not available")

        record = extract_bf8_combined(sample)
        self.assertEqual(float(record["Production_T"]), 2203)
        self.assertEqual(float(record["Iron_ore_rate_kgTHM"]), 207)
        self.assertEqual(float(record["HM_Si_pct_avg"]), 1.05)

    def test_hot_metal_slag_extraction(self) -> None:
        sample = "/workspace/NEW P.D.14.01-01.pdf"
        if not os.path.exists(sample):
            self.skipTest("NEW P.D.14.01-01.pdf not available")

        record = extract_hot_metal_slag(sample)
        self.assertEqual(record["report_date"], "1. Jan. 2025")
        self.assertEqual(record["HM_Si_pct_avg"], "0.71")
        self.assertEqual(record["HM_S_pct_avg"], "0.023")
        self.assertEqual(record["Slag_Basicity_avg"], "0.97")
        self.assertEqual(record["HM_Si_pct_min"], "0.43")
        self.assertEqual(record["HM_Si_pct_max"], "0.99")
        self.assertEqual(record["HM_Si_pct_till"], "0.71")

    def test_skip_iron_ore_extraction(self) -> None:
        sample = "/workspace/NEW P.D.14.01-01.pdf"
        if not os.path.exists(sample):
            self.skipTest("NEW P.D.14.01-01.pdf not available")

        record = extract_skip_iron_ore(sample)
        self.assertEqual(record["SkipIronOre_Fe_pct"], "63.56")
        self.assertEqual(record["SkipIronOre_SiO2_pct"], "2.09")
        self.assertEqual(record["SkipIronOre_Al2O3_pct"], "4.03")
        self.assertEqual(record["SkipIronOre_Moist_pct"], "4")
        self.assertEqual(record["SkipIronOre_plus40mm"], "21.02")
        self.assertEqual(record["SkipIronOre_minus10mm"], "13.75")
        self.assertEqual(record["SkipIronOre_MSize"], "26.87")

    def test_pellet_analysis_extraction(self) -> None:
        sample = "/workspace/NEW P.D.14.01-01.pdf"
        if not os.path.exists(sample):
            self.skipTest("NEW P.D.14.01-01.pdf not available")

        record = extract_pellet_analysis(sample)
        self.assertEqual(record["Pellet_Fe_pct"], "61.23")
        self.assertEqual(record["Pellet_SiO2_pct"], "6.42")
        self.assertEqual(record["Pellet_plus10mm"], "52.80")
        self.assertEqual(record["Pellet_MSize"], "11.00")
        self.assertEqual(record["Pellet_Basicity"], "0.11")

    def test_pellet_analysis_bf8_in_title_format(self) -> None:
        sample = "/home/ubuntu/.cursor/projects/workspace/uploads/NEW_P.D.14.17-06_570f.pdf"
        if not os.path.exists(sample):
            self.skipTest("NEW_P.D.14.17-06 sample not available")

        record = extract_pellet_analysis(sample)
        self.assertEqual(record["Pellet_Fe_pct"], "61.08")
        self.assertEqual(record["Pellet_SiO2_pct"], "6.57")
        self.assertEqual(record["Pellet_plus10mm"], "53.90")
        self.assertEqual(record["Pellet_MSize"], "60.30")
        self.assertEqual(record["Pellet_Basicity"], "0.17")


if __name__ == "__main__":
    raise SystemExit(unittest.main())
