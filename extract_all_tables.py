#!/usr/bin/env python3
"""Extract every row from every PDF table into a long-format CSV or Excel file.

Each output row is one cell from one table, with metadata for EDA / pivoting:
  date, source_file, page, table_index, table_title, header_row_index,
  row_index, column_index, column_name, value

Usage:
    python extract_all_tables.py --verbose
    python extract_all_tables.py --input-dir . --output bf8_all_rows.csv
    python extract_all_tables.py --output bf8_all_rows.xlsx --format excel
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from typing import Any

import pandas as pd
import pdfplumber

from drive_paths import load_drive_config, resolve_input_directories
from extract_bf8_daily import (
    _extract_date,
    _extract_page_tables,
    collect_pdf_paths,
)

DEFAULT_PDF_PATTERN = "NEW P.D.*.pdf"

HEADER_HINTS = (
    "PARAMETERS",
    "PARAMETER",
    "SL.NO",
    "UNIT",
    "SAMPLE",
    "FCE.NO",
    "FCE",
    "BF #",
    "BF-",
    "% FE",
    "DATE",
    "MIXER",
)


def _sanitize_column_name(value: Any, index: int) -> str:
    if value is None or not str(value).strip():
        return f"col_{index}"
    name = re.sub(r"\s+", " ", str(value).strip())
    name = re.sub(r"[^\w%./+-]+", "_", name)
    name = name.strip("_")
    return name or f"col_{index}"


def _unique_column_names(headers: list[Any]) -> list[str]:
    seen: dict[str, int] = {}
    result: list[str] = []
    for idx, header in enumerate(headers):
        base = _sanitize_column_name(header, idx)
        count = seen.get(base, 0)
        seen[base] = count + 1
        result.append(base if count == 0 else f"{base}_{count}")
    return result


def _row_text(row: list[Any] | None) -> str:
    if not row:
        return ""
    return " ".join(str(cell) for cell in row if cell is not None and str(cell).strip())


def _looks_like_header_row(row: list[Any]) -> bool:
    text = _row_text(row).upper()
    if not text:
        return False
    return any(hint in text for hint in HEADER_HINTS)


def _table_title(table: list[list[Any]], header_idx: int) -> str:
    for row in table[: max(header_idx, 1)]:
        if not row:
            continue
        for cell in row:
            if cell and str(cell).strip():
                title = str(cell).strip().split("\n")[0]
                if len(title) > 3:
                    return title[:120]
    first = _row_text(table[0]) if table else ""
    return first[:120] if first else "table"


def _detect_header_row(table: list[list[Any]]) -> int:
    best_idx = 0
    best_score = -1
    for idx, row in enumerate(table[:8]):
        if not row:
            continue
        filled = sum(1 for cell in row if cell is not None and str(cell).strip())
        score = filled
        if _looks_like_header_row(row):
            score += 10
        if score > best_score:
            best_score = score
            best_idx = idx
    return best_idx


def _extract_table_rows(
    table: list[list[Any]],
    *,
    page_num: int,
    table_index: int,
    date_str: str,
    source_file: str,
) -> list[dict[str, Any]]:
    if not table:
        return []

    header_idx = _detect_header_row(table)
    header_row = table[header_idx] if header_idx < len(table) else []
    column_names = _unique_column_names(header_row)
    title = _table_title(table, header_idx)

    records: list[dict[str, Any]] = []
    for row_idx, row in enumerate(table):
        if row_idx == header_idx:
            continue
        if not row or not any(cell is not None and str(cell).strip() for cell in row):
            continue

        base = {
            "date": date_str,
            "source_file": source_file,
            "page": page_num,
            "table_index": table_index,
            "table_title": title,
            "header_row_index": header_idx,
            "row_index": row_idx,
        }

        # Wide row with named columns (best for pivoting in EDA).
        wide = {**base, "record_type": "wide"}
        for col_idx, cell in enumerate(row):
            col_name = column_names[col_idx] if col_idx < len(column_names) else f"col_{col_idx}"
            value = cell
            if value is not None and str(value).strip() == "":
                value = None
            wide[col_name] = value
        records.append(wide)

        # Long row per non-empty cell (easy filtering in Excel).
        for col_idx, cell in enumerate(row):
            if cell is None or str(cell).strip() == "":
                continue
            col_name = column_names[col_idx] if col_idx < len(column_names) else f"col_{col_idx}"
            records.append(
                {
                    **base,
                    "column_index": col_idx,
                    "column_name": col_name,
                    "value": str(cell).strip(),
                    "record_type": "long",
                }
            )

    return records


def extract_pdf_all_tables(pdf_path: str, verbose: bool = False) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (wide_rows, long_rows) for one PDF."""
    wide_rows: list[dict[str, Any]] = []
    long_rows: list[dict[str, Any]] = []

    try:
        with pdfplumber.open(pdf_path) as pdf:
            page1_text = pdf.pages[0].extract_text() or "" if pdf.pages else ""
            date_str = _extract_date(page1_text, pdf_path)
            source_file = os.path.basename(pdf_path)

            for page_num, page in enumerate(pdf.pages, start=1):
                tables = _extract_page_tables(page)
                for table_index, table in enumerate(tables):
                    extracted = _extract_table_rows(
                        table,
                        page_num=page_num,
                        table_index=table_index,
                        date_str=date_str,
                        source_file=source_file,
                    )
                    for item in extracted:
                        if item.get("record_type") == "long":
                            long_rows.append(item)
                        else:
                            wide_rows.append(item)
    except Exception as exc:
        if verbose:
            print(f"WARNING: failed on {pdf_path}: {exc}", file=sys.stderr)

    return wide_rows, long_rows


def _write_dataframe(
    df: pd.DataFrame,
    output_path: str,
    output_format: str,
    verbose: bool = False,
) -> None:
    base, ext = os.path.splitext(output_path)
    if output_format == "both":
        csv_path = base + ".csv"
        xlsx_path = base + ".xlsx"
        df.to_csv(csv_path, index=False)
        df.to_excel(xlsx_path, index=False)
        if verbose:
            print(f"Saved CSV  -> {csv_path}")
            print(f"Saved Excel -> {xlsx_path}")
    elif output_format == "excel":
        xlsx_path = base + ".xlsx" if ext.lower() != ".xlsx" else output_path
        df.to_excel(xlsx_path, index=False)
        if verbose:
            print(f"Saved Excel -> {xlsx_path}")
    else:
        csv_path = base + ".csv" if ext.lower() != ".csv" else output_path
        df.to_csv(csv_path, index=False)
        if verbose:
            print(f"Saved CSV  -> {csv_path}")


def _prepare_dataframe(rows: list[dict[str, Any]]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    if "date" in df.columns:
        df["date"] = pd.to_datetime(df["date"], errors="coerce")

    meta_cols = [
        "date",
        "source_file",
        "page",
        "table_index",
        "table_title",
        "header_row_index",
        "row_index",
        "record_type",
    ]
    other_cols = [col for col in df.columns if col not in meta_cols]
    ordered = [col for col in meta_cols if col in df.columns] + sorted(other_cols)
    return df[ordered]


def stitch_all_tables(
    pdf_paths: list[str],
    output_path: str,
    output_format: str = "csv",
    layout: str = "wide",
    verbose: bool = False,
) -> pd.DataFrame | tuple[pd.DataFrame, pd.DataFrame]:
    all_wide: list[dict[str, Any]] = []
    all_long: list[dict[str, Any]] = []

    for pdf_path in pdf_paths:
        wide_rows, long_rows = extract_pdf_all_tables(pdf_path, verbose=verbose)
        all_wide.extend(wide_rows)
        all_long.extend(long_rows)
        if verbose:
            print(
                f"  {os.path.basename(pdf_path)} -> "
                f"{len(wide_rows)} wide rows, {len(long_rows)} long cells"
            )

    base, _ = os.path.splitext(output_path)

    if layout == "both":
        wide_df = _prepare_dataframe(all_wide)
        long_df = _prepare_dataframe(all_long)
        _write_dataframe(wide_df, base + "_wide", output_format, verbose=verbose)
        _write_dataframe(long_df, base + "_long", output_format, verbose=verbose)
        return wide_df, long_df

    rows = all_long if layout == "long" else all_wide
    df = _prepare_dataframe(rows)
    _write_dataframe(df, output_path, output_format, verbose=verbose)
    return df


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract every row from all PDF tables into CSV or Excel."
    )
    parser.add_argument("--input-dir", nargs="+", default=None, help="PDF folder(s).")
    parser.add_argument("--from-config", action="store_true", help="Use pdf_root from drive_config.json.")
    parser.add_argument(
        "--output",
        default="bf8_all_rows",
        help="Output path without extension (default: bf8_all_rows).",
    )
    parser.add_argument(
        "--format",
        choices=("csv", "excel", "both"),
        default="both",
        help="Output format (default: both).",
    )
    parser.add_argument(
        "--layout",
        choices=("wide", "long", "both"),
        default="wide",
        help="wide=one row per table row (default); long=one row per cell; both=write both.",
    )
    parser.add_argument(
        "--pdf-pattern",
        default=None,
        help=f"Glob for PDF filenames (default: {DEFAULT_PDF_PATTERN!r} when using --input-dir).",
    )
    parser.add_argument("--recursive", action="store_true", help="Search PDFs recursively.")
    parser.add_argument("--verbose", action="store_true", help="Print progress.")
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
        import fnmatch

        pdf_paths = [path for path in pdf_paths if fnmatch.fnmatch(os.path.basename(path), pdf_pattern)]

    if not pdf_paths:
        print("No PDF files found.", file=sys.stderr)
        return 1

    if use_config and args.verbose:
        print("PDF folders:")
        for folder in input_dirs:
            print(f"  - {folder}")

    print(f"Extracting all table rows from {len(pdf_paths)} PDF(s)...")
    result = stitch_all_tables(
        pdf_paths,
        args.output,
        output_format=args.format,
        layout=args.layout,
        verbose=args.verbose,
    )

    if isinstance(result, tuple):
        wide_df, long_df = result
        print(
            f"Saved wide: {len(wide_df)} rows x {len(wide_df.columns)} columns; "
            f"long: {len(long_df)} rows x {len(long_df.columns)} columns"
        )
    else:
        print(f"Saved {len(result)} rows x {len(result.columns)} columns")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
