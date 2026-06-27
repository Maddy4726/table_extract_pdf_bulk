#!/usr/bin/env python3
"""Extract sinter plant chemical analysis from daily production report PDFs.

Reads page 2, locates the SINTER PLANT-2 and SINTER PLANT-3 chemistry tables
(% Fe, % FeO, % SiO2, % Al2O3, % CaO, % MgO, % MnO, CaO-SiO2, Basicity), and
writes one row per report day with day-average and shift-sample values.

Usage:
    python extract_sinter_plant.py --input-dir . --verbose
    python extract_sinter_plant.py --from-config --recursive --verbose
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import sys
from typing import Any

import pdfplumber

from drive_paths import load_drive_config, resolve_input_directories
from extract_bf8_daily import (
    _extract_page_tables,
    _normalize_label,
    _value_from_header_aliases,
    collect_pdf_paths,
)
from extract_table_utils import (
    DEFAULT_PDF_PATTERN,
    assign_report_date,
    stitch_records,
)

DEFAULT_OUTPUT = "BF8_sinter_plant"

PLANT_NUMBERS = ("2", "3")
SAMPLE_KEYS = ("AO", "A1", "A2", "BO", "B1", "B2", "CO", "C1", "C2", "DayAvg")

PLANT_METRICS: list[tuple[str, str]] = [
    ("% Fe", "Fe_pct"),
    ("% FeO", "FeO_pct"),
    ("% SiO2", "SiO2_pct"),
    ("% Al2O3", "Al2O3_pct"),
    ("% CaO", "CaO_pct"),
    ("% MgO", "MgO_pct"),
    ("% MnO", "MnO_pct"),
    ("CaO-SiO2", "CaO_SiO2"),
    ("Basicity", "Basicity"),
]

HEADER_ALIASES: dict[str, list[str]] = {
    "% Fe": ["% Fe", "% FE"],
    "% FeO": ["% FeO", "% FEO"],
    "% SiO2": ["% SiO2", "% SIO2"],
    "% Al2O3": ["% Al2O3", "% AL2O3"],
    "% CaO": ["% CaO", "% CAO"],
    "% MgO": ["% MgO", "% MGO"],
    "% MnO": ["% MnO", "% MNO"],
    "CaO-SiO2": ["CaO-SiO2", "CAO-SIO2"],
    "Basicity": ["Basicity", "BASICITY"],
}

NUMERIC_COLUMNS = [
    f"SinterPlant{plant}_{sample}_{suffix}"
    for plant in PLANT_NUMBERS
    for sample in SAMPLE_KEYS
    for _, suffix in PLANT_METRICS
]

VALUE_RANGES: dict[str, tuple[float, float]] = {
    **{col: (40.0, 58.0) for col in NUMERIC_COLUMNS if col.endswith("_Fe_pct")},
    **{col: (7.0, 12.0) for col in NUMERIC_COLUMNS if col.endswith("_FeO_pct")},
    **{col: (4.0, 14.0) for col in NUMERIC_COLUMNS if col.endswith("_SiO2_pct")},
    **{col: (0.5, 5.0) for col in NUMERIC_COLUMNS if col.endswith("_Al2O3_pct")},
    **{col: (10.0, 20.0) for col in NUMERIC_COLUMNS if col.endswith("_CaO_pct")},
    **{col: (1.5, 5.0) for col in NUMERIC_COLUMNS if col.endswith("_MgO_pct")},
    **{col: (0.0, 4.0) for col in NUMERIC_COLUMNS if col.endswith("_MnO_pct")},
    **{col: (4.0, 12.0) for col in NUMERIC_COLUMNS if col.endswith("_CaO_SiO2")},
    **{col: (1.4, 2.6) for col in NUMERIC_COLUMNS if col.endswith("_Basicity")},
}

INVALID_TOKENS = {"#DIV/0!", "#DIV/0", "STOP", ""}


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


def _clean_cell(value: Any) -> Any:
    if value is None:
        return None
    text = str(value).strip()
    if text.upper() in INVALID_TOKENS:
        return None
    return text


def _is_sinter_plant_chem_header(row: list[Any]) -> bool:
    normalized = _normalize_label(_row_text(row))
    if not normalized:
        return False
    if "FCE" in normalized or "BF" in normalized and "SAMPLE" not in normalized:
        return False
    if "PELLET" in normalized or "SKIP SINTER" in normalized:
        return False
    has_sample_col = "SAMPLE" in normalized
    return (
        has_sample_col
        and "FE" in normalized
        and "FEO" in normalized
        and "BASICITY" in normalized
    )


def _normalize_sample_key(cell: Any) -> str | None:
    if cell is None:
        return None
    text = str(cell).strip()
    if not text:
        return None

    upper = text.upper()
    if "DAY AVG" in upper:
        return "DayAvg"
    if upper in SAMPLE_KEYS:
        return upper

    if "SP-3" in upper or "SP-3/" in upper:
        tail = re.sub(r"[^A-Z0-9]", "", upper.split("/")[-1])
        match = re.search(r"([ABC])([012])$", tail)
        if match:
            letter, digit = match.group(1), match.group(2)
            return f"{letter}O" if digit == "0" else f"{letter}{digit}"

    return None


def _table_has_sp3_ids(table: list[list[Any]]) -> bool:
    return any(
        row
        and row[0]
        and ("SP-3" in str(row[0]).upper() or "SP-3/" in str(row[0]).upper())
        for row in table
    )


def _table_fill_score(table: list[list[Any]]) -> int:
    score = 0
    for row in table:
        key = _normalize_sample_key(row[0] if row else None)
        if not key:
            continue
        if _clean_cell(row[1] if len(row) > 1 else None) is not None:
            score += 1
    return score


def _assign_plant_number(
    table: list[list[Any]],
    table_index: int,
    tables: list[list[list[Any]]],
) -> str:
    if _table_has_sp3_ids(table):
        return "3"

    prior = 0
    for idx, candidate in enumerate(tables):
        if idx >= table_index:
            break
        if any(_is_sinter_plant_chem_header(row) for row in candidate):
            prior += 1
    return "2" if prior == 0 else "3"


def _trim_chem_row(header_row: list[Any], data_row: list[Any]) -> tuple[list[Any], list[Any]]:
    width = min(12, len(header_row), len(data_row))
    header = list(header_row[:width])
    data = list(data_row[:width])
    if header and not str(header[0] or "").strip():
        header[0] = "SAMPLE"
    if data and not str(data[0] or "").strip():
        data[0] = "SAMPLE"
    return header, data


def _extract_row_values(header_row: list[Any], data_row: list[Any]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    header, data = _trim_chem_row(header_row, data_row)
    for header_label, suffix in PLANT_METRICS:
        aliases = HEADER_ALIASES.get(header_label, [header_label])
        values[suffix] = _clean_cell(_value_from_header_aliases(header, data, aliases))
    return values


def _extract_from_table(
    header_row: list[Any],
    table: list[list[Any]],
    plant: str,
) -> dict[str, Any]:
    record: dict[str, Any] = {}
    for row in table:
        sample_key = _normalize_sample_key(row[0] if row else None)
        if sample_key not in SAMPLE_KEYS:
            continue
        values = _extract_row_values(header_row, row)
        prefix = f"SinterPlant{plant}_{sample_key}"
        for suffix, value in values.items():
            col = f"{prefix}_{suffix}"
            if record.get(col) is None and value is not None:
                record[col] = value
    return record


def _find_sinter_plant_tables(
    tables: list[list[list[Any]]],
) -> dict[str, dict[str, Any]]:
    extracted: dict[str, dict[str, Any]] = {}
    candidates: list[tuple[str, int, list[Any], list[list[Any]]]] = []

    for table_index, table in enumerate(tables):
        header_row = next((row for row in table if _is_sinter_plant_chem_header(row)), None)
        if not header_row:
            continue
        plant = _assign_plant_number(table, table_index, tables)
        candidates.append((plant, _table_fill_score(table), header_row, table))

    for plant in PLANT_NUMBERS:
        plant_tables = [item for item in candidates if item[0] == plant]
        if not plant_tables:
            continue
        plant_tables.sort(
            key=lambda item: (
                1 if _table_has_sp3_ids(item[3]) else 0,
                item[1],
            ),
            reverse=True,
        )
        _, _, header_row, table = plant_tables[0]
        extracted[plant] = _extract_from_table(header_row, table, plant)

        for _, _, alt_header, alt_table in plant_tables[1:]:
            alt_values = _extract_from_table(alt_header, alt_table, plant)
            for col, value in alt_values.items():
                if extracted[plant].get(col) is None and value is not None:
                    extracted[plant][col] = value

    return extracted


def _parse_sample_line(line: str) -> tuple[str | None, list[str]]:
    upper = line.upper()
    if "DAY AVG" in upper:
        sample_key = "DayAvg"
    else:
        parts = line.split()
        sample_key = _normalize_sample_key(parts[0] if parts else None)
        if sample_key is None:
            sample_key = _normalize_sample_key(line)
    if sample_key is None:
        return None, []
    tokens = re.findall(r"\d+(?:\.\d+)?", line)
    return sample_key, tokens


def _assign_tokens(record: dict[str, Any], plant: str, sample_key: str, tokens: list[str]) -> None:
    prefix = f"SinterPlant{plant}_{sample_key}"
    for idx, (_, suffix) in enumerate(PLANT_METRICS):
        col = f"{prefix}_{suffix}"
        if idx < len(tokens) and record.get(col) is None:
            record[col] = tokens[idx]


def _extract_from_page_text(page_text: str) -> dict[str, Any]:
    record: dict[str, Any] = {col: None for col in NUMERIC_COLUMNS}
    if not page_text:
        return record

    current_plant: str | None = None
    in_section = False

    for line in page_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        upper = stripped.upper()

        if "SINTER CHEMICAL ANALYSIS" in upper:
            in_section = True
            current_plant = None
            continue

        if not in_section:
            continue

        if upper.startswith("SINTER PLANT-2"):
            current_plant = "2"
            continue
        if upper.startswith("SINTER PLANT-3"):
            current_plant = "3"
            continue

        if current_plant is None:
            continue

        if upper.startswith("NORM(") or upper.startswith("SAMPLE % FE") or upper.startswith("SAMPLE ID"):
            continue

        if "COKE" in upper and "QUALITY" in upper:
            break

        sample_key, tokens = _parse_sample_line(stripped)
        if sample_key and tokens:
            _assign_tokens(record, current_plant, sample_key, tokens)

    return record


def _merge_records(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    merged = dict(primary)
    for col in NUMERIC_COLUMNS:
        if merged.get(col) is None and secondary.get(col) is not None:
            merged[col] = secondary[col]
    return merged


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


def extract_sinter_plant(pdf_path: str, verbose: bool = False) -> dict[str, Any]:
    """Extract sinter plant chemical analysis for one PDF."""
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

    text_values = _extract_from_page_text(page_text)
    plant_values = _find_sinter_plant_tables(tables)
    table_values: dict[str, Any] = {}
    for plant_data in plant_values.values():
        table_values.update(plant_data)

    if table_values:
        record.update(_merge_records(table_values, text_values))
    else:
        if verbose:
            print(
                f"WARNING: sinter plant table not found in {pdf_path}; using text fallback",
                file=sys.stderr,
            )
        record.update(text_values)

    _sanitize_record(record, text_values)

    missing = [col for col in NUMERIC_COLUMNS if record.get(col) is None]
    if missing and verbose:
        print(
            f"WARNING: {os.path.basename(pdf_path)} missing {len(missing)} field(s): "
            + ", ".join(missing[:6])
            + ("..." if len(missing) > 6 else ""),
            file=sys.stderr,
        )

    return record


def stitch_sinter_plant(
    pdf_paths: list[str],
    output_path: str,
    output_format: str = "both",
    replace_zero_with_na: bool = True,
    verbose: bool = False,
) -> Any:
    records = [extract_sinter_plant(path, verbose=verbose) for path in pdf_paths]
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
        description="Extract sinter plant chemical analysis into a day-by-day CSV/Excel file."
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

    print(f"Extracting sinter plant analysis from {len(pdf_paths)} PDF(s)...")
    df = stitch_sinter_plant(
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
