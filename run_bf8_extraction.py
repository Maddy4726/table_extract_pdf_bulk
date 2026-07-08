#!/usr/bin/env python3
"""Run the full BF-8 PDF extraction pipeline and build a merged master dataset.

Runs every table-by-table extractor (production parameters, hot metal/slag,
skip materials, coke quality, sinter plant) and optionally merges them into
one day-by-day file for data-science work.

Usage:
    python run_bf8_extraction.py --input-dir . --verbose
    python run_bf8_extraction.py --from-config --recursive --verbose
    python run_bf8_extraction.py --only production_parameters hot_metal_slag
    python run_bf8_extraction.py --input-dir . --no-individual --output BF8_master_dataset
"""

from __future__ import annotations

import argparse
import os
import sys

from bf8_pipeline import (
    DEFAULT_EXTRACTOR_KEYS,
    DEFAULT_MASTER_OUTPUT,
    EXTRACTOR_BY_KEY,
    EXTRACTORS,
    merge_extractor_dataframes,
    resolve_pdf_inputs,
    run_all_extractors,
    write_master_dataset,
)
from drive_paths import load_drive_config
from extract_table_utils import DEFAULT_PDF_PATTERN


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run all BF-8 table extractors and optionally merge them into one master dataset."
        )
    )
    parser.add_argument(
        "--input-dir",
        nargs="+",
        default=None,
        help="Folder(s) containing daily PDF reports (overrides config).",
    )
    parser.add_argument(
        "--from-config",
        action="store_true",
        help="Read PDF folders from pdf_root in drive_config.json.",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_MASTER_OUTPUT,
        help=f"Master output path without extension (default: {DEFAULT_MASTER_OUTPUT}).",
    )
    parser.add_argument(
        "--output-dir",
        default=".",
        help="Directory for per-table outputs (default: current directory).",
    )
    parser.add_argument(
        "--only",
        nargs="+",
        choices=sorted(EXTRACTOR_BY_KEY),
        metavar="EXTRACTOR",
        help="Run only the listed extractors.",
    )
    parser.add_argument(
        "--no-merge",
        action="store_true",
        help="Write per-table files only; skip the merged master dataset.",
    )
    parser.add_argument(
        "--no-individual",
        action="store_true",
        help="Skip per-table CSV/Excel files; only write the merged master dataset.",
    )
    parser.add_argument(
        "--format",
        choices=("csv", "excel", "both"),
        default="both",
        help="Output format (default: both).",
    )
    parser.add_argument(
        "--pdf-pattern",
        default=None,
        help=f"Filename glob when using --input-dir (default: {DEFAULT_PDF_PATTERN!r}).",
    )
    parser.add_argument("--recursive", action="store_true", help="Search PDFs recursively.")
    parser.add_argument("--verbose", action="store_true", help="Print per-file progress.")
    parser.add_argument(
        "--keep-zero",
        action="store_true",
        help="Keep literal 0 values instead of converting them to NA.",
    )
    parser.add_argument(
        "--list-extractors",
        action="store_true",
        help="List available extractors and exit.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if args.list_extractors:
        print("Available extractors:")
        for spec in EXTRACTORS:
            print(f"  {spec.key:24}  {spec.label}  -> {spec.default_output}")
        return 0

    config = load_drive_config()
    use_config = args.from_config or args.input_dir is None

    try:
        input_dirs, pdf_paths = resolve_pdf_inputs(
            input_dirs=args.input_dir,
            from_config=use_config,
            recursive=args.recursive,
            pdf_pattern=args.pdf_pattern,
            config=config,
        )
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    if not input_dirs and not pdf_paths:
        print(
            "No input folders specified. Use --input-dir or set pdf_root in drive_config.json.",
            file=sys.stderr,
        )
        return 1

    if not pdf_paths:
        print("No PDF files found.", file=sys.stderr)
        return 1

    if use_config and args.verbose:
        print("PDF folders:")
        for folder in input_dirs:
            print(f"  - {folder}")

    extractor_keys = args.only or list(DEFAULT_EXTRACTOR_KEYS)
    write_individual = not args.no_individual
    write_merge = not args.no_merge

    print(
        f"Running {len(extractor_keys)} extractor(s) on {len(pdf_paths)} PDF(s)..."
    )
    results = run_all_extractors(
        pdf_paths,
        extractor_keys=extractor_keys,
        output_dir=args.output_dir,
        output_format=args.format,
        write_individual=write_individual,
        replace_zero_with_na=not args.keep_zero,
        verbose=args.verbose,
    )

    for key, df in results.items():
        spec = EXTRACTOR_BY_KEY[key]
        print(f"  {spec.key}: {len(df)} day(s) x {len(df.columns)} columns")

    if not write_merge:
        return 0

    master = merge_extractor_dataframes(list(results.values()))
    master_path = os.path.join(args.output_dir, args.output)
    write_master_dataset(
        master,
        master_path,
        output_format=args.format,
        verbose=args.verbose,
    )
    print(
        f"Master dataset: {len(master)} day(s) x {len(master.columns)} columns "
        f"-> {master_path}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
