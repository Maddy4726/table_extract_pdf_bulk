#!/usr/bin/env python3
"""Extract BF-8 skip sinter chemical analysis from daily production report PDFs.

Reads page 2, locates the SKIP SINTER table (% Fe, SiO2, Al2O3, CaO, MgO,
Basicity for BF # 8), and writes one row per report day.

Note: many newer daily PDFs omit this table and only report skip-sinter fines.
This script targets the chemical composition block when it is present.

Usage:
    python extract_skip_sinter.py --input-dir . --verbose
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import re
import sys
from typing import Any

import pdfplumber

from extract_bf8_daily import (
    _extract_page_tables,
    _is_bf8_label,
    _normalize_label,
    _value_from_header_aliases
)
from extract_cli import add_input_args, add_output_args, add_verbose_arg, resolve_pdf_paths
from extract_table_utils import (
    DEFAULT_PDF_PATTERN,
    assign_report_date,
    stitch_records,
)

DEFAULT_OUTPUT = "BF8_skip_sinter"

SINTER_COLUMNS: list[tuple[str, str]] = [
    ("% Fe", "SkipSinter_Fe_pct"),
    ("% SiO2", "SkipSinter_SiO2_pct"),
    ("% Al2O3", "SkipSinter_Al2O3_pct"),
    ("% CaO", "SkipSinter_CaO_pct"),
    ("% MgO", "SkipSinter_MgO_pct"),
    ("BASICITY", "SkipSinter_Basicity"),
]

HEADER_ALIASES: dict[str, list[str]] = {
    "% Fe": ["% Fe", "% FE", "Fe", "Fe (%)"],
    "% SiO2": ["% SiO2", "% SIO2", "SiO2", "SiO2 (%)"],
    "% Al2O3": ["% Al2O3", "% AL2O3", "Al2O3", "Al2O3(%)"],
    "% CaO": ["% CaO", "% CAO", "CaO", "CaO (%)"],
    "% MgO": ["% MgO", "% MGO", "MgO", "MgO (%)"],
    "BASICITY": ["BASICITY", "Basicity"],
}

NUMERIC_COLUMNS = [col for _, col in SINTER_COLUMNS]

VALUE_RANGES: dict[str, tuple[float, float]] = {
    "SkipSinter_Fe_pct": (45.0, 65.0),
    "SkipSinter_SiO2_pct": (3.0, 15.0),
    "SkipSinter_Al2O3_pct": (1.0, 8.0),
    "SkipSinter_CaO_pct": (8.0, 20.0),
    "SkipSinter_MgO_pct": (1.0, 6.0),
    "SkipSinter_Basicity": (1.0, 2.5),
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


def _is_skip_sinter_title(text: str) -> bool:
    upper = text.upper().strip()
    if "FINE" in upper or "FINES" in upper:
        return False
    return upper == "SKIP SINTER" or upper.startswith("SKIP SINTER\n")


def _is_skip_sinter_header(row: list[Any]) -> bool:
    normalized = _normalize_label(_row_text(row))
    if not normalized:
        return False
    if any(token in normalized for token in ("SAMPLE", "FEO", "FCE", "MOIST", "SHIFT")):
        return False
    if "+ 10" in normalized or "+10" in normalized or "- 10 MM" in normalized:
        return False
    return (
        "FE" in normalized
        and "SIO2" in normalized
        and "AL2O3" in normalized
        and "CAO" in normalized
        and "MGO" in normalized
        and "BASICITY" in normalized
    )


def _numeric_cells(row: list[Any]) -> list[str]:
    values: list[str] = []
    for cell in row:
        cleaned = _clean_cell(cell)
        if cleaned is not None and re.fullmatch(r"-?\d+(?:\.\d+)?", str(cleaned)):
            values.append(str(cleaned))
    return values


def _is_bf8_data_row(row: list[Any]) -> bool:
    if not row or not row[0]:
        return False
    return bool(re.fullmatch(r"BF\s*#\s*8\s*=>?", str(row[0]).strip(), re.IGNORECASE))


def _find_bf8_data_row(table: list[list[Any]], header_row: list[Any]) -> list[Any] | None:
    for row in table:
        if _is_bf8_data_row(row) and len(_numeric_cells(row)) >= 3:
            return row

    header_idx = table.index(header_row)
    for row in table[header_idx + 1 :]:
        if not row or not row[0]:
            continue
        label = str(row[0]).strip().upper()
        if label.startswith("BF") and "8" not in label:
            continue
        if label.startswith("AVG"):
            continue
        if _is_bf8_label(row[0]) and len(_numeric_cells(row)) >= 3:
            return row
    return None


def _is_skip_sinter_header_line(line: str) -> bool:
    normalized = _normalize_label(line)
    if not normalized:
        return False
    if any(token in normalized for token in ("SAMPLE", "FEO", "FCE", "MOIST", "SHIFT", "FINES")):
        return False
    if "+ 10" in normalized or "+10" in normalized:
        return False
    return (
        "FE" in normalized
        and "SIO2" in normalized
        and "AL2O3" in normalized
        and "CAO" in normalized
        and "MGO" in normalized
        and "BASICITY" in normalized
    )


def _find_skip_sinter_table(
    tables: list[list[list[Any]]],
) -> tuple[list[Any] | None, list[Any] | None]:
    candidates: list[tuple[list[Any], list[Any], int]] = []

    for table in tables:
        header_row = next((row for row in table if _is_skip_sinter_header(row)), None)
        if header_row is None:
            continue

        data_row = _find_bf8_data_row(table, header_row)
        if not data_row:
            continue

        score = 0
        if any(row and row[0] and _is_skip_sinter_title(str(row[0])) for row in table):
            score += 10
        if _is_bf8_data_row(data_row):
            score += 5
        score += len(_numeric_cells(data_row))

        candidates.append((header_row, data_row, score))

    if not candidates:
        return None, None

    header_row, data_row, _ = max(candidates, key=lambda item: item[2])
    return header_row, data_row


def _extract_mapped_values(
    header_row: list[Any] | None,
    data_row: list[Any] | None,
) -> dict[str, Any]:
    record: dict[str, Any] = {col: None for col in NUMERIC_COLUMNS}
    if not header_row or not data_row:
        return record

    for header_label, out_col in SINTER_COLUMNS:
        aliases = HEADER_ALIASES.get(header_label, [header_label])
        value = _clean_cell(_value_from_header_aliases(header_row, data_row, aliases))
        record[out_col] = value
    return record


def _tokenize_values(text: str) -> list[str]:
    tokens = re.findall(r"#DIV/0!|#DIV/0|\d+(?:\.\d+)?", text)
    return [token for token in tokens if token.upper() not in INVALID_TOKENS]


def _assign_tokens_to_columns(tokens: list[str]) -> dict[str, Any]:
    record: dict[str, Any] = {col: None for col in NUMERIC_COLUMNS}
    for idx, (_, col) in enumerate(SINTER_COLUMNS):
        if idx < len(tokens):
            record[col] = tokens[idx]
    return record


def _extract_from_page_text(page_text: str) -> dict[str, Any]:
    record: dict[str, Any] = {col: None for col in NUMERIC_COLUMNS}
    if not page_text:
        return record

    in_section = False
    past_header = False

    for line in page_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        upper = stripped.upper()

        if _is_skip_sinter_title(stripped):
            in_section = True
            past_header = False
            continue

        if in_section and ("% FINES IN BF SKIP SINTER" in upper or "SKIP IRON ORE" in upper):
            break

        if not in_section:
            continue

        match = re.search(r"BF\s*#\s*8\s*=>?\s*(.*)$", stripped, re.IGNORECASE)
        if match:
            return _assign_tokens_to_columns(_tokenize_values(match.group(1)))

        if _is_skip_sinter_header_line(stripped):
            past_header = True
            continue

        if past_header:
            if re.search(r"BF\s*#\s*[45]\b", stripped, re.IGNORECASE):
                continue
            if re.search(r"BF\s*#\s*7\b", stripped, re.IGNORECASE):
                break
            if re.search(r"BF\s*#\s*8\b", stripped, re.IGNORECASE):
                after = re.sub(r"^.*BF\s*#\s*8\s*=>?\s*", "", stripped, count=1, flags=re.IGNORECASE)
                tokens = _tokenize_values(after)
                if len(tokens) >= 3:
                    return _assign_tokens_to_columns(tokens)
                continue
            tokens = _tokenize_values(stripped)
            if len(tokens) >= 6 and not re.search(r"BF\s*#", stripped, re.IGNORECASE):
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


def extract_skip_sinter(pdf_path: str, verbose: bool = False) -> dict[str, Any]:
    """Extract BF-8 skip sinter chemical values for one PDF."""
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
    header_row, data_row = _find_skip_sinter_table(tables)

    if header_row and data_row:
        table_values = _extract_mapped_values(header_row, data_row)
        record.update(_merge_records(text_values, table_values))
    else:
        if verbose:
            print(
                f"WARNING: skip sinter chemical table not found in {pdf_path}; using text fallback",
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


def stitch_skip_sinter(
    pdf_paths: list[str],
    output_path: str,
    output_format: str = "both",
    replace_zero_with_na: bool = True,
    verbose: bool = False,
) -> Any:
    records = [extract_skip_sinter(path, verbose=verbose) for path in pdf_paths]
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
        description="Extract BF-8 skip sinter chemical analysis into a day-by-day CSV/Excel file."
    )
    add_input_args(parser)
    add_output_args(parser, DEFAULT_OUTPUT)
    add_verbose_arg(parser)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pdf_paths = resolve_pdf_paths(args)

    print(f"Extracting skip sinter chemical analysis from {len(pdf_paths)} PDF(s)...")
    df = stitch_skip_sinter(
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
