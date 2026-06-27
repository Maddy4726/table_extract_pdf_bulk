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
from extract_skip_sinter import extract_skip_sinter
from extract_skip_fines import (
    _extract_from_merged_table,
    _extract_from_page_text as _extract_skip_fines_text,
    _find_fines_tables,
    extract_skip_fines,
)
from extract_coke_quality import extract_coke_quality
from extract_sinter_plant import extract_sinter_plant
from extract_production_parameters import extract_production_parameters


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

    def test_skip_sinter_extraction(self) -> None:
        sample = "/workspace/sample_report.pdf"
        if not os.path.exists(sample):
            self.skipTest("sample_report.pdf not available")

        record = extract_skip_sinter(sample)
        self.assertEqual(record["SkipSinter_Fe_pct"], "50.35")
        self.assertEqual(record["SkipSinter_SiO2_pct"], "7.84")
        self.assertEqual(record["SkipSinter_CaO_pct"], "14.93")
        self.assertEqual(record["SkipSinter_Basicity"], "1.90")

    def test_skip_fines_merged_table(self) -> None:
        sample = "/workspace/NEW P.D.14.01-01.pdf"
        if not os.path.exists(sample):
            self.skipTest("NEW P.D.14.01-01.pdf not available")

        record = extract_skip_fines(sample)
        self.assertEqual(record["SkipSinterFines_minus10mm"], "30.03")
        self.assertEqual(record["SkipSinterFines_ShiftA"], "49.80")
        self.assertEqual(record["SkipCokeFines_minus40mm"], "41.83")
        self.assertEqual(record["SkipCokeFines_MSize"], "43.17")

    def test_skip_fines_split_tables(self) -> None:
        sample = "/workspace/NEW P.D.14.01-04.pdf"
        if not os.path.exists(sample):
            self.skipTest("NEW P.D.14.01-04.pdf not available")

        record = extract_skip_fines(sample)
        self.assertEqual(record["SkipSinterFines_minus10mm"], "36.70")
        self.assertEqual(record["SkipSinterFines_minus5mm"], "10.00")
        self.assertEqual(record["SkipCokeFines_minus40mm"], "41.30")
        self.assertEqual(record["SkipCokeFines_minus25mm"], "1.30")

    def test_skip_fines_wide_table(self) -> None:
        sample = "/workspace/sample_report.pdf"
        if not os.path.exists(sample):
            self.skipTest("sample_report.pdf not available")

        record = extract_skip_fines(sample)
        self.assertEqual(record["SkipSinterFines_minus10mm"], "27.10")
        self.assertEqual(record["SkipSinterFines_MSize"], "16.00")
        self.assertEqual(record["SkipCokeFines_minus40mm"], "44.25")
        self.assertEqual(record["SkipCokeFines_MSize"], "42.60")
        self.assertIsNone(record["SkipSinterFines_ShiftA"])

    def test_skip_fines_text_total_fe_layout(self) -> None:
        page_text = """
        % FINES IN BF SKIP SINTER
        Fce.No. -10 mm - 5 mm M.Size TOTAL Fe
        BF # 8 30.10 4.20 15.30 49.60
        COKE QUALITY
        """
        record = _extract_skip_fines_text(page_text)
        self.assertEqual(record["SkipSinterFines_minus10mm"], "30.10")
        self.assertEqual(record["SkipSinterFines_TotalFe"], "49.60")
        self.assertIsNone(record["SkipSinterFines_ShiftA"])

    def test_skip_fines_split_table_helpers(self) -> None:
        sinter_table = [
            ["Fce.No.", "-10 mm", "- 5 mm", "M.Size", "TOTAL Fe"],
            ["BF # 8", "30.10", "4.20", "15.30", "49.60"],
        ]
        coke_table = [
            ["Fce.No.", "-40 mm", "- 25 mm", "M.Size"],
            ["BF # 8", "41.00", "2.00", "43.00"],
        ]
        sinter_values, coke_values = _find_fines_tables([sinter_table, coke_table])
        self.assertEqual(sinter_values["SkipSinterFines_TotalFe"], "49.60")
        self.assertEqual(coke_values["SkipCokeFines_minus40mm"], "41.00")

    def test_skip_fines_wide_table_helpers(self) -> None:
        header = [
            "Fce.No.",
            "-10 mm",
            "- 5 mm",
            "M.Size",
            "+40 mm",
            "- 10 mm",
            "M.Size",
            "-40 mm",
            "- 25 mm",
            "M.Size",
        ]
        data = ["BF # 8", "27.10", "4.35", "16.00", "13.90", "11.10", "25.90", "44.25", "2.35", "42.60"]
        record = _extract_from_merged_table(header, data)
        self.assertEqual(record["SkipSinterFines_minus10mm"], "27.10")
        self.assertEqual(record["SkipCokeFines_minus40mm"], "44.25")
        self.assertIsNone(record["SkipSinterFines_ShiftA"])

    def test_skip_fines_2023_format_pdf(self) -> None:
        sample = "/home/ubuntu/.cursor/projects/workspace/uploads/NEW_P.D.14.17-06_570f.pdf"
        if not os.path.exists(sample):
            self.skipTest("NEW_P.D.14.17-06 sample not available")

        record = extract_skip_fines(sample)
        self.assertEqual(record["SkipSinterFines_minus10mm"], "29.9")
        self.assertEqual(record["SkipSinterFines_TotalFe"], "49.69")
        self.assertIsNone(record["SkipSinterFines_ShiftA"])
        self.assertEqual(record["SkipCokeFines_minus40mm"], "41.60")

    def test_coke_quality_extraction(self) -> None:
        sample = "/workspace/NEW P.D.14.01-01.pdf"
        if not os.path.exists(sample):
            self.skipTest("NEW P.D.14.01-01.pdf not available")

        record = extract_coke_quality(sample)
        self.assertEqual(record["CokeQuality_CSP1_Moisture"], "3.8")
        self.assertEqual(record["CokeQuality_CSP1_Ash"], "15.2")
        self.assertEqual(record["CokeQuality_CSP2_CSR"], "64.1")
        self.assertEqual(record["CokeQuality_CSP2_CRI"], "23.8")
        self.assertEqual(record["CokeQuality_BF8_Mix_CSR"], "65.6")
        self.assertEqual(record["CokeQuality_BF8_Mix_CRI"], "23.5")

    def test_coke_quality_wide_merged_table(self) -> None:
        sample = "/workspace/sample_report.pdf"
        if not os.path.exists(sample):
            self.skipTest("sample_report.pdf not available")

        record = extract_coke_quality(sample)
        self.assertEqual(record["CokeQuality_CSP3_CSR"], "64.6")
        self.assertEqual(record["CokeQuality_CSP3_CRI"], "23.1")
        self.assertEqual(record["CokeQuality_CSP1_M40"], "76.1")

    def test_coke_quality_sparse_2023_format(self) -> None:
        sample = "/home/ubuntu/.cursor/projects/workspace/uploads/NEW_P.D.14.17-06_570f.pdf"
        if not os.path.exists(sample):
            self.skipTest("NEW_P.D.14.17-06 sample not available")

        record = extract_coke_quality(sample)
        self.assertEqual(record["CokeQuality_CSP1_Sulphur"], "0.8")
        self.assertIsNone(record["CokeQuality_CSP1_M40"])
        self.assertEqual(record["CokeQuality_CSP3_M40"], "81.8")
        self.assertEqual(record["CokeQuality_CSP4_M10"], "5.6")

    def test_sinter_plant_extraction(self) -> None:
        sample = "/workspace/NEW P.D.14.01-01.pdf"
        if not os.path.exists(sample):
            self.skipTest("NEW P.D.14.01-01.pdf not available")

        record = extract_sinter_plant(sample)
        self.assertEqual(record["SinterPlant2_DayAvg_Fe_pct"], "49.88")
        self.assertEqual(record["SinterPlant2_DayAvg_Basicity"], "1.83")
        self.assertEqual(record["SinterPlant3_DayAvg_Fe_pct"], "50.92")
        self.assertEqual(record["SinterPlant3_AO_Fe_pct"], "51.73")
        self.assertEqual(record["SinterPlant2_A1_Fe_pct"], "49.72")

    def test_sinter_plant_split_pdf(self) -> None:
        sample = "/workspace/NEW P.D.14.01-04.pdf"
        if not os.path.exists(sample):
            self.skipTest("NEW P.D.14.01-04.pdf not available")

        record = extract_sinter_plant(sample)
        self.assertEqual(record["SinterPlant2_DayAvg_Fe_pct"], "51.36")
        self.assertEqual(record["SinterPlant3_DayAvg_Fe_pct"], "53.24")
        self.assertEqual(record["SinterPlant3_BO_Fe_pct"], "54.58")

    def test_sinter_plant_2023_format(self) -> None:
        sample = "/home/ubuntu/.cursor/projects/workspace/uploads/NEW_P.D.14.17-06_570f.pdf"
        if not os.path.exists(sample):
            self.skipTest("NEW_P.D.14.17-06 sample not available")

        record = extract_sinter_plant(sample)
        self.assertEqual(record["SinterPlant2_DayAvg_Fe_pct"], "48.11")
        self.assertEqual(record["SinterPlant3_DayAvg_Fe_pct"], "48.84")
        self.assertIsNone(record["SinterPlant2_C1_Fe_pct"])

    def test_production_parameters_complete_extraction(self) -> None:
        sample = "/workspace/NEW P.D.14.01-01.pdf"
        if not os.path.exists(sample):
            self.skipTest("NEW P.D.14.01-01.pdf not available")

        record = extract_production_parameters(sample)
        self.assertEqual(record["Prod_01_production"], "8021")
        self.assertEqual(record["Prod_07_a_cokeRt"], "385")
        self.assertEqual(record["Prod_11_11a_fuelRate"], "562")
        self.assertEqual(record["Prod_12_a_slagRate"], "545")
        self.assertEqual(record["Prod_13_a_ironOreRate"], "176")
        self.assertEqual(record["Prod_32_tD"], "36:40:00")
        self.assertEqual(record["Prod_07_a_cokeRt_till"], "385")
        self.assertGreater(
            sum(1 for key, value in record.items() if key.startswith("Prod_") and value is not None),
            90,
        )

    def test_production_parameters_2023_format(self) -> None:
        sample = "/home/ubuntu/.cursor/projects/workspace/uploads/NEW_P.D.14.17-06_570f.pdf"
        if not os.path.exists(sample):
            self.skipTest("NEW_P.D.14.17-06 sample not available")

        record = extract_production_parameters(sample)
        self.assertIsNotNone(record.get("Prod_01_production"))
        self.assertIsNotNone(record.get("Prod_07_a_cokeRt"))
        self.assertIsNotNone(record.get("Prod_13_a_ironOreRate"))


if __name__ == "__main__":
    raise SystemExit(unittest.main())
