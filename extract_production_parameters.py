#!/usr/bin/env python3
"""Extract the complete BF-8 page-1 PARAMETERS table from daily production PDFs.

Reads page 1, walks every row in the main PARAMETERS table, and writes one
row per report day with BF # 8 values for production, fuel, burden, blast,
and all sub-rows (Till, Yearly Rate, etc.).

Usage:
    python extract_production_parameters.py --input-dir . --verbose
    python extract_production_parameters.py --from-config --recursive --verbose
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import sys
from typing import Any

import pandas as pd
import pdfplumber

from drive_paths import load_drive_config, resolve_input_directories
from extract_bf8_daily import (
    _extract_page_tables,
    _find_bf8_column,
    _find_main_table,
    collect_pdf_paths,
)
from extract_table_utils import (
    DEFAULT_PDF_PATTERN,
    assign_report_date,
    finalize_dates,
    write_dataframe,
)

DEFAULT_OUTPUT = "BF8_production_parameters"

INVALID_TOKENS = {"#DIV/0!", "#DIV/0", "STOP", ""}

# Merge alternate PDF labels onto one canonical output column.
COLUMN_ALIASES: dict[str, str] = {
    "Prod_13_a_ironRate": "Prod_13_a_ironOreRate",
    "Prod_19_quartzDolomiteRt": "Prod_19_quartzRt",
    "Prod_01_d_date15042019BenchMarkTonnes1772": "Prod_01_d_dateBenchMarkTonnes",
    "Prod_19_abbc_lDSlagRt": "Prod_19_abc_lDSlagRt",
    "Prod_40_a_oxyEnrch": "Prod_40_a_pctOxyEnrch",
}

TEXT_COLUMN_RE = re.compile(
    r"(tD|oTD|stoppage|lowBlast|redBlast|downTime|productionHrs|dateBenchMark|lastCatRepair)",
    re.IGNORECASE,
)


def _slugify(text: str) -> str:
    text = str(text).replace("%", " pct ")
    text = re.sub(r"[^\w\s]", " ", text)
    words = re.findall(r"[A-Za-z0-9]+", text)
    if not words:
        return "value"
    slug = words[0].lower()
    for word in words[1:]:
        slug += word.capitalize()
    return slug[:60]


def _clean_param(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value).replace("\n", " ")).strip()


def _parse_major(sl_no: str) -> str:
    match = re.match(r"^(\d+)", sl_no.strip())
    return match.group(1) if match else ""


def _clean_value(value: Any) -> Any:
    if value is None:
        return None
    text = str(value).strip()
    if text.upper() in INVALID_TOKENS:
        return None
    return text


def _canonical_column(key: str) -> str:
    return COLUMN_ALIASES.get(key, key)


def _is_text_column(column: str) -> bool:
    return bool(TEXT_COLUMN_RE.search(column))


def _build_row_key(major: str, sl_no: str, param: str, last_base: str) -> tuple[str, str]:
    """Return (column_key, last_base_for_till_rows)."""
    param_upper = param.upper()

    if param_upper == "TILL":
        return f"{last_base}_till", last_base

    if param_upper == "YEARLY RATE" or (
        param_upper.startswith("YEARLY") and "RATE" in param_upper and "TILL" not in param_upper
    ):
        return f"{last_base}_yearlyRate", last_base

    if param_upper.startswith("TILL ") and param_upper not in {"TILL PELLET %"}:
        major_part = f"{int(major):02d}" if major else "x"
        return f"Prod_{major_part}_{_slugify(param)}", last_base

    sl_clean = re.sub(r"[^a-zA-Z0-9]+", "", sl_no).lower() if sl_no else ""
    parts = ["Prod", f"{int(major):02d}" if major else "x"]
    if sl_clean and sl_clean != major:
        parts.append(sl_clean)
    parts.append(_slugify(param))
    key = "_".join(parts)
    return key, key


def _extract_parameter_rows(
    main_table: list[list[Any]],
    header_row: list[Any],
) -> dict[str, Any]:
    bf8_col = _find_bf8_column(header_row)
    if bf8_col < 0:
        return {}

    started = False
    major = ""
    last_base = ""
    record: dict[str, Any] = {}

    for row in main_table:
        row_text = " ".join(str(cell) for cell in row if cell)
        if "PARAMETERS" in row_text.upper() and "SL.NO" in row_text.upper():
            started = True
            continue
        if not started:
            continue

        sl_no = str(row[1] or "").strip()
        param = _clean_param(row[2] or "")

        if not param:
            if sl_no == "(e)":
                value = _clean_value(row[bf8_col] if bf8_col < len(row) else None)
                if value is not None:
                    key = f"Prod_{int(major):02d}_e_benchMark" if major else "Prod_e_benchMark"
                    record[_canonical_column(key)] = value
            continue

        if param.upper() == "PARAMETERS":
            continue

        major_match = _parse_major(sl_no)
        if major_match:
            major = major_match

        key, last_base = _build_row_key(major, sl_no, param, last_base)
        key = _canonical_column(key)
        value = _clean_value(row[bf8_col] if bf8_col < len(row) else None)
        if value is None:
            continue
        record[key] = value

    return record


def _extract_from_page_text(page_text: str) -> dict[str, Any]:
    """Lightweight text fallback for a few critical rows when table cells are empty."""
    record: dict[str, Any] = {}
    if not page_text:
        return record

    patterns = {
        "Prod_01_production": r"^\s*1\s+PRODUCTION\s+TONNES\s+(?:\S+\s+){4}(\S+)",
        "Prod_07_a_cokeRt": r"\(a\)\s+COKE\s+Rt\.\s+Kg/THM\s+(?:\S+\s+){4}(\S+)",
        "Prod_11_11a_fuelRate": r"11\s*\(a\)\s+FUEL\s+RATE\s+Kg/THM\s+(?:\S+\s+){4}(\S+)",
        "Prod_12_a_slagRate": r"\(a\)\s+SLAG\s+RATE\s+Kg/THM\s+(?:\S+\s+){4}(\S+)",
        "Prod_13_a_ironOreRate": r"\(a\)\s+IRON(?:\s+ORE)?\s+RATE\s+Kg/THM\s+(?:\S+\s+){4}(\S+)",
    }

    for line in page_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        for column, pattern in patterns.items():
            if column in record:
                continue
            match = re.search(pattern, stripped, re.IGNORECASE)
            if match:
                record[column] = match.group(1)

    return record


def _merge_records(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    merged = dict(primary)
    for key, value in secondary.items():
        if merged.get(key) is None and value is not None:
            merged[key] = value
    return merged


def extract_production_parameters(pdf_path: str, verbose: bool = False) -> dict[str, Any]:
    """Extract the full BF-8 PARAMETERS table for one PDF."""
    record: dict[str, Any] = {
        "report_date": None,
        "date": None,
        "source_file": os.path.basename(pdf_path),
    }

    try:
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages:
                if verbose:
                    print(f"WARNING: no pages in {pdf_path}", file=sys.stderr)
                return record

            page1_text = pdf.pages[0].extract_text() or ""
            tables = _extract_page_tables(pdf.pages[0])
    except Exception as exc:
        if verbose:
            print(f"WARNING: failed to open {pdf_path}: {exc}", file=sys.stderr)
        return record

    assign_report_date(record, page1_text, pdf_path)

    main_table, header_row = _find_main_table(tables)
    if main_table is None or header_row is None:
        if verbose:
            print(f"WARNING: PARAMETERS table not found in {pdf_path}", file=sys.stderr)
        record.update(_extract_from_page_text(page1_text))
        return record

    table_values = _extract_parameter_rows(main_table, header_row)
    text_values = _extract_from_page_text(page1_text)
    record.update(_merge_records(table_values, text_values))

    filled = sum(1 for key, value in record.items() if key.startswith("Prod_") and value is not None)
    if verbose:
        print(
            f"  {os.path.basename(pdf_path)}: {filled} parameter value(s) extracted",
            file=sys.stderr,
        )

    return record


def stitch_production_parameters(
    pdf_paths: list[str],
    output_path: str,
    output_format: str = "both",
    replace_zero_with_na: bool = True,
    verbose: bool = False,
) -> pd.DataFrame:
    records = [extract_production_parameters(path, verbose=verbose) for path in pdf_paths]

    value_columns = sorted(
        {
            key
            for record in records
            for key in record
            if key.startswith("Prod_")
        }
    )

    df = pd.DataFrame(records)
    for column in value_columns:
        if column not in df.columns:
            df[column] = pd.NA

    for column in value_columns:
        if _is_text_column(column):
            continue
        df[column] = pd.to_numeric(df[column], errors="coerce")

    df = finalize_dates(df, pdf_paths)
    df = df.sort_values("date").reset_index(drop=True)

    if replace_zero_with_na:
        numeric_cols = [col for col in value_columns if not _is_text_column(col)]
        df[numeric_cols] = df[numeric_cols].replace(0, pd.NA)

    write_dataframe(df, output_path, output_format=output_format, verbose=verbose)
    return df


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract the complete BF-8 page-1 PARAMETERS table into a day-by-day CSV/Excel file."
    )
    parser.add_argument("--input-dir", nargs="+", default=None, help="Folder(s) with daily PDFs.")
    parser.add_argument("--from-config", action="store_true", help="Use pdf_root from drive_config.json.")
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help=f"Output path without extension (default: {DEFAULT_OUTPUT}).",
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
    parser.add_argument("--verbose", action="store_true", help="Print per-file progress and warnings.")
    parser.add_argument(
        "--keep-zero",
        action="store_true",
        help="Keep literal 0 values instead of converting them to NA.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = load_drive_config()
    use_config = args.from_config or args.input_dir is None

    try:
        input_dirs = resolve_input_directories(
            input_dirs=args.input_dir,
            from_config=use_config,
            config=config,
        )
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    if not input_dirs and args.input_dir:
        input_dirs = args.input_dir

    pdf_paths = collect_pdf_paths(input_dirs, recursive=args.recursive)
    pdf_pattern = args.pdf_pattern
    if pdf_pattern is None and args.input_dir is not None and not use_config:
        pdf_pattern = DEFAULT_PDF_PATTERN
    if pdf_pattern:
        pdf_paths = [path for path in pdf_paths if fnmatch.fnmatch(os.path.basename(path), pdf_pattern)]

    if not pdf_paths:
        print("No PDF files found.", file=sys.stderr)
        return 1

    if use_config and args.verbose:
        print("PDF folders:")
        for folder in input_dirs:
            print(f"  - {folder}")

    print(f"Extracting production parameters from {len(pdf_paths)} PDF(s)...")
    df = stitch_production_parameters(
        pdf_paths,
        args.output,
        output_format=args.format,
        replace_zero_with_na=not args.keep_zero,
        verbose=args.verbose,
    )

    value_columns = [col for col in df.columns if col.startswith("Prod_")]
    filled = df[value_columns].notna().sum().sum()
    total = len(df) * len(value_columns)
    print(
        f"Saved {len(df)} day(s) x {len(df.columns)} columns "
        f"({filled}/{total} values filled, {100 * filled / total:.1f}%)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
