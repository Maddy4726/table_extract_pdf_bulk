#!/usr/bin/env python3
"""Extract BF-8 skip sinter and skip coke fines from daily production report PDFs.

Reads page 2, locates the % FINES IN BF SKIP SINTER / SKIP COKE tables, and
writes one row per report day for BF # 8.

Usage:
    python extract_skip_fines.py --input-dir . --verbose
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

DEFAULT_OUTPUT = "BF8_skip_fines"

SINTER_FINES_COLUMNS: list[tuple[str, str]] = [
    ("-10 mm", "SkipSinterFines_minus10mm"),
    ("- 5 mm", "SkipSinterFines_minus5mm"),
    ("M.Size", "SkipSinterFines_MSize"),
    ("SHIFT A", "SkipSinterFines_ShiftA"),
    ("SHIFT B", "SkipSinterFines_ShiftB"),
    ("SHIFT C", "SkipSinterFines_ShiftC"),
    ("TOTAL Fe", "SkipSinterFines_TotalFe"),
]

COKE_FINES_COLUMNS: list[tuple[str, str]] = [
    ("-40 mm", "SkipCokeFines_minus40mm"),
    ("- 25 mm", "SkipCokeFines_minus25mm"),
    ("M.Size", "SkipCokeFines_MSize"),
]

SINTER_HEADER_ALIASES: dict[str, list[str]] = {
    "-10 mm": ["-10 mm", "- 10 mm", "-10MM"],
    "- 5 mm": ["- 5 mm", "-5 mm", "- 5MM"],
    "M.Size": ["M.Size", "M. SIZE", "M.SIZE"],
    "SHIFT A": ["SHIFT A"],
    "SHIFT B": ["SHIFT B"],
    "SHIFT C": ["SHIFT C"],
    "TOTAL Fe": ["TOTAL Fe", "TOTAL FE", "TOTAL  FE"],
}

COKE_HEADER_ALIASES: dict[str, list[str]] = {
    "-40 mm": ["-40 mm", "- 40 mm", "-40MM"],
    "- 25 mm": ["- 25 mm", "-25 mm", "- 25MM"],
    "M.Size": ["M.Size", "M. SIZE", "M.SIZE"],
}

NUMERIC_COLUMNS = [col for _, col in SINTER_FINES_COLUMNS + COKE_FINES_COLUMNS]

VALUE_RANGES: dict[str, tuple[float, float]] = {
    "SkipSinterFines_minus10mm": (0.0, 100.0),
    "SkipSinterFines_minus5mm": (0.0, 100.0),
    "SkipSinterFines_MSize": (0.0, 100.0),
    "SkipSinterFines_ShiftA": (0.0, 100.0),
    "SkipSinterFines_ShiftB": (0.0, 100.0),
    "SkipSinterFines_ShiftC": (0.0, 100.0),
    "SkipSinterFines_TotalFe": (0.0, 100.0),
    "SkipCokeFines_minus40mm": (0.0, 100.0),
    "SkipCokeFines_minus25mm": (0.0, 100.0),
    "SkipCokeFines_MSize": (0.0, 100.0),
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


def _is_fce_header_cell(cell: Any) -> bool:
    return bool(cell and "FCE" in str(cell).upper())


def _find_split_index(header_row: list[Any]) -> int | None:
    """Return the column index of the second Fce.No. header in merged sinter/coke tables."""
    fce_seen = 0
    for idx, cell in enumerate(header_row):
        if _is_fce_header_cell(cell):
            fce_seen += 1
            if fce_seen == 2:
                return idx
    return None


def _find_coke_start_index(header_row: list[Any]) -> int | None:
    for idx, cell in enumerate(header_row):
        if cell and re.search(r"-\s*40\s*mm", str(cell), re.IGNORECASE):
            return idx
    return None


def _bf8_positions(row: list[Any]) -> list[int]:
    positions: list[int] = []
    for idx, cell in enumerate(row):
        if cell and _is_bf8_label(cell):
            positions.append(idx)
    return positions


def _find_bf8_data_row(table: list[list[Any]]) -> list[Any] | None:
    for row in table:
        if row and row[0] and _is_bf8_label(row[0]):
            return row
    return None


def _is_sinter_fines_header(row: list[Any]) -> bool:
    normalized = _normalize_label(_row_text(row))
    if "FCE" not in normalized:
        return False
    if not any(token in normalized for token in ("-10", "- 10")):
        return False
    if any(token in normalized for token in ("- 5", "-5")):
        return True
    return "M.SIZE" in normalized and "SHIFT" in normalized


def _is_coke_fines_header(row: list[Any]) -> bool:
    normalized = _normalize_label(_row_text(row))
    if "FCE" not in normalized:
        return False
    return any(token in normalized for token in ("-40", "- 40")) and any(
        token in normalized for token in ("-25", "- 25")
    )


def _extract_mapped_values(
    header_row: list[Any],
    data_row: list[Any],
    column_map: list[tuple[str, str]],
    header_aliases: dict[str, list[str]],
) -> dict[str, Any]:
    record: dict[str, Any] = {col: None for _, col in column_map}
    for header_label, out_col in column_map:
        aliases = header_aliases.get(header_label, [header_label])
        value = _clean_cell(_value_from_header_aliases(header_row, data_row, aliases))
        record[out_col] = value
    return record


def _slice_row_pair(
    header_row: list[Any],
    data_row: list[Any],
    start: int,
    end: int | None = None,
) -> tuple[list[Any], list[Any]]:
    end = len(header_row) if end is None else end
    header_slice = [header_row[0] if start == 0 else "Fce.No."] + header_row[start:end]
    if _is_bf8_label(data_row[0]):
        data_slice = [data_row[0]] + data_row[start:end]
    else:
        data_slice = ["BF # 8"] + data_row[start:end]
    return header_slice, data_slice


def _extract_from_merged_table(
    header_row: list[Any],
    data_row: list[Any],
) -> dict[str, Any]:
    record: dict[str, Any] = {col: None for col in NUMERIC_COLUMNS}
    split_idx = _find_split_index(header_row)
    bf8_positions = _bf8_positions(data_row)

    if split_idx is not None:
        left_header, left_data = _slice_row_pair(header_row, data_row, 1, split_idx)
        right_header, right_data = _slice_row_pair(header_row, data_row, split_idx + 1)
        record.update(_extract_mapped_values(left_header, left_data, SINTER_FINES_COLUMNS, SINTER_HEADER_ALIASES))
        record.update(_extract_mapped_values(right_header, right_data, COKE_FINES_COLUMNS, COKE_HEADER_ALIASES))
        return record

    if len(bf8_positions) >= 2:
        split_at = bf8_positions[1]
        left_header, left_data = _slice_row_pair(header_row, data_row, 1, split_at)
        right_header, right_data = _slice_row_pair(header_row, data_row, split_at + 1)
        record.update(_extract_mapped_values(left_header, left_data, SINTER_FINES_COLUMNS, SINTER_HEADER_ALIASES))
        record.update(_extract_mapped_values(right_header, right_data, COKE_FINES_COLUMNS, COKE_HEADER_ALIASES))
        return record

    normalized = _normalize_label(_row_text(header_row))
    if _is_sinter_fines_header(header_row) and not any(
        token in normalized for token in ("-40", "- 40")
    ):
        record.update(_extract_mapped_values(header_row, data_row, SINTER_FINES_COLUMNS, SINTER_HEADER_ALIASES))
    elif _is_coke_fines_header(header_row) and not any(
        token in normalized for token in ("-10", "- 10")
    ):
        record.update(_extract_mapped_values(header_row, data_row, COKE_FINES_COLUMNS, COKE_HEADER_ALIASES))
    else:
        # sample_report-style wide table: sinter fines, ore sieve, coke fines.
        split_at = _find_split_index(header_row)
        sinter_end = split_at if split_at is not None else 4
        sinter_header = ["Fce.No."] + header_row[1:sinter_end]
        sinter_data = [data_row[0]] + data_row[1:sinter_end]
        record.update(
            _extract_mapped_values(
                sinter_header,
                sinter_data,
                SINTER_FINES_COLUMNS[:3],
                SINTER_HEADER_ALIASES,
            )
        )

        coke_start = _find_coke_start_index(header_row)
        if coke_start is not None:
            coke_header = ["Fce.No."] + header_row[coke_start : coke_start + 3]
            coke_data = [data_row[0]] + data_row[coke_start : coke_start + 3]
            record.update(_extract_mapped_values(coke_header, coke_data, COKE_FINES_COLUMNS, COKE_HEADER_ALIASES))

    return record


def _find_fines_tables(
    tables: list[list[list[Any]]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    sinter_values: dict[str, Any] = {col: None for _, col in SINTER_FINES_COLUMNS}
    coke_values: dict[str, Any] = {col: None for _, col in COKE_FINES_COLUMNS}

    for table in tables:
        for header_row in table:
            if not header_row:
                continue
            if not (_is_sinter_fines_header(header_row) or _is_coke_fines_header(header_row)):
                continue
            data_row = _find_bf8_data_row(table)
            if not data_row:
                break

            extracted = _extract_from_merged_table(header_row, data_row)
            for _, out_col in SINTER_FINES_COLUMNS:
                if sinter_values[out_col] is None and extracted.get(out_col) is not None:
                    sinter_values[out_col] = extracted[out_col]
            for _, out_col in COKE_FINES_COLUMNS:
                if coke_values[out_col] is None and extracted.get(out_col) is not None:
                    coke_values[out_col] = extracted[out_col]
            break

    return sinter_values, coke_values


def _tokenize_values(text: str) -> list[str]:
    return re.findall(r"#DIV/0!|#DIV/0|\d+(?:\.\d+)?", text)


def _parse_bf8_number_chunks(line: str) -> list[list[str]]:
    chunks: list[list[str]] = []
    for part in re.split(r"(BF\s*#\s*\d+)", line, flags=re.IGNORECASE):
        if not part or not part.strip():
            continue
        if re.fullmatch(r"BF\s*#\s*\d+", part.strip(), re.IGNORECASE):
            continue
        tokens = [t for t in _tokenize_values(part) if t.upper() not in INVALID_TOKENS]
        if tokens:
            chunks.append(tokens)
    return chunks


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

        if "% FINES IN BF SKIP SINTER" in upper:
            in_section = True
            continue

        if in_section and upper.startswith("COKE QUALITY"):
            break

        if not in_section:
            continue

        if not re.search(r"BF\s*#\s*8\b", stripped, re.IGNORECASE):
            continue

        chunks = _parse_bf8_number_chunks(stripped)
        if not chunks:
            continue

        if len(chunks) == 1:
            tokens = chunks[0]
            if len(tokens) >= 9:
                # Wide layout: sinter (3) | iron ore sieve (3) | coke (3)
                record["SkipSinterFines_minus10mm"] = tokens[0]
                record["SkipSinterFines_minus5mm"] = tokens[1]
                record["SkipSinterFines_MSize"] = tokens[2]
                record["SkipCokeFines_minus40mm"] = tokens[6]
                record["SkipCokeFines_minus25mm"] = tokens[7]
                record["SkipCokeFines_MSize"] = tokens[8]
            elif len(tokens) >= 6:
                _assign_sinter_tokens(record, tokens)
            elif len(tokens) in (4, 5):
                _assign_sinter_tokens(record, tokens)
            elif len(tokens) == 3:
                record["SkipCokeFines_minus40mm"] = tokens[0]
                record["SkipCokeFines_minus25mm"] = tokens[1]
                record["SkipCokeFines_MSize"] = tokens[2]
        elif len(chunks) >= 2:
            sinter_tokens, coke_tokens = chunks[0], chunks[1]
            _assign_sinter_tokens(record, sinter_tokens)
            for idx, (_, col) in enumerate(COKE_FINES_COLUMNS):
                if idx < len(coke_tokens):
                    record[col] = coke_tokens[idx]
        break

    return record


def _assign_sinter_tokens(record: dict[str, Any], tokens: list[str]) -> None:
    if len(tokens) >= 6:
        for idx, (_, col) in enumerate(SINTER_FINES_COLUMNS):
            if idx < len(tokens):
                record[col] = tokens[idx]
    elif len(tokens) in (4, 5):
        record["SkipSinterFines_minus10mm"] = tokens[0]
        record["SkipSinterFines_minus5mm"] = tokens[1]
        record["SkipSinterFines_MSize"] = tokens[2]
        record["SkipSinterFines_TotalFe"] = tokens[3]
    elif len(tokens) == 3:
        record["SkipSinterFines_minus10mm"] = tokens[0]
        record["SkipSinterFines_minus5mm"] = tokens[1]
        record["SkipSinterFines_MSize"] = tokens[2]


def _merge_records(primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
    merged = dict(primary)
    for col in NUMERIC_COLUMNS:
        if merged.get(col) is None and secondary.get(col) is not None:
            merged[col] = secondary[col]

    if merged.get("SkipSinterFines_TotalFe") is not None:
        merged["SkipSinterFines_ShiftA"] = None
        merged["SkipSinterFines_ShiftB"] = None
        merged["SkipSinterFines_ShiftC"] = None
    elif any(
        merged.get(col) is not None
        for col in ("SkipSinterFines_ShiftA", "SkipSinterFines_ShiftB", "SkipSinterFines_ShiftC")
    ):
        merged["SkipSinterFines_TotalFe"] = None

    return merged


def extract_skip_fines(pdf_path: str, verbose: bool = False) -> dict[str, Any]:
    """Extract BF-8 skip sinter and skip coke fines for one PDF."""
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
    sinter_values, coke_values = _find_fines_tables(tables)
    table_values = _merge_records(sinter_values, coke_values)

    if any(table_values.get(col) is not None for col in NUMERIC_COLUMNS):
        record.update(_merge_records(table_values, text_values))
    else:
        if verbose:
            print(
                f"WARNING: skip fines table not found in {pdf_path}; using text fallback",
                file=sys.stderr,
            )
        record.update(text_values)

    missing = [col for col in NUMERIC_COLUMNS if record.get(col) is None]
    if missing and verbose:
        print(
            f"WARNING: {os.path.basename(pdf_path)} missing {len(missing)} field(s): "
            + ", ".join(missing[:6])
            + ("..." if len(missing) > 6 else ""),
            file=sys.stderr,
        )

    return record


def stitch_skip_fines(
    pdf_paths: list[str],
    output_path: str,
    output_format: str = "both",
    replace_zero_with_na: bool = True,
    verbose: bool = False,
) -> Any:
    records = [extract_skip_fines(path, verbose=verbose) for path in pdf_paths]
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
        description="Extract BF-8 skip fines into a day-by-day CSV/Excel file."
    )
    add_input_args(parser)
    add_output_args(parser, DEFAULT_OUTPUT)
    add_verbose_arg(parser)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pdf_paths = resolve_pdf_paths(args)

    print(f"Extracting skip fines from {len(pdf_paths)} PDF(s)...")
    df = stitch_skip_fines(
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
