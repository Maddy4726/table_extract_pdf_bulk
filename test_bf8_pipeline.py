#!/usr/bin/env python3
"""Tests for the unified BF-8 extraction pipeline."""

from __future__ import annotations

import os
import sys
import unittest

import pandas as pd

from bf8_pipeline import (
    EXTRACTOR_BY_KEY,
    merge_extractor_dataframes,
    resolve_pdf_inputs,
    run_all_extractors,
)


class PipelineTests(unittest.TestCase):
    def test_resolve_pdf_inputs_sample_dir(self) -> None:
        _, pdf_paths = resolve_pdf_inputs(input_dirs=["."], recursive=False)
        self.assertGreaterEqual(len(pdf_paths), 1)
        self.assertTrue(all(path.endswith(".pdf") for path in pdf_paths))

    def test_merge_on_date_combines_columns(self) -> None:
        left = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
                "report_date": ["1. Jan. 2024", "2. Jan. 2024"],
                "year": [2024, 2024],
                "month": [1, 1],
                "day": [1, 2],
                "source_file": ["a.pdf", "b.pdf"],
                "Prod_01_production": [4000.0, 4100.0],
            }
        )
        right = pd.DataFrame(
            {
                "date": pd.to_datetime(["2024-01-01", "2024-01-03"]),
                "report_date": ["1. Jan. 2024", "3. Jan. 2024"],
                "year": [2024, 2024],
                "month": [1, 1],
                "day": [1, 3],
                "source_file": ["a.pdf", "c.pdf"],
                "HM_Si_pct_avg": [0.45, 0.50],
            }
        )
        merged = merge_extractor_dataframes([left, right])
        self.assertEqual(len(merged), 3)
        self.assertIn("Prod_01_production", merged.columns)
        self.assertIn("HM_Si_pct_avg", merged.columns)
        self.assertEqual(merged.loc[0, "Prod_01_production"], 4000.0)
        self.assertEqual(merged.loc[0, "HM_Si_pct_avg"], 0.45)

    def test_run_all_extractors_on_sample_pdfs(self) -> None:
        _, pdf_paths = resolve_pdf_inputs(
            input_dirs=["."],
            recursive=False,
            pdf_pattern="NEW P.D.14.01-0*.pdf",
        )
        self.assertGreaterEqual(len(pdf_paths), 2)

        results = run_all_extractors(
            pdf_paths,
            extractor_keys=["production_parameters", "hot_metal_slag"],
            write_individual=False,
            verbose=False,
        )
        self.assertEqual(set(results), {"production_parameters", "hot_metal_slag"})
        self.assertEqual(len(results["production_parameters"]), len(pdf_paths))
        self.assertGreater(
            len([col for col in results["production_parameters"].columns if col.startswith("Prod_")]),
            20,
        )

        master = merge_extractor_dataframes(list(results.values()))
        self.assertEqual(len(master), len(pdf_paths))
        self.assertIn("Prod_01_production", master.columns)
        self.assertIn("HM_Si_pct_avg", master.columns)

    def test_extractor_registry_has_expected_members(self) -> None:
        expected = {
            "production_parameters",
            "hot_metal_slag",
            "skip_iron_ore",
            "pellet_analysis",
            "skip_sinter",
            "skip_fines",
            "coke_quality",
            "sinter_plant",
        }
        self.assertEqual(set(EXTRACTOR_BY_KEY), expected)


if __name__ == "__main__":
    raise SystemExit(unittest.main())
