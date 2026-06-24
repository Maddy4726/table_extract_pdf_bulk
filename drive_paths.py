"""Resolve local PDF folder paths for BF-8 daily production reports."""

from __future__ import annotations

import glob
import json
import os
from pathlib import Path
from typing import Any

DEFAULT_PDF_ROOT = (
    r"F:\Fuel-Slag Rate Reduction Project\Blast Furnace Data\BF-8"
    r"\Production and Quality\PDF - Daily Production Reports"
)
DEFAULT_FISCAL_YEAR_GLOB = "DailyProdReports_FY*"
DEFAULT_OUTPUT_CSV = "BF8_merged_all.csv"
DEFAULT_PAGE = "all"

CONFIG_FILENAME = "drive_config.json"


def _config_path() -> Path:
    return Path(__file__).resolve().parent / CONFIG_FILENAME


def load_drive_config() -> dict[str, Any]:
    """Load drive_config.json next to this module."""
    defaults = {
        "pdf_root": DEFAULT_PDF_ROOT,
        "fiscal_year_glob": DEFAULT_FISCAL_YEAR_GLOB,
        "output_csv": DEFAULT_OUTPUT_CSV,
        "page": DEFAULT_PAGE,
    }

    config_file = _config_path()
    if not config_file.exists():
        return defaults

    with config_file.open(encoding="utf-8") as handle:
        user_config = json.load(handle)

    defaults.update(user_config)

    # Backward compatibility with older config key.
    if not str(defaults.get("pdf_root", "")).strip() and defaults.get("drive_base"):
        defaults["pdf_root"] = defaults["drive_base"]

    return defaults


def resolve_pdf_root(config: dict[str, Any] | None = None) -> Path:
    """
    Return the folder that contains DailyProdReports_FY* subfolders.

    Resolution order:
    1. BF8_PDF_ROOT or BF8_DRIVE_ROOT environment variable
    2. pdf_root in drive_config.json
    """
    config = config or load_drive_config()

    for env_name in ("BF8_PDF_ROOT", "BF8_DRIVE_ROOT"):
        env_root = os.environ.get(env_name, "").strip()
        if env_root:
            base = Path(env_root).expanduser()
            if base.is_dir():
                return base
            raise FileNotFoundError(
                f"{env_name} is set but not found: {base}\n"
                "Point it at the folder that contains DailyProdReports_FY* subfolders."
            )

    pdf_root = str(config.get("pdf_root", "")).strip()
    if not pdf_root:
        raise FileNotFoundError(
            "No PDF folder configured.\n\n"
            "Edit drive_config.json and set pdf_root to your local folder, e.g.\n"
            '  "pdf_root": "F:\\\\Fuel-Slag Rate Reduction Project\\\\Blast Furnace Data\\\\'
            'BF-8\\\\Production and Quality\\\\PDF - Daily Production Reports"'
        )

    base = Path(pdf_root).expanduser()
    if base.is_dir():
        return base

    raise FileNotFoundError(
        f"PDF folder not found: {base}\n\n"
        "Check that the F: drive is connected and pdf_root in drive_config.json is correct.\n"
        "Or run:\n"
        '  python extract_bf8_daily.py --input-dir "F:\\...\\DailyProdReports_FY2024-25" --verbose'
    )


def discover_fiscal_year_dirs(
    pdf_root: Path | None = None,
    config: dict[str, Any] | None = None,
) -> list[str]:
    """Return all fiscal-year PDF folders under the configured root."""
    config = config or load_drive_config()
    base = pdf_root or resolve_pdf_root(config)

    pattern = str(base / config["fiscal_year_glob"])
    folders = sorted(p for p in glob.glob(pattern) if os.path.isdir(p))

    if not folders:
        raise FileNotFoundError(
            f"No folders matched {pattern!r}.\n"
            "Expected subfolders like DailyProdReports_FY2023-24 with PDF files inside."
        )

    return folders


def resolve_input_directories(
    input_dirs: list[str] | None = None,
    from_config: bool = False,
    config: dict[str, Any] | None = None,
) -> list[str]:
    """Resolve PDF input folders from CLI paths or pdf_config."""
    if input_dirs:
        return input_dirs

    if not from_config:
        return []

    config = config or load_drive_config()
    return discover_fiscal_year_dirs(config=config)


# Backward-compatible alias used by older code paths.
resolve_drive_base = resolve_pdf_root
