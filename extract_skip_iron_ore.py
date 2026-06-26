#!/usr/bin/env python3
"""Extract BF-8 skip iron ore analysis from daily production report PDFs.

Reads page 2, locates the SKIP IRON ORE chemical and sieve tables, and writes
one row per report day for BF # 8.

Usage:
    python extract_skip_iron_ore.py --input-dir . --verbose
    python extract_skip_iron_ore.py --from-config --recursive --verbose
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
    _find_bf8_row,
    _normalize_label,
    _value_from_header_aliases,
    collect_pdf_paths,
)
from extract_table_utils import (
    DEFAULT_PDF_PATTERN,
    assign_report_date,
    stitch_records,
)

DEFAULT_OUTPUT = "BF8_skip_iron_ore"

CHEM_COLUMNS: list[tuple[str, str]] = [
    ("Fe (%)", "SkipIronOre_Fe_pct"),
    ("SiO2 (%)", "SkipIronOre_SiO2_pct"),
    ("Al2O3(%)", "SkipIronOre_Al2O3_pct"),
    ("Moist.", "SkipIronOre_Moist_pct"),
]

SIEVE_COLUMNS: list[tuple[str, str]] = [
    ("+40 mm", "SkipIronOre_plus40mm"),
    ("- 10 mm", "SkipIronOre_minus10mm"),
    ("M.Size", "SkipIronOre_MSize"),
]

CHEM_HEADER_ALIASES: dict[str, list[str]] = {
    "Fe (%)": ["Fe (%)", "Fe(%)"],
    "SiO2 (%)": ["SiO2 (%)", "SiO2(%)"],
    "Al2O3(%)": ["Al2O3(%)", "Al2O3 (%)"],
    "Moist.": ["Moist.", "Moist"],
}

SIEVE_HEADER_ALIASES: dict[str, list[str]] = {
    "+40 mm": ["+40 mm", "+ 40 mm", "+40MM"],
    "- 10 mm": ["- 10 mm", "-10 mm", "- 10MM"],
    "M.Size": ["M.Size", "M. SIZE", "M.SIZE"],
}

NUMERIC_COLUMNS = [col for _, col in CHEM_COLUMNS + SIEVE_COLUMNS]

VALUE_RANGES: dict[str, tuple[float, float]] = {
    "SkipIronOre_Fe_pct": (55.0, 70.0),
    "SkipIronOre_SiO2_pct": (1.0, 15.0),
    "SkipIronOre_Al2O3_pct": (1.0, 10.0),
    "SkipIronOre_Moist_pct": (0.0, 15.0),
    "SkipIronOre_plus40mm": (5.0, 50.0),
    "SkipIronOre_minus10mm": (3.0, 30.0),
    "SkipIronOre_MSize": (15.0, 45.0),
}


def _empty_record(pdf_path: str) -> dict[str, Any]:
    record: dict[str, Any] = {
        "report_date": None,
        "date": None,
        "source_file": os.path.basename(pdf_path),
    }
    for col in NUMERIC_COLUMNS:
        record[col] = None
    return record


def _row_text(row: list[Any] | None) -> str:
    if not row:
        return ""
    return " ".join(str(cell) for cell in row if cell is not None and str(cell).strip())


def _is_skip_iron_ore_chem_header(row: list[Any]) -> bool:
    normalized = _normalize_label(_row_text(row))
    if not normalized:
        return False
    if "BASICITY" in normalized or "CAO" in normalized or "MGO" in normalized:
        return False
    if "SHIFT" in normalized or "FCE" in normalized:
        return False
    return "FE" in normalized and "SIO2" in normalized and "AL2O3" in normalized


def _is_skip_iron_ore_sieve_header(row: list[Any]) -> bool:
    normalized = _normalize_label(_row_text(row))
    if not normalized:
        return False
    if "SHIFT" in normalized or "- 5" in normalized or "-5" in normalized:
        return False
    return "FCE" in normalized and "+40" in normalized and ("- 10" in normalized or "-10" in normalized)


def _find_skip_iron_ore_chem_table(
    tables: list[list[list[Any]]],
) -> tuple[list[Any] | None, list[Any] | None]:
    for table in tables:
        header_row = next((row for row in table if _is_skip_iron_ore_chem_header(row)), None)
        data_row = _find_bf8_row(table)
        if header_row and data_row:
            return header_row, data_row
    return None, None


def _find_skip_iron_ore_sieve_table(
    tables: list[list[list[Any]]],
) -> tuple[list[Any] | None, list[Any] | None]:
    for table in tables:
        header_row = next((row for row in table if _is_skip_iron_ore_sieve_header(row)), None)
        data_row = _find_bf8_row(table)
        if header_row and data_row:
            return header_row, data_row
    return None, None


def _extract_mapped_values(
    header_row: list[Any] | None,
    data_row: list[Any] | None,
    column_map: list[tuple[str, str]],
    header_aliases: dict[str, list[str]],
) -> dict[str, Any]:
    record: dict[str, Any] = {col: None for _, col in column_map}
    if not header_row or not data_row:
        return record

    for header_label, out_col in column_map:
        aliases = header_aliases.get(header_label, [header_label])
        value = _value_from_header_aliases(header_row, data_row, aliases)
        if value is not None and str(value).strip() == "":
            value = None
        record[out_col] = value
    return record


def _is_plausible(col: str, value: Any) -> bool:
    if value is None:
        return True
    bounds = VALUE_RANGES.get(col)
    if not bounds:
        return True
    try:
        number = float(value)
    except (TypeError, ValueError):
        return False
    low, high = bounds
    return low <= number <= high


def _sanitize_record(record: dict[str, Any], text_values: dict[str, Any]) -> None:
    for col in NUMERIC_COLUMNS:
        value = record.get(col)
        if value is None or _is_plausible(col, value):
            continue
        fallback = text_values.get(col)
        if fallback is not None and _is_plausible(col, fallback):
            record[col] = fallback
        else:
            record[col] = None


def _bf8_line_numbers(line: str) -> list[str]:
    if not re.search(r"BF\s*#\s*8\b", line, re.IGNORECASE):
        return []
    after_label = re.sub(r"^.*BF\s*#\s*8\s*=>?\s*", "", line, count=1, flags=re.IGNORECASE)
    return re.findall(r"-?\d+(?:\.\d+)?", after_label)


def _extract_from_page_text(page_text: str) -> dict[str, Any]:
    record: dict[str, Any] = {col: None for col in NUMERIC_COLUMNS}
    if not page_text:
        return record

    in_section = False
    chem_seen = False

    for line in page_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        upper = stripped.upper()

        if "SKIP IRON ORE" in upper or "SKIP I/ORE" in upper:
            in_section = True
            chem_seen = False
            continue

        if in_section and ("% FINES IN BF SKIP SINTER" in upper or "PELLET CHEMICAL" in upper):
            break

        if not in_section:
            continue

        if not re.search(r"BF\s*#\s*8\b", stripped, re.IGNORECASE):
            continue

        numbers = _bf8_line_numbers(stripped)
        if not numbers:
            continue

        if not chem_seen and len(numbers) >= 3:
            record["SkipIronOre_Fe_pct"] = numbers[0]
            record["SkipIronOre_SiO2_pct"] = numbers[1]
            record["SkipIronOre_Al2O3_pct"] = numbers[2]
            if len(numbers) >= 4:
                record["SkipIronOre_Moist_pct"] = numbers[3]
            chem_seen = True
            continue

        if chem_seen and len(numbers) >= 3:
            record["SkipIronOre_plus40mm"] = numbers[0]
            record["SkipIronOre_minus10mm"] = numbers[1]
            record["SkipIronOre_MSize"] = numbers[2]

    return record


def extract_skip_iron_ore(pdf_path: str, verbose: bool = False) -> dict[str, Any]:
    """Extract BF-8 skip iron ore chemical and sieve values for one PDF."""
    record = _empty_record(pdf_path)

    try:
        with pdfplumber.open(pdf_path) as pdf:
            if len(pdf.pages) < 2:
                if verbose:
                    print(f"WARNING: page 2 missing in {pdf_path}", file=sys.stderr)
                return record

            page1_text = pdf.pages[0].extract_text() or ""
            page = pdf.pages[1]
            page_text = page.extract_text() or ""
            tables = _extract_page_tables(page)
    except Exception as exc:
        if verbose:
            print(f"WARNING: failed to open {pdf_path}: {exc}", file=sys.stderr)
        return record

    assign_report_date(record, page1_text, pdf_path)

    chem_header, chem_row = _find_skip_iron_ore_chem_table(tables)
    if chem_header and chem_row:
        record.update(_extract_mapped_values(chem_header, chem_row, CHEM_COLUMNS, CHEM_HEADER_ALIASES))
    elif verbose:
        print(f"WARNING: skip iron ore chemical table not found in {pdf_path}", file=sys.stderr)

    sieve_header, sieve_row = _find_skip_iron_ore_sieve_table(tables)
    if sieve_header and sieve_row:
        record.update(_extract_mapped_values(sieve_header, sieve_row, SIEVE_COLUMNS, SIEVE_HEADER_ALIASES))
    elif verbose:
        print(f"WARNING: skip iron ore sieve table not found in {pdf_path}", file=sys.stderr)

    text_values = _extract_from_page_text(page_text)
    for col, value in text_values.items():
        if record.get(col) is None and value is not None:
            record[col] = value

    _sanitize_record(record, text_values)

    missing = [col for col in NUMERIC_COLUMNS if record.get(col) is None]
    if missing and verbose:
        print(
            f"WARNING: {os.path.basename(pdf_path)} missing {len(missing)} field(s): "
            + ", ".join(missing),
            file=sys.stderr,
        )

    return record


def stitch_skip_iron_ore(
    pdf_paths: list[str],
    output_path: str,
    output_format: str = "both",
    replace_zero_with_na: bool = True,
    verbose: bool = False,
) -> pd.DataFrame:
    records = [extract_skip_iron_ore(path, verbose=verbose) for path in pdf_paths]
    return stitch_records(
        records,
        pdf_paths,
        NUMERIC_COLUMNS,
        output_path,
        output_format=output_format,
        replace_zero_with_na=replace_zero_with_na,
        verbose=verbose,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract BF-8 skip iron ore analysis into a day-by-day CSV/Excel file."
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

    print(f"Extracting skip iron ore analysis from {len(pdf_paths)} PDF(s)...")
    df = stitch_skip_iron_ore(
        pdf_paths,
        args.output,
        output_format=args.format,
        replace_zero_with_na=not args.keep_zero,
        verbose=args.verbose,
    )

    filled = df[NUMERIC_COLUMNS].notna().sum().sum()
    total = len(df) * len(NUMERIC_COLUMNS)
    print(
        f"Saved {len(df)} day(s) x {len(df.columns)} columns "
        f"({filled}/{total} values filled, {100 * filled / total:.1f}%)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
