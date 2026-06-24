"""Resolve Google Drive PDF folders for BF-8 daily production reports."""

from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path
from typing import Any

# Relative path inside Google Drive (My Drive) from the notebook.
DEFAULT_DRIVE_ROOT = (
    "Blast Furnace Data/BF-8/Production and Quality/"
    "PDF - Daily Production Reports"
)
DEFAULT_FISCAL_YEAR_GLOB = "DailyProdReports_FY*"
DEFAULT_OUTPUT_CSV = "BF8_merged_all.csv"
DEFAULT_PAGE = "all"

CONFIG_FILENAME = "drive_config.json"


def _config_path() -> Path:
    return Path(__file__).resolve().parent / CONFIG_FILENAME


def load_drive_config() -> dict[str, Any]:
    """Load drive_config.json next to this module, else use defaults."""
    defaults = {
        "drive_root": DEFAULT_DRIVE_ROOT,
        "fiscal_year_glob": DEFAULT_FISCAL_YEAR_GLOB,
        "output_csv": DEFAULT_OUTPUT_CSV,
        "page": DEFAULT_PAGE,
        "mount_colab_drive": True,
    }

    config_file = _config_path()
    if not config_file.exists():
        return defaults

    with config_file.open(encoding="utf-8") as handle:
        user_config = json.load(handle)

    defaults.update(user_config)
    return defaults


def is_google_colab() -> bool:
    try:
        import google.colab  # type: ignore[import-not-found]

        return google.colab is not None
    except ImportError:
        return False


def mount_colab_drive(mount_point: str = "/content/drive") -> str:
    """Mount Google Drive when running inside Google Colab."""
    if not is_google_colab():
        return mount_point

    from google.colab import drive  # type: ignore[import-not-found]

    if not os.path.isdir(os.path.join(mount_point, "MyDrive")):
        drive.mount(mount_point)
    return mount_point


def _my_drive_candidates() -> list[Path]:
    """Common local Google Drive sync locations across OSes."""
    home = Path.home()
    candidates = [
        Path("/content/drive/MyDrive"),
        home / "Google Drive" / "My Drive",
        home / "GoogleDrive" / "My Drive",
        home / "My Drive",
    ]

    cloud_storage = home / "Library" / "CloudStorage"
    if cloud_storage.is_dir():
        candidates.extend(sorted(cloud_storage.glob("GoogleDrive-*/My Drive")))

    return candidates


def resolve_drive_base(config: dict[str, Any] | None = None) -> Path:
    """
    Find the mounted Google Drive base directory containing the PDF root.

    Resolution order:
    1. BF8_DRIVE_ROOT environment variable (full path to PDF parent folder)
    2. Colab mount + drive_root from config
    3. Local Google Drive desktop sync + drive_root from config
    """
    config = config or load_drive_config()

    env_root = os.environ.get("BF8_DRIVE_ROOT", "").strip()
    if env_root:
        base = Path(env_root).expanduser()
        if base.is_dir():
            return base
        raise FileNotFoundError(
            f"BF8_DRIVE_ROOT is set but not found: {base}\n"
            "Point it at the folder that contains DailyProdReports_FY* subfolders."
        )

    if config.get("mount_colab_drive", True):
        mount_colab_drive()

    drive_root = config["drive_root"]
    checked: list[str] = []

    for my_drive in _my_drive_candidates():
        candidate = my_drive / drive_root
        checked.append(str(candidate))
        if candidate.is_dir():
            return candidate

    checked_list = "\n  ".join(checked)
    raise FileNotFoundError(
        "Could not find your Google Drive PDF folders.\n\n"
        "Do one of the following:\n"
        "  1. Copy drive_config.json.example to drive_config.json and verify drive_root\n"
        "  2. Set BF8_DRIVE_ROOT to the full path of your PDF parent folder\n"
        "  3. In Colab, run this script after Google Drive is mounted\n"
        "  4. Install Google Drive for desktop and sync the PDF folders locally\n\n"
        f"Checked:\n  {checked_list}"
    )


def discover_fiscal_year_dirs(
    drive_base: Path | None = None,
    config: dict[str, Any] | None = None,
) -> list[str]:
    """Return all fiscal-year PDF folders under the configured Drive root."""
    config = config or load_drive_config()
    base = drive_base or resolve_drive_base(config)

    pattern = str(base / config["fiscal_year_glob"])
    folders = sorted(p for p in glob.glob(pattern) if os.path.isdir(p))

    if not folders:
        raise FileNotFoundError(
            f"No folders matched {pattern!r}.\n"
            "Check fiscal_year_glob in drive_config.json."
        )

    return folders


def resolve_input_directories(
    input_dirs: list[str] | None = None,
    from_drive: bool = False,
    config: dict[str, Any] | None = None,
) -> list[str]:
    """Resolve PDF input folders from CLI paths or Google Drive."""
    if input_dirs:
        return input_dirs

    if not from_drive:
        return []

    config = config or load_drive_config()
    folders = discover_fiscal_year_dirs(config=config)
    return folders
