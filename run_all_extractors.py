#!/usr/bin/env python3
"""Run every BF-8 table extractor against PDFs in a folder on your PC.

Example:
    python run_all_extractors.py --input-dir "F:\\...\\DailyProdReports_FY2024-25" --verbose
    python run_all_extractors.py --input-dir "F:\\...\\PDF - Daily Production Reports" --recursive --output-dir output
"""

from __future__ import annotations

import argparse
import os
import sys

from extract_cli import add_input_args, add_verbose_arg, resolve_pdf_paths
from extract_coke_quality import stitch_coke_quality
from extract_hot_metal_slag import stitch_hot_metal_slag
from extract_pellet_analysis import stitch_pellet_analysis
from extract_production_parameters import stitch_production_parameters
from extract_sinter_plant import stitch_sinter_plant
from extract_skip_fines import stitch_skip_fines
from extract_skip_iron_ore import stitch_skip_iron_ore
from extract_skip_sinter import stitch_skip_sinter

EXTRACTORS: list[tuple[str, str, object]] = [
    ("Page 1 production parameters", "BF8_production_parameters", stitch_production_parameters),
    ("Hot metal and slag quality", "BF8_hot_metal_slag", stitch_hot_metal_slag),
    ("Skip iron ore", "BF8_skip_iron_ore", stitch_skip_iron_ore),
    ("Pellet analysis", "BF8_pellet_analysis", stitch_pellet_analysis),
    ("Skip sinter chemistry", "BF8_skip_sinter", stitch_skip_sinter),
    ("Skip fines", "BF8_skip_fines", stitch_skip_fines),
    ("Coke quality", "BF8_coke_quality", stitch_coke_quality),
    ("Sinter plant chemistry", "BF8_sinter_plant", stitch_sinter_plant),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run all BF-8 PDF extractors and write one CSV/Excel file per table."
    )
    add_input_args(parser)
    add_verbose_arg(parser)
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Folder for output files (default: output).",
    )
    parser.add_argument(
        "--format",
        choices=("csv", "excel", "both"),
        default="both",
        help="Output format for every table (default: both).",
    )
    parser.add_argument(
        "--keep-zero",
        action="store_true",
        help="Keep literal 0 values instead of converting them to NA.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pdf_paths = resolve_pdf_paths(args)
    os.makedirs(args.output_dir, exist_ok=True)

    print(f"Running {len(EXTRACTORS)} extractor(s) on {len(pdf_paths)} PDF(s)...")
    for label, output_name, stitch_fn in EXTRACTORS:
        output_path = os.path.join(args.output_dir, output_name)
        print(f"\n=== {label} ===")
        stitch_fn(
            pdf_paths,
            output_path,
            output_format=args.format,
            replace_zero_with_na=not args.keep_zero,
            verbose=args.verbose,
        )

    print(f"\nDone. Files saved under: {os.path.abspath(args.output_dir)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
