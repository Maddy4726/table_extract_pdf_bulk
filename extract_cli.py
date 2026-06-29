"""Shared command-line helpers for BF-8 extractors."""

from __future__ import annotations

import argparse
import fnmatch
import os
import sys

from pdf_paths import collect_pdf_paths

DEFAULT_PDF_PATTERN = "NEW P.D.*.pdf"


def add_input_args(parser: argparse.ArgumentParser) -> None:
    """Add the standard PDF input arguments used by every extractor."""
    parser.add_argument(
        "--input-dir",
        nargs="+",
        required=True,
        metavar="PATH",
        help="Folder on your PC that contains the daily PDF files.",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search for PDFs in subfolders (use for FY2023-24 / FY2024-25 / FY2025-26).",
    )
    parser.add_argument(
        "--pdf-pattern",
        default=DEFAULT_PDF_PATTERN,
        help=f"Only include PDFs matching this filename pattern (default: {DEFAULT_PDF_PATTERN!r}).",
    )


def add_output_args(parser: argparse.ArgumentParser, default_output: str) -> None:
    """Add output format options."""
    parser.add_argument(
        "--output",
        default=default_output,
        help=f"Output path without extension (default: {default_output}).",
    )
    parser.add_argument(
        "--format",
        choices=("csv", "excel", "both"),
        default="both",
        help="Output format (default: both).",
    )
    parser.add_argument(
        "--keep-zero",
        action="store_true",
        help="Keep literal 0 values instead of converting them to NA.",
    )


def add_verbose_arg(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--verbose", action="store_true", help="Print per-file progress and warnings.")


def resolve_pdf_paths(args: argparse.Namespace) -> list[str]:
    """Collect and filter PDF paths from parsed CLI arguments."""
    pdf_paths = collect_pdf_paths(args.input_dir, recursive=args.recursive)
    pattern = args.pdf_pattern
    if pattern:
        pdf_paths = [
            path for path in pdf_paths if fnmatch.fnmatch(os.path.basename(path), pattern)
        ]

    if not pdf_paths:
        print("No PDF files found.", file=sys.stderr)
        print(f"Checked: {', '.join(args.input_dir)}", file=sys.stderr)
        sys.exit(1)

    if args.verbose:
        print("PDF folders:")
        for folder in args.input_dir:
            print(f"  - {folder}")
        print(f"Found {len(pdf_paths)} PDF(s)")

    return pdf_paths
