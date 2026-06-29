#!/usr/bin/env python3
"""Merge per-table extractor CSVs into one day-by-day file.

Each extractor writes its own BF8_*.csv with a shared ``date`` column.
This script outer-joins them so you get one row per day with every column.

Example:
    python merge_extractor_outputs.py --input-dir output
    python merge_extractor_outputs.py output/BF8_production_parameters.csv output/BF8_hot_metal_slag.csv ...
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from typing import Any

import pandas as pd

META_COLUMNS = ("report_date", "year", "month", "day", "source_file")
DEFAULT_GLOB = "BF8_*.csv"
PREFERRED_BASE = "BF8_production_parameters"
ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DMY_DATE_RE = re.compile(r"^\d{2}-\d{2}-\d{4}$")


def _sort_input_paths(paths: list[str]) -> list[str]:
    """Put production parameters first when present — it has the fullest date block."""

    def sort_key(path: str) -> tuple[int, str]:
        base = os.path.splitext(os.path.basename(path))[0]
        if base == PREFERRED_BASE or base.startswith(PREFERRED_BASE):
            return (0, path)
        return (1, path)

    return sorted(paths, key=sort_key)


def _canonical_date(value: Any) -> str:
    """Normalize mixed date strings to ISO ``YYYY-MM-DD``."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = str(value).strip()
    if not text or text.lower() in {"nan", "nat", "none"}:
        return ""

    if ISO_DATE_RE.match(text):
        parsed = pd.to_datetime(text, format="%Y-%m-%d", errors="coerce")
    elif DMY_DATE_RE.match(text):
        parsed = pd.to_datetime(text, format="%d-%m-%Y", errors="coerce")
    else:
        parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)

    if pd.isna(parsed):
        return ""
    return parsed.strftime("%Y-%m-%d")


def _normalize_date_column(df: pd.DataFrame) -> pd.DataFrame:
    """Drop blank dates, canonicalize format, and keep one row per day (last wins)."""
    df = df.copy()
    df["date"] = df["date"].map(_canonical_date)
    df = df.loc[df["date"] != ""].copy()
    if df.empty:
        return df
    return df.drop_duplicates(subset=["date"], keep="last")


def collect_csv_paths(input_dir: str | None, inputs: list[str], pattern: str) -> list[str]:
    paths: list[str] = []
    if input_dir:
        paths.extend(glob.glob(os.path.join(input_dir, pattern)))
    paths.extend(inputs)
    paths = sorted(set(os.path.abspath(path) for path in paths))
    paths = [
        path
        for path in paths
        if not os.path.basename(path).startswith("BF8_merged_all")
    ]
    if not paths:
        raise FileNotFoundError("No extractor CSV files found.")
    return _sort_input_paths(paths)


def _read_table(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    if "date" not in df.columns:
        raise ValueError(f"{path} has no 'date' column.")
    df = _normalize_date_column(df)
    if df.empty:
        raise ValueError(f"{path}: no valid dates after cleanup.")
    return df


def merge_extractor_csvs(paths: list[str], verbose: bool = False) -> pd.DataFrame:
    """Merge multiple extractor outputs on ``date`` (outer join)."""
    merged: pd.DataFrame | None = None

    for path in paths:
        df = _read_table(path)
        if verbose:
            print(f"  {os.path.basename(path)}: {len(df)} row(s), {len(df.columns)} column(s)")

        if merged is None:
            merged = df
            continue

        new_cols = [col for col in df.columns if col != "date" and col not in merged.columns]
        if not new_cols:
            if verbose:
                print(f"    (no new columns — skipped)")
            continue

        merged = merged.merge(df[["date", *new_cols]], on="date", how="outer")

    if merged is None:
        raise ValueError("No tables to merge.")

    meta_present = [col for col in META_COLUMNS if col in merged.columns]
    other_cols = [col for col in merged.columns if col not in {"date", *meta_present}]
    merged = merged[["date", *meta_present, *other_cols]]

    order = sorted(
        range(len(merged)),
        key=lambda index: str(merged.iat[index, 0]),
    )
    merged = merged.iloc[order].reset_index(drop=True)
    return merged


def write_merged(df: pd.DataFrame, output_path: str, output_format: str) -> None:
    base, ext = os.path.splitext(output_path)
    if output_format in ("csv", "both"):
        csv_path = output_path if ext.lower() == ".csv" else base + ".csv"
        df.to_csv(csv_path, index=False)
        print(f"Saved CSV  -> {csv_path}")
    if output_format in ("excel", "both"):
        xlsx_path = output_path if ext.lower() == ".xlsx" else base + ".xlsx"
        df.to_excel(xlsx_path, index=False)
        print(f"Saved Excel -> {xlsx_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Merge BF8_*.csv extractor outputs into one day-by-day file."
    )
    parser.add_argument(
        "inputs",
        nargs="*",
        help="Extractor CSV file(s). If omitted, use --input-dir.",
    )
    parser.add_argument(
        "--input-dir",
        help=f"Folder containing extractor CSVs (default glob: {DEFAULT_GLOB!r}).",
    )
    parser.add_argument(
        "--pattern",
        default=DEFAULT_GLOB,
        help=f"Glob pattern when using --input-dir (default: {DEFAULT_GLOB!r}).",
    )
    parser.add_argument(
        "--output",
        default="BF8_merged_all",
        help="Output path without extension (default: BF8_merged_all).",
    )
    parser.add_argument(
        "--format",
        choices=("csv", "excel", "both"),
        default="csv",
        help="Output format (default: csv).",
    )
    parser.add_argument("--verbose", action="store_true", help="Print per-file details.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        paths = collect_csv_paths(args.input_dir, args.inputs, args.pattern)
    except FileNotFoundError as exc:
        print(exc, file=sys.stderr)
        return 1

    if args.verbose:
        print(f"Merging {len(paths)} file(s)...")
    else:
        print(f"Merging {len(paths)} extractor CSV(s)...")

    try:
        df = merge_extractor_csvs(paths, verbose=args.verbose)
    except (ValueError, OSError) as exc:
        print(exc, file=sys.stderr)
        return 1

    write_merged(df, args.output, args.format)
    print(f"Merged shape: {len(df)} row(s) x {len(df.columns)} column(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
