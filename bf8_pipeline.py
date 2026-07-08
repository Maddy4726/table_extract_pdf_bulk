"""Unified BF-8 PDF extraction pipeline: run all table extractors and merge by date."""

from __future__ import annotations

import fnmatch
import os
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import pandas as pd

from drive_paths import load_drive_config, resolve_input_directories
from extract_bf8_daily import collect_pdf_paths
from extract_coke_quality import DEFAULT_OUTPUT as COKE_OUTPUT
from extract_coke_quality import stitch_coke_quality
from extract_hot_metal_slag import DEFAULT_OUTPUT as HOT_METAL_OUTPUT
from extract_hot_metal_slag import stitch_hot_metal_slag
from extract_pellet_analysis import DEFAULT_OUTPUT as PELLET_OUTPUT
from extract_pellet_analysis import stitch_pellet_analysis
from extract_production_parameters import DEFAULT_OUTPUT as PROD_OUTPUT
from extract_production_parameters import stitch_production_parameters
from extract_sinter_plant import DEFAULT_OUTPUT as SINTER_PLANT_OUTPUT
from extract_sinter_plant import stitch_sinter_plant
from extract_skip_fines import DEFAULT_OUTPUT as SKIP_FINES_OUTPUT
from extract_skip_fines import stitch_skip_fines
from extract_skip_iron_ore import DEFAULT_OUTPUT as SKIP_IRON_OUTPUT
from extract_skip_iron_ore import stitch_skip_iron_ore
from extract_skip_sinter import DEFAULT_OUTPUT as SKIP_SINTER_OUTPUT
from extract_skip_sinter import stitch_skip_sinter
from extract_table_utils import DEFAULT_PDF_PATTERN, META_COLUMNS, write_dataframe

DEFAULT_MASTER_OUTPUT = "BF8_master_dataset"

MERGE_META_COLUMNS = list(META_COLUMNS)


@dataclass(frozen=True)
class ExtractorSpec:
    """One table-by-table BF-8 extractor."""

    key: str
    label: str
    default_output: str
    stitch: Callable[..., pd.DataFrame]


EXTRACTORS: tuple[ExtractorSpec, ...] = (
    ExtractorSpec(
        "production_parameters",
        "Page 1 production parameters",
        PROD_OUTPUT,
        stitch_production_parameters,
    ),
    ExtractorSpec(
        "hot_metal_slag",
        "Page 2 hot metal and slag quality",
        HOT_METAL_OUTPUT,
        stitch_hot_metal_slag,
    ),
    ExtractorSpec(
        "skip_iron_ore",
        "Page 2 skip iron ore analysis",
        SKIP_IRON_OUTPUT,
        stitch_skip_iron_ore,
    ),
    ExtractorSpec(
        "pellet_analysis",
        "Page 2 pellet chemical and sieve analysis",
        PELLET_OUTPUT,
        stitch_pellet_analysis,
    ),
    ExtractorSpec(
        "skip_sinter",
        "Page 2 skip sinter chemistry",
        SKIP_SINTER_OUTPUT,
        stitch_skip_sinter,
    ),
    ExtractorSpec(
        "skip_fines",
        "Page 2 skip sinter and coke fines",
        SKIP_FINES_OUTPUT,
        stitch_skip_fines,
    ),
    ExtractorSpec(
        "coke_quality",
        "Page 2 coke quality",
        COKE_OUTPUT,
        stitch_coke_quality,
    ),
    ExtractorSpec(
        "sinter_plant",
        "Page 2 sinter plant chemistry",
        SINTER_PLANT_OUTPUT,
        stitch_sinter_plant,
    ),
)

EXTRACTOR_BY_KEY = {spec.key: spec for spec in EXTRACTORS}
DEFAULT_EXTRACTOR_KEYS = tuple(spec.key for spec in EXTRACTORS)


def resolve_pdf_inputs(
    input_dirs: list[str] | None = None,
    from_config: bool = False,
    recursive: bool = False,
    pdf_pattern: str | None = None,
    config: dict[str, Any] | None = None,
) -> tuple[list[str], list[str]]:
    """Return (input_dirs, pdf_paths) using the same rules as the table extractors."""
    config = config or load_drive_config()
    use_config = from_config or input_dirs is None

    resolved_dirs = resolve_input_directories(
        input_dirs=input_dirs,
        from_config=use_config,
        config=config,
    )
    if not resolved_dirs and input_dirs:
        resolved_dirs = input_dirs

    pdf_paths = collect_pdf_paths(resolved_dirs, recursive=recursive)
    pattern = pdf_pattern
    if pattern is None and input_dirs is not None and not use_config:
        pattern = DEFAULT_PDF_PATTERN
    if pattern:
        pdf_paths = [
            path for path in pdf_paths if fnmatch.fnmatch(os.path.basename(path), pattern)
        ]

    return resolved_dirs, pdf_paths


def run_extractor(
    spec: ExtractorSpec,
    pdf_paths: list[str],
    output_path: str,
    *,
    output_format: str = "both",
    replace_zero_with_na: bool = True,
    write_files: bool = True,
    verbose: bool = False,
) -> pd.DataFrame:
    """Run one registered extractor and return its dataframe."""
    if verbose:
        print(f"  -> {spec.label}")
    if write_files:
        return spec.stitch(
            pdf_paths,
            output_path,
            output_format=output_format,
            replace_zero_with_na=replace_zero_with_na,
            verbose=verbose,
        )

    import importlib

    module = importlib.import_module(spec.stitch.__module__)
    extract_name = spec.stitch.__name__.replace("stitch_", "extract_", 1)
    extract_fn = getattr(module, extract_name)
    records = [extract_fn(path, verbose=verbose) for path in pdf_paths]

    from extract_table_utils import finalize_dates

    df = pd.DataFrame(records)
    numeric_columns = [col for col in df.columns if col not in MERGE_META_COLUMNS]
    for col in numeric_columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = finalize_dates(df, pdf_paths)
    if replace_zero_with_na:
        df = df.replace(0, pd.NA)
    return df.sort_values("date").reset_index(drop=True)


def run_all_extractors(
    pdf_paths: list[str],
    *,
    extractor_keys: list[str] | None = None,
    output_dir: str = ".",
    output_format: str = "both",
    write_individual: bool = True,
    replace_zero_with_na: bool = True,
    verbose: bool = False,
) -> dict[str, pd.DataFrame]:
    """Run selected extractors and optionally write each table output."""
    keys = extractor_keys or list(DEFAULT_EXTRACTOR_KEYS)
    unknown = [key for key in keys if key not in EXTRACTOR_BY_KEY]
    if unknown:
        raise ValueError(f"Unknown extractor(s): {', '.join(unknown)}")

    results: dict[str, pd.DataFrame] = {}
    for key in keys:
        spec = EXTRACTOR_BY_KEY[key]
        output_path = os.path.join(output_dir, spec.default_output)
        if verbose:
            print(f"[{key}] {spec.label}")
        df = run_extractor(
            spec,
            pdf_paths,
            output_path,
            output_format=output_format,
            write_files=write_individual,
            replace_zero_with_na=replace_zero_with_na,
            verbose=verbose,
        )
        results[key] = df
    return results


def merge_extractor_dataframes(
    dataframes: list[pd.DataFrame],
    *,
    sort: bool = True,
) -> pd.DataFrame:
    """Outer-join extractor outputs on date into one master dataset."""
    frames: list[pd.DataFrame] = []
    for df in dataframes:
        if df.empty:
            continue
        piece = df.copy()
        if "date" not in piece.columns and "Date" in piece.columns:
            piece = piece.rename(columns={"Date": "date"})
        if "date" not in piece.columns:
            raise ValueError("Each extractor output must include a date column.")
        piece["date"] = pd.to_datetime(piece["date"], errors="coerce")
        frames.append(piece)

    if not frames:
        return pd.DataFrame(columns=MERGE_META_COLUMNS)

    merged = frames[0]
    for piece in frames[1:]:
        data_cols = [col for col in piece.columns if col not in MERGE_META_COLUMNS]
        overlap = set(merged.columns) & set(data_cols)
        add_cols = ["date"] + [col for col in data_cols if col not in overlap]
        merged = merged.merge(piece[add_cols], on="date", how="outer")

        for col in MERGE_META_COLUMNS:
            if col == "date" or col not in piece.columns:
                continue
            fill = (
                piece[["date", col]]
                .drop_duplicates("date")
                .set_index("date")[col]
            )
            if col not in merged.columns:
                merged[col] = merged["date"].map(fill)
            else:
                merged[col] = merged[col].combine_first(merged["date"].map(fill))

    if sort:
        merged = merged.sort_values("date").reset_index(drop=True)

    meta = [col for col in MERGE_META_COLUMNS if col in merged.columns]
    other = [col for col in merged.columns if col not in meta]
    return merged[meta + other]


def write_master_dataset(
    df: pd.DataFrame,
    output_path: str,
    *,
    output_format: str = "both",
    verbose: bool = False,
) -> None:
    """Write the merged master dataset."""
    write_dataframe(df, output_path, output_format=output_format, verbose=verbose)
