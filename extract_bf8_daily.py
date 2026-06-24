#!/usr/bin/env python3
"""Extract BF-8 daily production parameters from blast furnace PDF reports.

Reads page 1 of each PDF, locates the main PARAMETERS table via pdfplumber,
pulls BF # 8 column values, and stitches one row per report day into a CSV.

Usage:
    python extract_bf8_daily.py --input-dir ./pdfs --output bf8_daily.csv
    python extract_bf8_daily.py --input-dir ./fy2024-25 ./fy2023-24 --output merged.csv
"""

from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from typing import Any

import pandas as pd
import pdfplumber

# Parameter label in PDF table -> output CSV column name
KEY_PARAMS: list[tuple[str, str]] = [
    ("PRODUCTION", "Production_T"),
    ("COKE Rt.", "CokeRate_kgTHM"),
    ("COAL DUST INJ.", "CDI_Rate_kgTHM"),
    ("FUEL RATE", "FuelRate_kgTHM"),
    ("RAFT", "RAFT_C"),
    ("IRON ORE RATE", "Iron_ore_rate_kgTHM"),
    ("SINTER Rt.", "SinterRate_kgTHM"),
    ("NUT COKE Rt.", "NutCokeRate_kgTHM"),
    ("SLAG RATE", "SlagRate_kgTHM"),
    ("Scrap Rt.", "ScrapRate_kgTHM"),
    ("Pellet Rt.", "PelletRate_kgTHM"),
    ("Mn.Ore Rt.", "MnOreRate_kgTHM"),
    ("Lime stone Rate", "LimeStoneRate_kgTHM"),
    ("L.D. SLAG Rt.", "LDSlagRate_kgTHM"),
    ("Quartz Rt.", "QuartzRate_kgTHM"),
    ("Burden Ratio", "Burden_Ratio"),
    ("Burden Weight / Chg.", "Burden_wt_chg"),
    ("HOT BLAST Temp.", "Hot_Blast_Temp"),
    ("BLAST Vol.", "Blast_vol"),
    ("BLAST Pressure", "Blast_Pressure"),
    ("BLAST Rate", "Blast_Rate"),
    ("HOT METAL TEMP", "Hot_Metal_Temp"),
    ("% OXY. ENRCH.", "Oxygen_Enrichment_%"),
]

NUMERIC_COLUMNS = [label for _, label in KEY_PARAMS]

# Text-line aliases when the PARAMETERS column label differs slightly in extract_text().
TEXT_PARAM_ALIASES: dict[str, list[str]] = {
    "PRODUCTION": [r"\bPRODUCTION\b"],
    "COKE Rt.": [r"COKE\s+Rt\."],
    "COAL DUST INJ.": [r"COAL\s+DUST\s+INJ\."],
    "FUEL RATE": [r"FUEL\s+RATE"],
    "RAFT": [r"\bRAFT\b"],
    "IRON ORE RATE": [r"IRON\s+ORE\s+RATE"],
    "SINTER Rt.": [r"SINTER\s+Rt\."],
    "NUT COKE Rt.": [r"NUT\s+COKE\s+Rt\."],
    "SLAG RATE": [r"SLAG\s+RATE"],
    "Scrap Rt.": [r"Scrap\s+Rt\."],
    "Pellet Rt.": [r"Pellet\s+Rt\."],
    "Mn.Ore Rt.": [r"Mn\.Ore\s+Rt\."],
    "Lime stone Rate": [r"Lime\s+stone\s+Rate"],
    "L.D. SLAG Rt.": [r"L\.D\.\s+SLAG\s+Rt\."],
    "Quartz Rt.": [r"Quartz\s+Rt\."],
    "Burden Ratio": [r"Burden\s+Ratio"],
    "Burden Weight / Chg.": [r"Burden\s+Weight\s*/\s*Chg\."],
    "HOT BLAST Temp.": [r"HOT\s+BLAST\s+Temp\."],
    "BLAST Vol.": [r"BLAST\s+Vol\."],
    "BLAST Pressure": [r"BLAST\s+Pressure"],
    "BLAST Rate": [r"BLAST\s+Rate"],
    "HOT METAL TEMP": [r"HOT\s+METAL\s+TEMP"],
    "% OXY. ENRCH.": [r"%\s*OXY\.\s*ENRCH\."],
}

# BF # 8 is the 5th furnace value: BF4, BF5, BF6, BF7, BF8.
BF8_NUMBER_INDEX = 4


def _normalize_label(value: Any) -> str:
    """Collapse whitespace so minor PDF spacing differences still match."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip()).upper()


def _find_main_table(tables: list[list[list[Any]]]) -> tuple[list[list[Any]] | None, list[Any] | None]:
    """Return the PARAMETERS table and its header row."""
    for table in tables:
        for row in table:
            if not row:
                continue
            row_text = " ".join(str(cell) for cell in row if cell)
            if "PARAMETERS" in row_text and "BF # 8" in row_text:
                return table, row
    return None, None


def _find_bf8_column(header_row: list[Any] | None) -> int:
    if not header_row:
        return -1
    for idx, cell in enumerate(header_row):
        if cell and re.search(r"BF\s*#\s*8", str(cell)):
            return idx
    return -1


def _numbers_from_line(line: str) -> list[str]:
    return re.findall(r"-?\d+(?:\.\d+)?", line)


def _numbers_after_unit(line: str) -> list[str]:
    """Return numeric furnace values that appear after the measurement unit token."""
    unit_markers = [
        "Kg/THM",
        "Cu.M/Thm",
        "Cu.M/Min",
        "TONNES",
        "T/Cu.M/D",
        "°C",
        "Atm",
        "T/Hr.",
        "Gm/NM3",
        "Cu.M.",
        "Hrs.",
        "Nos.",
    ]
    segment = line
    for marker in unit_markers:
        if marker in segment:
            segment = segment.split(marker, 1)[1]
            break

    # Drop oxygen-enrichment suffix labels such as "31300 B".
    numbers = _numbers_from_line(segment)
    if "% OXY" in line.upper():
        numbers = [n for n in numbers if float(n) < 100][:5]
    return numbers


def _bf8_from_furnace_numbers(numbers: list[str], bf5_empty: bool = False) -> str | None:
    """Map extracted furnace numbers to BF # 8."""
    if not numbers:
        return None
    if bf5_empty:
        if len(numbers) >= 5:
            return numbers[3]
        return numbers[-1]
    if len(numbers) >= 5:
        return numbers[BF8_NUMBER_INDEX]
    return numbers[-1]


def _reconcile_bf8_value(
    table_bf8: Any,
    table_total: Any,
    text_numbers: list[str],
    bf5_empty: bool,
    param_name: str = "",
) -> Any:
    """Pick the most reliable BF # 8 value when table cells are ambiguous."""
    if not bf5_empty:
        return table_bf8

    text_at_3 = text_numbers[3] if len(text_numbers) > 3 else None
    text_at_4 = text_numbers[4] if len(text_numbers) > 4 else None

    # Wet coke rate rows shift BF # 8 into TOTAL when BF # 5 is blank in the table.
    if (
        param_name == "COKE Rt."
        and text_at_4 is not None
        and table_total is not None
        and text_at_4 == str(table_total)
    ):
        return table_total

    if text_at_3 is not None and table_bf8 is not None and text_at_3 == str(table_bf8):
        return table_bf8

    if table_bf8 is not None and str(table_bf8).strip() != "":
        return table_bf8
    if table_total is not None and str(table_total).strip() != "":
        return table_total
    return text_at_3 or text_at_4


def _extract_bf8_from_text(page_text: str, param_name: str) -> list[str]:
    """Return furnace numbers parsed from the parameter line in page text."""
    patterns = TEXT_PARAM_ALIASES.get(param_name, [re.escape(param_name)])
    for line in page_text.splitlines():
        for pattern in patterns:
            if re.search(pattern, line, re.IGNORECASE):
                return _numbers_after_unit(line)
    return []


def _extract_date(page_text: str | None, pdf_path: str) -> str:
    if page_text:
        match = re.search(r"DATE-\s*(\d{1,2}\.\s*\w+\.\s*\d{4})", page_text)
        if match:
            return match.group(1).strip()

    # Fallback: filename like NEW P.D.14.02-12.pdf -> day-month hint only
    basename = os.path.basename(pdf_path)
    file_match = re.search(r"(\d{2})-(\d{2})\.pdf$", basename, re.IGNORECASE)
    if file_match:
        return f"{int(file_match.group(1))}-{int(file_match.group(2))} (from filename)"

    return "Unknown"


def extract_bf8(pdf_path: str, verbose: bool = False) -> dict[str, Any]:
    """Extract BF-8 parameters from one daily production report PDF."""
    empty = {"Date": "Unknown", "source_file": os.path.basename(pdf_path)}
    empty.update({label: None for _, label in KEY_PARAMS})

    try:
        with pdfplumber.open(pdf_path) as pdf:
            if not pdf.pages:
                if verbose:
                    print(f"WARNING: no pages in {pdf_path}", file=sys.stderr)
                return empty

            page = pdf.pages[0]
            page_text = page.extract_text() or ""
            tables = page.extract_tables() or []
    except Exception as exc:
        if verbose:
            print(f"WARNING: failed to open {pdf_path}: {exc}", file=sys.stderr)
        return empty

    main_table, header_row = _find_main_table(tables)
    if main_table is None:
        if verbose:
            print(f"WARNING: main PARAMETERS table not found in {pdf_path}", file=sys.stderr)
        empty["Date"] = _extract_date(page_text, pdf_path)
        return empty

    bf8_col_idx = _find_bf8_column(header_row)
    if bf8_col_idx < 0:
        if verbose:
            print(f"WARNING: BF # 8 column not found in {pdf_path}", file=sys.stderr)
        empty["Date"] = _extract_date(page_text, pdf_path)
        return empty

    param_lookup: dict[str, list[Any]] = {}
    for row in main_table:
        if not row or len(row) <= 2 or not row[2]:
            continue
        param_lookup[_normalize_label(row[2])] = row

    bf5_col_idx = -1
    total_col_idx = -1
    if header_row:
        for idx, cell in enumerate(header_row):
            if cell and re.search(r"BF\s*#\s*5", str(cell)):
                bf5_col_idx = idx
            if cell and str(cell).strip().upper() == "TOTAL":
                total_col_idx = idx

    record: dict[str, Any] = {
        "Date": _extract_date(page_text, pdf_path),
        "source_file": os.path.basename(pdf_path),
    }

    for param_name, col_label in KEY_PARAMS:
        row = param_lookup.get(_normalize_label(param_name))
        text_numbers = _extract_bf8_from_text(page_text, param_name)

        if row is None:
            record[col_label] = _bf8_from_furnace_numbers(text_numbers) if text_numbers else None
            if record[col_label] is None and verbose:
                print(f"WARNING: parameter {param_name!r} missing in {pdf_path}", file=sys.stderr)
            continue

        table_bf8 = row[bf8_col_idx] if bf8_col_idx < len(row) else None
        table_total = row[total_col_idx] if total_col_idx >= 0 and total_col_idx < len(row) else None
        bf5_empty = (
            bf5_col_idx >= 0
            and bf5_col_idx < len(row)
            and (row[bf5_col_idx] is None or str(row[bf5_col_idx]).strip() == "")
        )

        value = _reconcile_bf8_value(
            table_bf8, table_total, text_numbers, bf5_empty, param_name=param_name
        )
        if value is not None and str(value).strip() == "":
            value = None
        record[col_label] = value

    return record


def collect_pdf_paths(input_dirs: list[str], recursive: bool = False) -> list[str]:
    paths: list[str] = []
    pattern = "**/*.pdf" if recursive else "*.pdf"

    for directory in input_dirs:
        if not os.path.isdir(directory):
            raise FileNotFoundError(f"Input directory not found: {directory}")
        matched = glob.glob(os.path.join(directory, pattern), recursive=recursive)
        paths.extend(matched)

    return sorted(set(paths))


def stitch_pdfs_to_csv(
    pdf_paths: list[str],
    output_csv: str,
    verbose: bool = False,
    replace_zero_with_na: bool = True,
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []

    for pdf_path in pdf_paths:
        record = extract_bf8(pdf_path, verbose=verbose)
        records.append(record)
        if verbose:
            print(f"  {os.path.basename(pdf_path)} -> {record['Date']}")

    df = pd.DataFrame(records)

    for col in NUMERIC_COLUMNS:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.sort_values("Date").reset_index(drop=True)

    if replace_zero_with_na:
        df = df.replace(0, pd.NA)

    df.to_csv(output_csv, index=False)
    return df


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Extract BF-8 daily parameters from production report PDFs into one CSV."
    )
    parser.add_argument(
        "--input-dir",
        nargs="+",
        required=True,
        help="One or more folders containing daily PDF reports.",
    )
    parser.add_argument(
        "--output",
        default="bf8_daily.csv",
        help="Output CSV path (default: bf8_daily.csv).",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search for PDFs recursively inside input folders.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-file progress and warnings.",
    )
    parser.add_argument(
        "--keep-zero",
        action="store_true",
        help="Keep literal 0 values instead of converting them to NA.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    pdf_paths = collect_pdf_paths(args.input_dir, recursive=args.recursive)
    if not pdf_paths:
        print("No PDF files found.", file=sys.stderr)
        return 1

    print(f"Found {len(pdf_paths)} PDF(s). Extracting...")
    df = stitch_pdfs_to_csv(
        pdf_paths,
        args.output,
        verbose=args.verbose,
        replace_zero_with_na=not args.keep_zero,
    )

    print(f"Saved {df.shape[0]} rows x {df.shape[1]} columns -> {args.output}")
    missing_dates = int(df["Date"].isna().sum())
    if missing_dates:
        print(f"Note: {missing_dates} row(s) have unparseable dates.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
