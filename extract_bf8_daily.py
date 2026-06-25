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
import calendar
import glob
import os
import re
import sys
from typing import Any

import pandas as pd
import pdfplumber

from drive_paths import load_drive_config, resolve_input_directories

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

# Page 2: hot metal & slag quality (table 0, column layout with BF-8)
QUALITY_PARAMS: list[tuple[str, str]] = [
    ("Avg. % 'Si'", "HM_Si_pct_avg"),
    ("Avg. % 'S'", "HM_S_pct_avg"),
    ("Avg. % MgO", "Slag_MgO_pct_avg"),
    ("Avg. % Al2O3", "Slag_Al2O3_pct_avg"),
    ("Avg. % FeO", "Slag_FeO_pct_avg"),
    ("Avg. % K2O", "Slag_K2O_pct_avg"),
    ("BASICITY(-)", "Slag_Basicity_avg"),
    ("Avg. % 'P'", "HM_P_pct_avg"),
]

QUALITY_NUMERIC_COLUMNS = [label for _, label in QUALITY_PARAMS]

# Page 2: BF-8 row tables (first column identifies the furnace)
SKIP_SINTER_COLUMNS: list[tuple[str, str]] = [
    ("% Fe", "SkipSinter_Fe_pct"),
    ("% SiO2", "SkipSinter_SiO2_pct"),
    ("% Al2O3", "SkipSinter_Al2O3_pct"),
    ("% CaO", "SkipSinter_CaO_pct"),
    ("% MgO", "SkipSinter_MgO_pct"),
    ("BASICITY", "SkipSinter_Basicity"),
]

SEIVE_COLUMNS: list[tuple[str, str]] = [
    ("-10 mm", "Seive_minus10mm"),
    ("- 5 mm", "Seive_minus5mm"),
    ("M.Size", "Seive_MSize"),
    ("+40 mm", "Seive_plus40mm"),
]

PELLET_COLUMNS: list[tuple[str, str]] = [
    ("Fe", "Pellet_Fe_pct"),
    ("SiO2", "Pellet_SiO2_pct"),
    ("Al2O3", "Pellet_Al2O3_pct"),
    ("CaO", "Pellet_CaO_pct"),
    ("MgO", "Pellet_MgO_pct"),
    ("+ 10 MM", "Pellet_plus10mm"),
    ("- 5 MM", "Pellet_minus5mm"),
    ("M.Size", "Pellet_MSize"),
    ("Basicity", "Pellet_Basicity"),
]

PAGE2_NUMERIC_COLUMNS = (
    QUALITY_NUMERIC_COLUMNS
    + [label for _, label in SKIP_SINTER_COLUMNS]
    + [label for _, label in SEIVE_COLUMNS]
    + [label for _, label in PELLET_COLUMNS]
)

# Text-line aliases when the PARAMETERS column label differs slightly in extract_text().
TEXT_PARAM_ALIASES: dict[str, list[str]] = {
    "PRODUCTION": [r"\bPRODUCTION\b"],
    "COKE Rt.": [r"COKE\s+Rt\."],
    "COAL DUST INJ.": [r"COAL\s+DUST\s+INJ\."],
    "FUEL RATE": [r"FUEL\s+RATE"],
    "RAFT": [r"\bRAFT\b"],
    "IRON ORE RATE": [r"IRON\s+ORE\s+RATE", r"IRON\s+RATE"],
    "SINTER Rt.": [r"SINTER\s+Rt\."],
    "NUT COKE Rt.": [r"NUT\s+COKE\s+Rt\."],
    "SLAG RATE": [r"SLAG\s+RATE"],
    "Scrap Rt.": [r"Scrap\s+Rt\."],
    "Pellet Rt.": [r"Pellet\s+Rt\."],
    "Mn.Ore Rt.": [r"Mn\.Ore\s+Rt\."],
    "Lime stone Rate": [r"Lime\s+stone\s+Rate"],
    "L.D. SLAG Rt.": [r"L\.D\.\s+SLAG\s+Rt\."],
    "Quartz Rt.": [r"Quartz\s+Rt\.", r"Quartz/DOLOMITE\s+Rt\."],
    "Burden Ratio": [r"Burden\s+Ratio"],
    "Burden Weight / Chg.": [r"Burden\s+Weight\s*/\s*Chg\."],
    "HOT BLAST Temp.": [r"HOT\s+BLAST\s+Temp\."],
    "BLAST Vol.": [r"BLAST\s+Vol\."],
    "BLAST Pressure": [r"BLAST\s+Pressure"],
    "BLAST Rate": [r"BLAST\s+Rate"],
    "HOT METAL TEMP": [r"HOT\s+METAL\s+TEMP"],
    "% OXY. ENRCH.": [r"%\s*OXY\.\s*ENRCH\."],
}

# Alternate PDF labels for the same parameter (older report formats).
PARAM_NAME_ALIASES: dict[str, list[str]] = {
    "IRON ORE RATE": ["IRON ORE RATE", "IRON ORE RT.", "IRON  ORE RATE", "IRON RATE"],
    "Mn.Ore Rt.": ["MN.ORE RT.", "MN ORE RT.", "(A) MN.ORE RT."],
    "Quartz Rt.": ["QUARTZ RT.", "QUARTZ/DOLOMITE RT.", "QUARTZ/DOLOMITE RT"],
    "PRODUCTION": ["PRODUCTION", "NOITCUDORP"],
    "SLAG RATE": ["SLAG RATE", "SLAG  RATE"],
}

# BF # 8 is the 5th furnace value: BF4, BF5, BF6, BF7, BF8.
BF8_NUMBER_INDEX = 4

BF8_ROW_RE = re.compile(r"BF\s*#\s*-?\s*8", re.IGNORECASE)


def _normalize_label(value: Any) -> str:
    """Collapse whitespace so minor PDF spacing differences still match."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip()).upper()


def _find_main_table(tables: list[list[list[Any]]]) -> tuple[list[list[Any]] | None, list[Any] | None]:
    """Return the PARAMETERS table and its header row."""
    best_table: list[list[Any]] | None = None
    best_header: list[Any] | None = None
    best_size = 0

    for table in tables:
        for row in table:
            if not row:
                continue
            row_text = " ".join(str(cell) for cell in row if cell)
            row_upper = row_text.upper()
            if "PARAMETERS" in row_upper and BF8_ROW_RE.search(row_text):
                return table, row
            if BF8_ROW_RE.search(row_text) and ("UNIT" in row_upper or "SL.NO" in row_upper):
                return table, row

        has_production = any(
            row and len(row) > 2 and _normalize_label(row[2]) == "PRODUCTION" for row in table
        )
        if not has_production:
            continue

        for row in table:
            if not row:
                continue
            row_text = " ".join(str(cell) for cell in row if cell)
            if BF8_ROW_RE.search(row_text):
                if len(table) > best_size:
                    best_table, best_header, best_size = table, row, len(table)

    return best_table, best_header


def _build_param_lookup(main_table: list[list[Any]]) -> dict[str, list[Any]]:
    """Map normalized parameter labels to table rows."""
    lookup: dict[str, list[Any]] = {}
    for row in main_table:
        if not row or len(row) < 3:
            continue
        labels: list[str] = []
        if row[2]:
            labels.append(str(row[2]))
        if row[1] and row[2]:
            labels.append(f"{row[1]} {row[2]}")
        for label in labels:
            lookup[_normalize_label(label)] = row
    return lookup


def _lookup_param_row(lookup: dict[str, list[Any]], param_name: str) -> list[Any] | None:
    """Find a parameter row using aliases and fuzzy matching."""
    key = _normalize_label(param_name)
    if key in lookup:
        return lookup[key]

    for alias in PARAM_NAME_ALIASES.get(param_name, []):
        alias_key = _normalize_label(alias)
        if alias_key in lookup:
            return lookup[alias_key]
        for label, row in lookup.items():
            if label == alias_key or label.endswith(" " + alias_key):
                return row

    if param_name == "IRON ORE RATE":
        for label, row in lookup.items():
            if label == "IRON RATE" or label.endswith(" IRON RATE"):
                return row
            if "IRON" in label and "RATE" in label and "ORE" not in label:
                if "TONNES" not in label and "TILL" not in label and "%" not in label:
                    return row
        for label, row in lookup.items():
            if "IRON" in label and "ORE" in label and ("RATE" in label or "RT." in label):
                if "TILL" not in label and "%" not in label:
                    return row

    if param_name == "Mn.Ore Rt.":
        for label, row in lookup.items():
            if "MN" in label and "ORE" in label and "RT" in label:
                return row

    if param_name == "Quartz Rt.":
        for label, row in lookup.items():
            if "QUARTZ" in label and "RT" in label:
                return row

    return None


def _is_bf8_label(value: Any) -> bool:
    if value is None:
        return False
    text = str(value).strip().upper().rstrip("=>").strip()
    return bool(BF8_ROW_RE.search(text)) or text in {"BF-8", "BF #8"}


def _find_bf8_row(table: list[list[Any]]) -> list[Any] | None:
    for row in table:
        if row and _is_bf8_label(row[0]):
            return row
    return None


def _header_lookup(header_row: list[Any] | None) -> dict[str, int]:
    if not header_row:
        return {}
    return {
        _normalize_label(cell): idx
        for idx, cell in enumerate(header_row)
        if cell and str(cell).strip()
    }


def _value_from_header_aliases(
    header_row: list[Any] | None,
    data_row: list[Any],
    aliases: list[str],
) -> Any:
    lookup = _header_lookup(header_row)
    for alias in aliases:
        idx = lookup.get(_normalize_label(alias))
        if idx is None or idx >= len(data_row):
            continue
        value = data_row[idx]
        if value is not None and str(value).strip() not in ("", "#DIV/0!", "#DIV/0"):
            return value
    return None


def _find_bf8_column(header_row: list[Any] | None) -> int:
    if not header_row:
        return -1
    for idx, cell in enumerate(header_row):
        if cell and re.search(r"BF\s*[#-]\s*8", str(cell)):
            return idx
    return -1


def _find_quality_table(
    tables: list[list[list[Any]]],
) -> tuple[list[list[Any]] | None, list[Any] | None]:
    """Return the HOT METAL AND SLAG QUALITY table and its header row."""
    for table in tables:
        for row in table:
            if not row:
                continue
            row_text = " ".join(str(cell) for cell in row if cell)
            if "Parameter" in row_text and re.search(r"BF\s*-\s*8", row_text):
                return table, row
    return None, None


def _extract_row_table_values(
    header_row: list[Any] | None,
    data_row: list[Any],
    column_map: list[tuple[str, str]],
    header_aliases: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Map header labels to output columns for a BF # 8 data row."""
    record: dict[str, Any] = {}
    if not header_row or not data_row:
        return record

    header_aliases = header_aliases or {}
    lookup = _header_lookup(header_row)

    for header_label, out_col in column_map:
        aliases = header_aliases.get(header_label, [header_label])
        value = _value_from_header_aliases(header_row, data_row, aliases)
        if value is None:
            record[out_col] = None
            continue
        record[out_col] = value

    return record


SEIVE_HEADER_ALIASES: dict[str, list[str]] = {
    "-10 mm": ["-10 mm", "- 10 mm", "-10MM"],
    "- 5 mm": ["- 5 mm", "-5 mm", "- 5MM"],
    "M.Size": ["M.Size", "M. SIZE", "M.SIZE"],
    "+40 mm": ["+40 mm", "+ 40 mm", "+40MM"],
}


def _find_skip_sinter_table(
    tables: list[list[list[Any]]],
) -> tuple[list[Any] | None, list[Any] | None]:
    def is_sinter_header(row: list[Any]) -> bool:
        row_text = " ".join(str(cell) for cell in row if cell)
        normalized = _normalize_label(row_text)
        return "% FE" in normalized and "BASICITY" in normalized and "SKIP" not in normalized

    for table in tables:
        header_row = next((row for row in table if is_sinter_header(row)), None)
        data_row = _find_bf8_row(table)
        if header_row and data_row:
            return header_row, data_row
    return None, None


def _extract_seive_values(tables: list[list[list[Any]]]) -> dict[str, Any]:
    """Merge sieve metrics from one or more page-2 tables."""
    record: dict[str, Any] = {col: None for _, col in SEIVE_COLUMNS}

    for table in tables:
        data_row = _find_bf8_row(table)
        if not data_row:
            continue

        header_row = None
        for row in table:
            if not row:
                continue
            row_text = " ".join(str(cell) for cell in row if cell)
            if any(
                token in _normalize_label(row_text)
                for token in ("-10", "- 10", "+40", "- 5", "M.SIZE", "FCE.NO")
            ):
                header_row = row
                break
        if not header_row:
            continue

        for header_label, out_col in SEIVE_COLUMNS:
            if record[out_col] is not None:
                continue
            aliases = SEIVE_HEADER_ALIASES.get(header_label, [header_label])
            value = _value_from_header_aliases(header_row, data_row, aliases)
            if value is not None:
                record[out_col] = value

    return record


def _find_pellet_table(
    tables: list[list[list[Any]]],
) -> tuple[list[Any] | None, list[Any] | None]:
    for table in tables:
        if not any(
            row and row[0] and "PELLET CHEMICAL" in str(row[0]).upper() for row in table
        ):
            continue
        header_row = next(
            (
                row
                for row in table
                if row and any(str(cell).strip().upper() == "FE" for cell in row if cell)
            ),
            None,
        )
        data_row = _find_bf8_row(table)
        if header_row and data_row:
            return header_row, data_row
    return None, None


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

    if text_numbers and (table_bf8 is None or str(table_bf8).strip() == ""):
        text_value = _bf8_from_furnace_numbers(text_numbers, bf5_empty=bf5_empty)
        if text_value is not None:
            return text_value

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


def _infer_year_from_path(pdf_path: str, month: int) -> int:
    """Infer calendar year from DailyProdReports_FY2023-24 style folder names."""
    fy_match = re.search(r"FY(\d{4})-(\d{2})", pdf_path, re.IGNORECASE)
    if not fy_match:
        return 2024

    start_year = int(fy_match.group(1))
    end_year_suffix = int(fy_match.group(2))
    end_year = (start_year // 100) * 100 + end_year_suffix
    if end_year < start_year:
        end_year = start_year // 100 * 100 + end_year_suffix
    if end_year < start_year:
        end_year = start_year + 1

    # Indian fiscal year: Apr–Mar
    return start_year if month >= 4 else end_year


def _date_from_filename(pdf_path: str) -> str | None:
    """Parse NEW P.D.14.DD-MM.pdf filenames into a DATE- compatible string."""
    basename = os.path.basename(pdf_path)
    match = re.search(r"(\d{2})-(\d{2})\.pdf$", basename, re.IGNORECASE)
    if not match:
        return None

    day = int(match.group(1))
    month = int(match.group(2))
    if not 1 <= month <= 12 or not 1 <= day <= 31:
        return None

    year = _infer_year_from_path(pdf_path, month)
    month_name = calendar.month_abbr[month]
    return f"{day}. {month_name}. {year}"


def _extract_date(page_text: str | None, pdf_path: str) -> str:
    if page_text:
        patterns = [
            r"DATE-\s*(\d{1,2}\.\s*\w+\.\s*\d{4})",
            r"DATE\s*:\s*(\d{1,2}\.\s*\w+\.\s*\d{4})",
            r"DATE\s+(\d{1,2}\.\s*\w+\.\s*\d{4})",
        ]
        for pattern in patterns:
            match = re.search(pattern, page_text, re.IGNORECASE)
            if match:
                return match.group(1).strip()

    filename_date = _date_from_filename(pdf_path)
    if filename_date:
        return filename_date

    return "Unknown"


def _extract_page_tables(page: Any) -> list[list[list[Any]]]:
    """Extract tables from a page, retrying with line-based detection if needed."""
    tables = page.extract_tables() or []
    if tables:
        return tables

    return page.extract_tables(
        table_settings={
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines",
            "intersection_tolerance": 5,
        }
    ) or []


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
            tables = _extract_page_tables(page)
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

    param_lookup = _build_param_lookup(main_table)

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
        row = _lookup_param_row(param_lookup, param_name)
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


def extract_bf8_page2(pdf_path: str, verbose: bool = False) -> dict[str, Any]:
    """Extract BF-8 hot metal / slag quality and related page-2 tables."""
    empty: dict[str, Any] = {
        "Date": "Unknown",
        "source_file": os.path.basename(pdf_path),
    }
    empty.update({label: None for _, label in QUALITY_PARAMS})
    empty.update({label: None for _, label in SKIP_SINTER_COLUMNS})
    empty.update({label: None for _, label in SEIVE_COLUMNS})
    empty.update({label: None for _, label in PELLET_COLUMNS})

    try:
        with pdfplumber.open(pdf_path) as pdf:
            if len(pdf.pages) < 2:
                if verbose:
                    print(f"WARNING: page 2 missing in {pdf_path}", file=sys.stderr)
                return empty

            page1_text = pdf.pages[0].extract_text() or ""
            page = pdf.pages[1]
            page_text = page.extract_text() or ""
            tables = _extract_page_tables(page)
    except Exception as exc:
        if verbose:
            print(f"WARNING: failed to open {pdf_path}: {exc}", file=sys.stderr)
        return empty

    record: dict[str, Any] = {
        "Date": _extract_date(page1_text, pdf_path),
        "source_file": os.path.basename(pdf_path),
    }

    quality_table, quality_header = _find_quality_table(tables)
    if quality_table is None:
        if verbose:
            print(f"WARNING: quality table not found in {pdf_path}", file=sys.stderr)
        record.update({label: None for _, label in QUALITY_PARAMS})
    else:
        bf8_col_idx = _find_bf8_column(quality_header)

        param_lookup = {
            _normalize_label(row[0]): row
            for row in quality_table
            if row and row[0] and str(row[0]).strip()
        }

        for param_name, col_label in QUALITY_PARAMS:
            row = param_lookup.get(_normalize_label(param_name))
            if row is None:
                record[col_label] = None
                if verbose:
                    print(
                        f"WARNING: quality parameter {param_name!r} missing in {pdf_path}",
                        file=sys.stderr,
                    )
                continue

            value = row[bf8_col_idx] if bf8_col_idx >= 0 and bf8_col_idx < len(row) else None
            if value is not None and str(value).strip() == "":
                value = None
            record[col_label] = value

    sinter_header, sinter_row = _find_skip_sinter_table(tables)
    record.update(_extract_row_table_values(sinter_header, sinter_row or [], SKIP_SINTER_COLUMNS))
    record.update(_extract_seive_values(tables))

    pellet_header, pellet_row = _find_pellet_table(tables)
    record.update(_extract_row_table_values(pellet_header, pellet_row or [], PELLET_COLUMNS))

    return record


def extract_bf8_combined(pdf_path: str, verbose: bool = False) -> dict[str, Any]:
    """Extract page-1 production and page-2 quality fields for one PDF."""
    record = extract_bf8(pdf_path, verbose=verbose)
    page2 = extract_bf8_page2(pdf_path, verbose=verbose)
    for key, value in page2.items():
        if key in ("Date", "source_file"):
            continue
        record[key] = value
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
    page: str = "1",
) -> pd.DataFrame:
    records: list[dict[str, Any]] = []

    extractors = {
        "1": extract_bf8,
        "2": extract_bf8_page2,
        "all": extract_bf8_combined,
    }
    extract_fn = extractors[page]

    for pdf_path in pdf_paths:
        record = extract_fn(pdf_path, verbose=verbose)
        records.append(record)
        if verbose:
            print(f"  {os.path.basename(pdf_path)} -> {record['Date']}")

    df = pd.DataFrame(records)

    numeric_cols = {
        "1": NUMERIC_COLUMNS,
        "2": PAGE2_NUMERIC_COLUMNS,
        "all": NUMERIC_COLUMNS + PAGE2_NUMERIC_COLUMNS,
    }[page]

    for col in numeric_cols:
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
        description=(
            "Extract BF-8 daily parameters from production report PDFs into CSV. "
            "With no --input-dir, reads PDF folders from drive_config.json."
        )
    )
    parser.add_argument(
        "--input-dir",
        nargs="+",
        default=None,
        help="One or more folders containing daily PDF reports (overrides config).",
    )
    parser.add_argument(
        "--from-config",
        action="store_true",
        help="Read PDF folders from pdf_root in drive_config.json.",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output CSV path (default: BF8_merged_all.csv from config, else bf8_daily.csv).",
    )
    parser.add_argument(
        "--page",
        choices=("1", "2", "all"),
        default=None,
        help="Which pages to extract: 1=production, 2=quality, all=merged.",
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

    if not input_dirs:
        print(
            "No input folders specified. Use --input-dir or set pdf_root in drive_config.json.\n"
            "See drive_config.json.example and README.md.",
            file=sys.stderr,
        )
        return 1

    output_csv = args.output or (config["output_csv"] if use_config else "bf8_daily.csv")
    page = args.page or (config["page"] if use_config else "1")

    if use_config:
        print("Using PDF folders from drive_config.json:")
        for folder in input_dirs:
            print(f"  - {folder}")

    pdf_paths = collect_pdf_paths(input_dirs, recursive=args.recursive)
    if not pdf_paths:
        print("No PDF files found.", file=sys.stderr)
        return 1

    page_label = {"1": "page 1 production", "2": "page 2 quality", "all": "pages 1+2"}[page]
    print(f"Found {len(pdf_paths)} PDF(s). Extracting {page_label}...")
    df = stitch_pdfs_to_csv(
        pdf_paths,
        output_csv,
        verbose=args.verbose,
        replace_zero_with_na=not args.keep_zero,
        page=page,
    )

    print(f"Saved {df.shape[0]} rows x {df.shape[1]} columns -> {output_csv}")
    missing_dates = int(df["Date"].isna().sum())
    if missing_dates:
        print(f"Note: {missing_dates} row(s) have unparseable dates.", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
