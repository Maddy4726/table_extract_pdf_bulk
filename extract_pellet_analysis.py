#!/usr/bin/env python3
"""Extract BF-8 pellet chemical and sieve analysis from daily production report PDFs.

Reads page 2, locates the PELLET CHEMICAL AND SEIVE ANALYSIS table, and writes
one row per report day for BF # 8.

Usage:
    python extract_pellet_analysis.py --input-dir . --verbose
    python extract_pellet_analysis.py --from-config --recursive --verbose
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

DEFAULT_OUTPUT = "BF8_pellet_analysis"

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

PELLET_HEADER_ALIASES: dict[str, list[str]] = {
    "Fe": ["Fe", "Fe (%)"],
    "SiO2": ["SiO2", "SiO2 (%)"],
    "Al2O3": ["Al2O3", "Al2O3(%)", "Al2O3 (%)"],
    "CaO": ["CaO", "CaO (%)"],
    "MgO": ["MgO", "MgO (%)"],
    "+ 10 MM": ["+ 10 MM", "+10 MM", "+ 10MM", "+10MM"],
    "- 5 MM": ["- 5 MM", "-5 MM", "- 5MM", "-5MM"],
    "M.Size": ["M.Size", "M. SIZE", "M.SIZE"],
    "Basicity": ["Basicity", "BASICITY"],
}

NUMERIC_COLUMNS = [col for _, col in PELLET_COLUMNS]

VALUE_RANGES: dict[str, tuple[float, float]] = {
    "Pellet_Fe_pct": (50.0, 70.0),
    "Pellet_SiO2_pct": (0.5, 15.0),
    "Pellet_Al2O3_pct": (0.5, 10.0),
    "Pellet_CaO_pct": (0.0, 5.0),
    "Pellet_MgO_pct": (0.0, 5.0),
    "Pellet_plus10mm": (0.0, 100.0),
    "Pellet_minus5mm": (0.0, 100.0),
    "Pellet_MSize": (0.0, 100.0),
    "Pellet_Basicity": (0.0, 25.0),
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


def _is_pellet_header(row: list[Any]) -> bool:
    normalized = _normalize_label(_row_text(row))
    if not normalized:
        return False
    if "SAMPLE" in normalized or "FEO" in normalized or "FCE" in normalized:
        return False
    if "MOIST" in normalized:
        return False
    return (
        "FE" in normalized
        and "SIO2" in normalized
        and "AL2O3" in normalized
        and "CAO" in normalized
        and "BASICITY" in normalized
        and ("+ 10" in normalized or "+10" in normalized)
    )


def _is_pellet_title_row(row: list[Any]) -> bool:
    if not row or not row[0]:
        return False
    return "PELLET" in str(row[0]).upper()


def _is_pellet_header_line(line: str) -> bool:
    upper = line.upper()
    return bool(re.search(r"\bFE\b", upper)) and "SIO2" in upper and "AL2O3" in upper and "CAO" in upper


def _numeric_cells(row: list[Any]) -> list[str]:
    values: list[str] = []
    for cell in row:
        cleaned = _clean_cell(cell)
        if cleaned is not None and re.fullmatch(r"-?\d+(?:\.\d+)?", str(cleaned)):
            values.append(str(cleaned))
    return values


def _is_numeric_data_row(row: list[Any]) -> bool:
    if not row or _is_pellet_title_row(row):
        return False
    label = _normalize_label(row[0]) if row[0] else ""
    if label.startswith("BF") and not re.search(r"BF\s*#\s*8\b", str(row[0]), re.IGNORECASE):
        return False
    return len(_numeric_cells(row)) >= 3


def _title_targets_bf8(table: list[list[Any]]) -> bool:
    for row in table:
        if _is_pellet_title_row(row):
            return bool(re.search(r"BF\s*#\s*8\b", str(row[0]), re.IGNORECASE))
    return False


def _find_pellet_data_row(
    table: list[list[Any]],
    header_row: list[Any],
) -> list[Any] | None:
    """Return the BF-8 pellet data row, ignoring title rows that also mention BF # 8."""
    for row in table:
        if not row or not row[0] or _is_pellet_title_row(row):
            continue
        label = str(row[0]).strip()
        if re.fullmatch(r"BF\s*#\s*8\s*=>?", label, re.IGNORECASE) and len(_numeric_cells(row)) >= 3:
            return row

    header_idx = table.index(header_row)
    for row in table[header_idx + 1 :]:
        if _is_numeric_data_row(row):
            if row[0] and str(row[0]).strip() and not re.fullmatch(
                r"BF\s*#\s*8\s*=>?", str(row[0]).strip(), re.IGNORECASE
            ):
                # Unlabeled numeric row right under the header.
                if _title_targets_bf8(table) or not row[0] or not str(row[0]).strip().startswith("BF"):
                    return row
            elif re.fullmatch(r"BF\s*#\s*8\s*=>?", str(row[0]).strip(), re.IGNORECASE):
                return row

    return None


def _is_data_row(row: list[Any]) -> bool:
    return _is_numeric_data_row(row)


def _extract_mapped_values(
    header_row: list[Any] | None,
    data_row: list[Any] | None,
) -> dict[str, Any]:
    record: dict[str, Any] = {col: None for col in NUMERIC_COLUMNS}
    if not header_row or not data_row:
        return record

    for header_label, out_col in PELLET_COLUMNS:
        aliases = PELLET_HEADER_ALIASES.get(header_label, [header_label])
        value = _clean_cell(_value_from_header_aliases(header_row, data_row, aliases))
        record[out_col] = value
    return record


def _find_pellet_table(
    tables: list[list[list[Any]]],
) -> tuple[list[Any] | None, list[Any] | None]:
    for table in tables:
        header_row = next((row for row in table if _is_pellet_header(row)), None)
        if header_row is None:
            continue

        data_row = _find_pellet_data_row(table, header_row)
        if data_row is None:
            header_idx = table.index(header_row)
            for row in table[header_idx + 1 :]:
                if _is_numeric_data_row(row):
                    data_row = row
                    break

        if header_row and data_row:
            return header_row, data_row
    return None, None


def _tokenize_pellet_values(text: str) -> list[str]:
    tokens = re.findall(r"#DIV/0!|#DIV/0|\d+(?:\.\d+)?", text)
    return [token for token in tokens if token.upper() not in INVALID_TOKENS]


def _assign_tokens_to_columns(tokens: list[str]) -> dict[str, Any]:
    record: dict[str, Any] = {col: None for col in NUMERIC_COLUMNS}
    if not tokens:
        return record

    try:
        floats = [float(token) for token in tokens]
    except ValueError:
        return record

    if len(floats) >= 6 and floats[1] >= 3.0:
        for idx, (_, col) in enumerate(PELLET_COLUMNS):
            if idx < len(tokens):
                record[col] = tokens[idx]
        return record

    if floats[0] >= 15.0:
        sieve_cols = ["Pellet_plus10mm", "Pellet_minus5mm", "Pellet_MSize"]
        for idx, col in enumerate(sieve_cols):
            if idx < len(tokens):
                record[col] = tokens[idx]
    return record


def _extract_from_page_text(page_text: str) -> dict[str, Any]:
    record: dict[str, Any] = {col: None for col in NUMERIC_COLUMNS}
    if not page_text:
        return record

    in_section = False
    title_has_bf8 = False
    past_header = False

    for line in page_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        upper = stripped.upper()

        if "PELLET CHEMICAL" in upper:
            in_section = True
            title_has_bf8 = bool(re.search(r"BF\s*#\s*8\b", stripped, re.IGNORECASE))
            past_header = False
            continue

        if in_section and ("SKIP IRON ORE" in upper or "SKIP I/ORE" in upper):
            break

        if not in_section:
            continue

        match = re.search(r"BF\s*#\s*8\s*=>?\s*(.*)$", stripped, re.IGNORECASE)
        if match:
            return _assign_tokens_to_columns(_tokenize_pellet_values(match.group(1)))

        if _is_pellet_header_line(stripped):
            past_header = True
            continue

        if past_header and title_has_bf8:
            if re.search(r"BF\s*#\s*[47]\b", stripped, re.IGNORECASE):
                break
            if re.search(r"BF\s*#\s*\d", stripped, re.IGNORECASE):
                continue
            tokens = _tokenize_pellet_values(stripped)
            if len(tokens) >= 3:
                return _assign_tokens_to_columns(tokens)

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


def _merge_records(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    merged = dict(primary)
    for col in NUMERIC_COLUMNS:
        if merged.get(col) is None and secondary.get(col) is not None:
            merged[col] = secondary[col]
    return merged


def extract_pellet_analysis(pdf_path: str, verbose: bool = False) -> dict[str, Any]:
    """Extract BF-8 pellet chemical and sieve values for one PDF."""
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

    header_row, data_row = _find_pellet_table(tables)
    if header_row and data_row:
        table_values = _extract_mapped_values(header_row, data_row)
        record.update(_merge_records(text_values, table_values))
    else:
        if verbose:
            print(
                f"WARNING: pellet table not found in {pdf_path}; using text fallback",
                file=sys.stderr,
            )
        record.update(text_values)

    _sanitize_record(record, text_values)

    missing = [col for col in NUMERIC_COLUMNS if record.get(col) is None]
    if missing and verbose:
        print(
            f"WARNING: {os.path.basename(pdf_path)} missing {len(missing)} field(s): "
            + ", ".join(missing),
            file=sys.stderr,
        )

    return record


def stitch_pellet_analysis(
    pdf_paths: list[str],
    output_path: str,
    output_format: str = "both",
    replace_zero_with_na: bool = True,
    verbose: bool = False,
) -> Any:
    records = [extract_pellet_analysis(path, verbose=verbose) for path in pdf_paths]
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
        description="Extract BF-8 pellet chemical and sieve analysis into a day-by-day CSV/Excel file."
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

    print(f"Extracting pellet analysis from {len(pdf_paths)} PDF(s)...")
    df = stitch_pellet_analysis(
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
