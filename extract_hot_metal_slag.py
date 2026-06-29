#!/usr/bin/env python3
"""Extract BF-8 hot metal and slag quality from daily production report PDFs.

Reads page 2, locates the HOT METAL AND SLAG QUALITY table, and writes one
row per report day with BF-8 averages plus min/max ranges where reported.

Usage:
    python extract_hot_metal_slag.py --input-dir "F:\\...\\DailyProdReports_FY2024-25" --verbose
    python extract_hot_metal_slag.py --input-dir ./pdfs --recursive --output BF8_hot_metal_slag
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Any

import pandas as pd
import pdfplumber

from extract_bf8_daily import (
    _extract_page_tables,
    _find_bf8_column,
    _find_quality_table,
    _normalize_label,
)
from extract_cli import add_input_args, add_output_args, add_verbose_arg, resolve_pdf_paths
from extract_table_utils import (
    DEFAULT_PDF_PATTERN,
    assign_report_date,
    stitch_records,
)
DEFAULT_OUTPUT = "BF8_hot_metal_slag"

# Parameter label in PDF -> output column stem (avg/min/max/till appended).
METRIC_ROWS: list[tuple[str, str, bool]] = [
    ("Avg. % 'Si'", "HM_Si_pct", True),
    ("Avg. % 'S'", "HM_S_pct", True),
    ("Avg. % MgO", "Slag_MgO_pct", True),
    ("Avg. % Al2O3", "Slag_Al2O3_pct", False),
    ("Avg. % FeO", "Slag_FeO_pct", False),
    ("Avg. % K2O", "Slag_K2O_pct", False),
    ("BASICITY(-)", "Slag_Basicity", True),
    ("Avg. % 'P'", "HM_P_pct", True),
]

EXTRA_ROWS: list[tuple[str, str]] = [
    ("Till % 'Si'", "HM_Si_pct_till"),
]

NUMERIC_COLUMNS = [
    f"{stem}_{suffix}"
    for label, stem, has_minmax in METRIC_ROWS
    for suffix in (["avg", "min", "max"] if has_minmax else ["avg"])
] + [col for _, col in EXTRA_ROWS]

TEXT_PARAM_ALIASES: dict[str, list[str]] = {
    "Avg. % 'Si'": [r"Avg\.\s*%\s*'Si'", r"Avg\.\s*%\s*Si"],
    "Avg. % 'S'": [r"Avg\.\s*%\s*'S'", r"Avg\.\s*%\s*S"],
    "Avg. % MgO": [r"Avg\.\s*%\s*MgO"],
    "Avg. % Al2O3": [r"Avg\.\s*%\s*Al2O3"],
    "Avg. % FeO": [r"Avg\.\s*%\s*FeO"],
    "Avg. % K2O": [r"Avg\.\s*%\s*K2O"],
    "BASICITY(-)": [r"BASICITY\s*\(-\)", r"BASICITY"],
    "Avg. % 'P'": [r"Avg\.\s*%\s*'P'", r"Avg\.\s*%\s*P"],
    "Till % 'Si'": [r"Till\s*%\s*'Si'", r"Till\s*%\s*Si"],
}

# Plausible BF-8 ranges; values outside these are treated as extraction errors.
VALUE_RANGES: dict[str, tuple[float, float]] = {
    "HM_Si_pct_avg": (0.1, 2.5),
    "HM_Si_pct_min": (0.05, 2.5),
    "HM_Si_pct_max": (0.05, 2.5),
    "HM_Si_pct_till": (0.1, 2.5),
    "HM_S_pct_avg": (0.005, 0.15),
    "HM_S_pct_min": (0.005, 0.15),
    "HM_S_pct_max": (0.005, 0.15),
    "Slag_MgO_pct_avg": (4.0, 12.0),
    "Slag_MgO_pct_min": (4.0, 12.0),
    "Slag_MgO_pct_max": (4.0, 12.0),
    "Slag_Al2O3_pct_avg": (12.0, 25.0),
    "Slag_FeO_pct_avg": (0.2, 2.5),
    "Slag_K2O_pct_avg": (0.1, 1.5),
    "Slag_Basicity_avg": (0.5, 2.5),
    "Slag_Basicity_min": (0.5, 2.5),
    "Slag_Basicity_max": (0.5, 2.5),
    "HM_P_pct_avg": (0.05, 0.25),
    "HM_P_pct_min": (0.05, 0.25),
    "HM_P_pct_max": (0.05, 0.25),
}

DATE_COLUMNS = ("date", "report_date", "year", "month", "day")

# BF-8 is the 5th furnace column in page-2 text lines (BF-4 .. BF-8).
BF8_TEXT_VALUE_INDEX = 4


def _empty_record(pdf_path: str) -> dict[str, Any]:
    record: dict[str, Any] = {
        "report_date": None,
        "date": None,
        "source_file": os.path.basename(pdf_path),
    }
    for col in NUMERIC_COLUMNS:
        record[col] = None
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
    """Drop out-of-range table values and back-fill from text when possible."""
    for col in NUMERIC_COLUMNS:
        value = record.get(col)
        if value is None or _is_plausible(col, value):
            continue
        fallback = text_values.get(col)
        if fallback is not None and _is_plausible(col, fallback):
            record[col] = fallback
        else:
            record[col] = None


def _parse_min_max(value: Any) -> tuple[Any, Any]:
    if value is None:
        return None, None
    text = str(value).strip()
    if not text or "/" not in text:
        return None, None
    left, _, right = text.partition("/")
    left = left.strip()
    right = right.strip().lstrip(".")
    return left or None, right or None


def _cell_value(row: list[Any], col_idx: int) -> Any:
    if col_idx < 0 or col_idx >= len(row):
        return None
    value = row[col_idx]
    if value is None or str(value).strip() == "":
        return None
    return str(value).strip()


def _metric_label_map() -> dict[str, tuple[str, bool]]:
    mapping: dict[str, tuple[str, bool]] = {}
    for label, stem, has_minmax in METRIC_ROWS:
        mapping[_normalize_label(label)] = (stem, has_minmax)
    for label, col in EXTRA_ROWS:
        mapping[_normalize_label(label)] = (col, False)
    return mapping


def _extract_from_quality_table(
    table: list[list[Any]],
    header_row: list[Any],
) -> dict[str, Any]:
    record: dict[str, Any] = {col: None for col in NUMERIC_COLUMNS}
    bf8_col = _find_bf8_column(header_row)
    if bf8_col < 0:
        return record

    label_map = _metric_label_map()
    pending_minmax: str | None = None

    for row in table:
        if not row or not row[0]:
            continue
        label = _normalize_label(row[0])
        value = _cell_value(row, bf8_col)

        if label == "MIN/MAX" and pending_minmax:
            min_val, max_val = _parse_min_max(value)
            record[f"{pending_minmax}_min"] = min_val
            record[f"{pending_minmax}_max"] = max_val
            pending_minmax = None
            continue

        if label not in label_map:
            continue

        stem, has_minmax = label_map[label]
        if stem.endswith("_till"):
            record[stem] = value
            pending_minmax = None
            continue

        record[f"{stem}_avg"] = value
        pending_minmax = stem if has_minmax else None

    return record


def _bf8_value_from_text_line(line: str) -> str | None:
    numbers = re.findall(r"-?\d+(?:\.\d+)?", line)
    if len(numbers) <= BF8_TEXT_VALUE_INDEX:
        return None
    return numbers[BF8_TEXT_VALUE_INDEX]


def _bf8_minmax_from_text_line(line: str) -> tuple[str | None, str | None]:
    pairs = re.findall(r"(\d+(?:\.\d+)?)\s*/\s*(\d+(?:\.\d+)?)", line)
    if len(pairs) <= BF8_TEXT_VALUE_INDEX:
        return None, None
    return pairs[BF8_TEXT_VALUE_INDEX]


def _extract_from_page_text(page_text: str) -> dict[str, Any]:
    record: dict[str, Any] = {col: None for col in NUMERIC_COLUMNS}
    if not page_text:
        return record

    lines = page_text.splitlines()
    pending_minmax: str | None = None

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        upper = stripped.upper()

        if upper.startswith("MIN/MAX"):
            if pending_minmax:
                min_val, max_val = _bf8_minmax_from_text_line(stripped)
                record[f"{pending_minmax}_min"] = min_val
                record[f"{pending_minmax}_max"] = max_val
                pending_minmax = None
            continue

        for label, stem, has_minmax in METRIC_ROWS:
            for pattern in TEXT_PARAM_ALIASES.get(label, [re.escape(label)]):
                if re.search(pattern, stripped, re.IGNORECASE):
                    value = _bf8_value_from_text_line(stripped)
                    record[f"{stem}_avg"] = value
                    pending_minmax = stem if has_minmax else None
                    break
            else:
                continue
            break
        else:
            for label, col in EXTRA_ROWS:
                for pattern in TEXT_PARAM_ALIASES.get(label, [re.escape(label)]):
                    if re.search(pattern, stripped, re.IGNORECASE):
                        record[col] = _bf8_value_from_text_line(stripped)
                        pending_minmax = None
                        break
                else:
                    continue
                break

    return record


def extract_hot_metal_slag(pdf_path: str, verbose: bool = False) -> dict[str, Any]:
    """Extract BF-8 hot metal / slag quality for one PDF."""
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

    quality_table, quality_header = _find_quality_table(tables)
    if quality_table is not None and quality_header is not None:
        record.update(_extract_from_quality_table(quality_table, quality_header))
    elif verbose:
        print(f"WARNING: quality table not found in {pdf_path}; trying text fallback", file=sys.stderr)

    text_values = _extract_from_page_text(page_text)
    for col, value in text_values.items():
        if record.get(col) is None and value is not None:
            record[col] = value

    _sanitize_record(record, text_values)

    missing = [col for col in NUMERIC_COLUMNS if record.get(col) is None]
    if missing and verbose:
        print(
            f"WARNING: {os.path.basename(pdf_path)} missing {len(missing)} field(s): "
            + ", ".join(missing[:5])
            + ("..." if len(missing) > 5 else ""),
            file=sys.stderr,
        )

    return record


def stitch_hot_metal_slag(
    pdf_paths: list[str],
    output_path: str,
    output_format: str = "both",
    replace_zero_with_na: bool = True,
    verbose: bool = False,
) -> pd.DataFrame:
    records = [extract_hot_metal_slag(path, verbose=verbose) for path in pdf_paths]
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
        description="Extract BF-8 hot metal and slag quality into a day-by-day CSV/Excel file."
    )
    add_input_args(parser)
    add_output_args(parser, DEFAULT_OUTPUT)
    add_verbose_arg(parser)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pdf_paths = resolve_pdf_paths(args)

    print(f"Extracting hot metal / slag quality from {len(pdf_paths)} PDF(s)...")
    df = stitch_hot_metal_slag(
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
