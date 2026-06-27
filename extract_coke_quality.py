#!/usr/bin/env python3
"""Extract BF-8 coke quality from daily production report PDFs.

Reads page 2, locates the COKE QUALITY table (CSP-I through CSP-IV samples plus
BF # 8 stock-house surface mix coke CSR/CRI), and writes one row per report day.

Usage:
    python extract_coke_quality.py --input-dir . --verbose
    python extract_coke_quality.py --from-config --recursive --verbose
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

DEFAULT_OUTPUT = "BF8_coke_quality"

COKE_METRICS: list[tuple[str, str]] = [
    ("Moisture", "Moisture"),
    ("Ash", "Ash"),
    ("V.M", "VM"),
    ("F.C", "FC"),
    ("M-40", "M40"),
    ("M-10", "M10"),
    ("Sulphur", "Sulphur"),
    ("CSR", "CSR"),
    ("CRI", "CRI"),
]

CSP_ROMAN_TO_NUM = {"I": "1", "II": "2", "III": "3", "IV": "4"}

HEADER_ALIASES: dict[str, list[str]] = {
    "Moisture": ["Moisture"],
    "Ash": ["Ash"],
    "V.M": ["V.M", "V.M."],
    "F.C": ["F.C", "F.C."],
    "M-40": ["M-40", "M - 40"],
    "M-10": ["M-10", "M - 10"],
    "Sulphur": ["Sulphur", "Sulfur"],
    "CSR": ["CSR"],
    "CRI": ["CRI"],
}

NUMERIC_COLUMNS = [
    f"CokeQuality_CSP{num}_{suffix}"
    for num in ("1", "2", "3", "4")
    for _, suffix in COKE_METRICS
] + ["CokeQuality_BF8_Mix_CSR", "CokeQuality_BF8_Mix_CRI"]

VALUE_RANGES: dict[str, tuple[float, float]] = {
    **{
        col: (0.0, 20.0)
        for col in NUMERIC_COLUMNS
        if col.endswith("_Moisture")
    },
    **{
        col: (8.0, 20.0)
        for col in NUMERIC_COLUMNS
        if col.endswith("_Ash")
    },
    **{
        col: (0.0, 5.0)
        for col in NUMERIC_COLUMNS
        if col.endswith("_VM")
    },
    **{
        col: (70.0, 92.0)
        for col in NUMERIC_COLUMNS
        if col.endswith("_FC")
    },
    **{
        col: (0.0, 100.0)
        for col in NUMERIC_COLUMNS
        if col.endswith(("_M40", "_M10"))
    },
    **{
        col: (0.0, 2.0)
        for col in NUMERIC_COLUMNS
        if col.endswith("_Sulphur")
    },
    **{
        col: (0.0, 85.0)
        for col in NUMERIC_COLUMNS
        if col.endswith("_CSR")
    },
    **{
        col: (0.0, 50.0)
        for col in NUMERIC_COLUMNS
        if col.endswith("_CRI")
    },
    "CokeQuality_BF8_Mix_CSR": (40.0, 85.0),
    "CokeQuality_BF8_Mix_CRI": (10.0, 45.0),
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


def _csp_number(cell: Any) -> str | None:
    if cell is None:
        return None
    text = str(cell).strip().upper().replace(":", " ").replace("  ", " ")
    match = re.match(r"CSP[-\s]*([IVX]+)", text)
    if not match:
        return None
    return CSP_ROMAN_TO_NUM.get(match.group(1))


def _is_coke_quality_header(row: list[Any]) -> bool:
    normalized = _normalize_label(_row_text(row))
    if not normalized:
        return False
    return (
        "MOISTURE" in normalized
        and "ASH" in normalized
        and "CSR" in normalized
        and "CRI" in normalized
    )


def _trim_coke_row(header_row: list[Any], data_row: list[Any]) -> tuple[list[Any], list[Any]]:
    width = min(10, len(header_row), len(data_row))
    header = header_row[:width]
    if header and not str(header[0] or "").strip():
        header = ["Sample"] + header[1:]
    data = data_row[:width]
    if data and not str(data[0] or "").strip():
        data = [data_row[0] or ""] + data[1:]
    return header, data


def _extract_mapped_values(
    header_row: list[Any],
    data_row: list[Any],
    prefix: str,
) -> dict[str, Any]:
    record: dict[str, Any] = {}
    header, data = _trim_coke_row(header_row, data_row)
    for header_label, suffix in COKE_METRICS:
        aliases = HEADER_ALIASES.get(header_label, [header_label])
        value = _clean_cell(_value_from_header_aliases(header, data, aliases))
        record[f"{prefix}_{suffix}"] = value
    return record


def _is_bf8_mix_summary_row(row: list[Any]) -> bool:
    if not row or len(row) < 10:
        return False
    if row[0] is not None and str(row[0]).strip():
        return False
    for cell in row[1:8]:
        if cell is not None and str(cell).strip():
            return False
    csr = _clean_cell(row[8])
    cri = _clean_cell(row[9])
    return csr is not None or cri is not None


def _extract_bf8_mix_from_table(table: list[list[Any]]) -> tuple[Any, Any]:
    for row in reversed(table):
        if not _is_bf8_mix_summary_row(row):
            continue
        return _clean_cell(row[8]), _clean_cell(row[9])
    return None, None


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


def _find_coke_quality_table(
    tables: list[list[list[Any]]],
) -> tuple[list[Any] | None, dict[str, list[Any]], list[list[Any]] | None]:
    for table in tables:
        header_row = next((row for row in table if _is_coke_quality_header(row)), None)
        if not header_row:
            continue

        csp_rows: dict[str, list[Any]] = {}
        for row in table:
            csp_num = _csp_number(row[0] if row else None)
            if csp_num:
                csp_rows[csp_num] = row

        if csp_rows:
            return header_row, csp_rows, table
    return None, {}, None


def _extract_from_table(
    header_row: list[Any],
    csp_rows: dict[str, list[Any]],
    table: list[list[Any]],
) -> dict[str, Any]:
    record: dict[str, Any] = {col: None for col in NUMERIC_COLUMNS}

    for csp_num, data_row in csp_rows.items():
        prefix = f"CokeQuality_CSP{csp_num}"
        record.update(_extract_mapped_values(header_row, data_row, prefix))

    csr, cri = _extract_bf8_mix_from_table(table)
    record["CokeQuality_BF8_Mix_CSR"] = csr
    record["CokeQuality_BF8_Mix_CRI"] = cri
    return record


def _parse_csp_line(line: str) -> tuple[str | None, list[str]]:
    match = re.match(r"CSP[-\s]*(I{1,3}|IV)\s*:", line.strip(), re.IGNORECASE)
    if not match:
        return None, []
    csp_num = CSP_ROMAN_TO_NUM.get(match.group(1).upper())
    tokens = re.findall(r"\d+(?:\.\d+)?", line[match.end() :])
    return csp_num, tokens


def _assign_csp_tokens(record: dict[str, Any], csp_num: str, tokens: list[str]) -> None:
    prefix = f"CokeQuality_CSP{csp_num}"
    if len(tokens) >= 9:
        for idx, (_, suffix) in enumerate(COKE_METRICS):
            record[f"{prefix}_{suffix}"] = tokens[idx]
    elif len(tokens) == 7:
        for idx, (_, suffix) in enumerate(COKE_METRICS[:7]):
            record[f"{prefix}_{suffix}"] = tokens[idx]
    elif len(tokens) == 5:
        record[f"{prefix}_Moisture"] = tokens[0]
        record[f"{prefix}_Ash"] = tokens[1]
        record[f"{prefix}_VM"] = tokens[2]
        record[f"{prefix}_FC"] = tokens[3]
        record[f"{prefix}_Sulphur"] = tokens[4]
    elif len(tokens) == 4:
        record[f"{prefix}_Moisture"] = tokens[0]
        record[f"{prefix}_Ash"] = tokens[1]
        record[f"{prefix}_VM"] = tokens[2]
        record[f"{prefix}_FC"] = tokens[3]
    else:
        for idx, (_, suffix) in enumerate(COKE_METRICS):
            if idx < len(tokens):
                record[f"{prefix}_{suffix}"] = tokens[idx]


def _extract_bf8_mix_from_text(page_text: str) -> tuple[Any, Any]:
    for line in page_text.splitlines():
        if not re.search(r"BF\s*#\s*8\s+STOCK\s+HOUSE", line, re.IGNORECASE):
            continue
        match = re.search(
            r"=>\s*(\d+(?:\.\d+)?)\s+(\d+(?:\.\d+)?)\s*$",
            line.strip(),
            re.IGNORECASE,
        )
        if not match:
            continue
        csr, cri = match.group(1), match.group(2)
        if _is_plausible("CokeQuality_BF8_Mix_CSR", csr) and _is_plausible(
            "CokeQuality_BF8_Mix_CRI", cri
        ):
            return csr, cri
        break
    return None, None


def _extract_from_page_text(page_text: str) -> dict[str, Any]:
    record: dict[str, Any] = {col: None for col in NUMERIC_COLUMNS}
    if not page_text:
        return record

    in_section = False
    for line in page_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        upper = stripped.upper()

        if "COKE QUALITY" in upper:
            in_section = True
            continue

        if in_section and ("COAL BLEND" in upper or "SINTER CHEMICAL" in upper):
            break

        if not in_section:
            continue

        csp_num, tokens = _parse_csp_line(stripped)
        if csp_num and tokens:
            _assign_csp_tokens(record, csp_num, tokens)
            continue

        if re.search(r"BF\s*#\s*8\s+STOCK\s+HOUSE", stripped, re.IGNORECASE):
            csr, cri = _extract_bf8_mix_from_text(stripped)
            if csr is not None:
                record["CokeQuality_BF8_Mix_CSR"] = csr
            if cri is not None:
                record["CokeQuality_BF8_Mix_CRI"] = cri

    return record


def _merge_records(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    merged = dict(primary)
    for col in NUMERIC_COLUMNS:
        if merged.get(col) is None and secondary.get(col) is not None:
            merged[col] = secondary[col]
    return merged


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


def extract_coke_quality(pdf_path: str, verbose: bool = False) -> dict[str, Any]:
    """Extract BF-8 coke quality metrics for one PDF."""
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
    header_row, csp_rows, table = _find_coke_quality_table(tables)

    if header_row and csp_rows and table is not None:
        table_values = _extract_from_table(header_row, csp_rows, table)
        record.update(_merge_records(table_values, text_values))
    else:
        if verbose:
            print(
                f"WARNING: coke quality table not found in {pdf_path}; using text fallback",
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


def stitch_coke_quality(
    pdf_paths: list[str],
    output_path: str,
    output_format: str = "both",
    replace_zero_with_na: bool = True,
    verbose: bool = False,
) -> Any:
    records = [extract_coke_quality(path, verbose=verbose) for path in pdf_paths]
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
        description="Extract BF-8 coke quality into a day-by-day CSV/Excel file."
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

    print(f"Extracting coke quality from {len(pdf_paths)} PDF(s)...")
    df = stitch_coke_quality(
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
