"""Shared helpers for table-by-table BF-8 PDF extractors."""

from __future__ import annotations

import os
from typing import Any

import pandas as pd

from extract_bf8_daily import _date_from_filename, _extract_date

DEFAULT_PDF_PATTERN = "NEW P.D.*.pdf"
META_COLUMNS = ["date", "report_date", "year", "month", "day", "source_file"]


def resolve_report_date(page_text: str, pdf_path: str) -> str:
    """Return a human-readable date string, preferring the PDF header then the filename."""
    report_date = _extract_date(page_text, pdf_path)
    if report_date == "Unknown":
        report_date = _date_from_filename(pdf_path) or "Unknown"

    parsed = pd.to_datetime(report_date, errors="coerce")
    if pd.isna(parsed):
        filename_date = _date_from_filename(pdf_path)
        if filename_date:
            return filename_date
    return report_date


def assign_report_date(record: dict[str, Any], page_text: str, pdf_path: str) -> None:
    report_date = resolve_report_date(page_text, pdf_path)
    parsed = pd.to_datetime(report_date, errors="coerce")
    if pd.isna(parsed):
        filename_date = _date_from_filename(pdf_path)
        if filename_date:
            report_date = filename_date
    record["report_date"] = report_date


def sort_records_by_date(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sort extracted records chronologically without pandas sort_values.

    pdfplumber can leave native libraries in a bad state on some Linux builds;
    sorting via Python before building the DataFrame avoids a pandas segfault.
    """

    def sort_key(record: dict[str, Any]) -> tuple[int, str]:
        parsed = pd.to_datetime(record.get("report_date"), errors="coerce")
        if pd.isna(parsed):
            return (1, str(record.get("source_file", "")))
        return (0, parsed.isoformat())

    return sorted(records, key=sort_key)


def finalize_dates(df: pd.DataFrame, pdf_paths: list[str] | None = None) -> pd.DataFrame:
    df["date"] = pd.to_datetime(df["report_date"], errors="coerce")
    missing = df["date"].isna()
    if missing.any() and pdf_paths:
        path_by_name = {os.path.basename(path): path for path in pdf_paths}
        for idx in df.index[missing]:
            source_path = path_by_name.get(str(df.at[idx, "source_file"]))
            if not source_path:
                continue
            filename_date = _date_from_filename(source_path)
            if filename_date:
                df.at[idx, "report_date"] = filename_date
                df.at[idx, "date"] = pd.to_datetime(filename_date, errors="coerce")

    df["year"] = df["date"].dt.year.astype("Int64")
    df["month"] = df["date"].dt.month.astype("Int64")
    df["day"] = df["date"].dt.day.astype("Int64")

    other_cols = [col for col in df.columns if col not in META_COLUMNS]
    return df[META_COLUMNS + other_cols]


def write_dataframe(
    df: pd.DataFrame,
    output_path: str,
    output_format: str = "both",
    verbose: bool = False,
) -> None:
    base, ext = os.path.splitext(output_path)
    if output_format == "both":
        df.to_csv(base + ".csv", index=False)
        df.to_excel(base + ".xlsx", index=False)
        if verbose:
            print(f"Saved CSV  -> {base}.csv")
            print(f"Saved Excel -> {base}.xlsx")
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


def stitch_records(
    records: list[dict[str, Any]],
    pdf_paths: list[str],
    numeric_columns: list[str],
    output_path: str,
    output_format: str = "both",
    replace_zero_with_na: bool = True,
    verbose: bool = False,
) -> pd.DataFrame:
    records = sort_records_by_date(records)
    df = pd.DataFrame(records)

    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    df = finalize_dates(df, pdf_paths)
    df = df.reset_index(drop=True)

    if replace_zero_with_na:
        df = df.replace(0, pd.NA)

    write_dataframe(df, output_path, output_format=output_format, verbose=verbose)
    return df
