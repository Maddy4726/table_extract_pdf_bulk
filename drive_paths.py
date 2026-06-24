"""Resolve Google Drive PDF folders for BF-8 daily production reports."""

from __future__ import annotations

import glob
import json
import os
import string
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
        "drive_base": "",
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


def _windows_drive_letter_candidates(drive_root: str) -> list[Path]:
    """Google Drive for desktop on Windows often mounts as G:\\My Drive."""
    candidates: list[Path] = []
    if os.name != "nt":
        return candidates

    drive_root_path = Path(drive_root)
    for letter in string.ascii_uppercase:
        drive = Path(f"{letter}:\\")
        if not drive.exists():
            continue
        candidates.extend(
            [
                drive / "My Drive" / drive_root_path,
                drive / "MyDrive" / drive_root_path,
                drive / drive_root_path,
            ]
        )
    return candidates


def _my_drive_candidates() -> list[Path]:
    """Common local Google Drive sync locations across OSes."""
    home = Path.home()
    candidates = [
        Path("/content/drive/MyDrive"),
        home / "Google Drive" / "My Drive",
        home / "Google Drive",
        home / "GoogleDrive" / "My Drive",
        home / "GoogleDrive",
        home / "My Drive",
    ]

    cloud_storage = home / "Library" / "CloudStorage"
    if cloud_storage.is_dir():
        candidates.extend(sorted(cloud_storage.glob("GoogleDrive-*/My Drive")))
        candidates.extend(sorted(cloud_storage.glob("GoogleDrive-*")))

    return candidates


def _candidate_bases(config: dict[str, Any]) -> list[Path]:
    """Build ordered list of candidate PDF parent folder paths."""
    drive_root = config["drive_root"]
    drive_root_path = Path(drive_root)
    candidates: list[Path] = []

    drive_base = str(config.get("drive_base", "")).strip()
    if drive_base:
        candidates.append(Path(drive_base).expanduser())

    for my_drive in _my_drive_candidates():
        candidates.append(my_drive / drive_root_path)
        candidates.append(my_drive / drive_root_path.name)

    candidates.extend(_windows_drive_letter_candidates(drive_root))

    # De-duplicate while preserving order.
    seen: set[str] = set()
    unique: list[Path] = []
    for path in candidates:
        key = str(path)
        if key not in seen:
            seen.add(key)
            unique.append(path)
    return unique


def _folder_has_pdfs(folder: Path) -> bool:
    return folder.is_dir() and bool(list(folder.glob("*.pdf")))


def _find_pdf_root_by_search() -> Path | None:
    """
    Last resort: search Desktop, Documents, Downloads, and repo folder
    for DailyProdReports_FY* directories that contain PDFs.
    """
    repo_dir = Path(__file__).resolve().parent
    search_roots = [
        repo_dir,
        Path.home() / "Desktop",
        Path.home() / "Documents",
        Path.home() / "Downloads",
        Path.home(),
    ]

    seen_parents: set[str] = set()
    for root in search_roots:
        if not root.exists():
            continue
        try:
            matches = root.glob("**/DailyProdReports_FY*")
        except OSError:
            continue
        for match in matches:
            if not match.is_dir() or not _folder_has_pdfs(match):
                continue
            parent = match.parent
            parent_key = str(parent)
            if parent_key in seen_parents:
                continue
            seen_parents.add(parent_key)
            return parent
    return None


def resolve_drive_base(config: dict[str, Any] | None = None) -> Path:
    """
    Find the folder that contains DailyProdReports_FY* subfolders.

    Resolution order:
    1. BF8_DRIVE_ROOT environment variable
    2. drive_base in drive_config.json (full path)
    3. Google Drive / Colab standard locations
    4. Windows drive letters (G:\\My Drive, etc.)
    5. Search Desktop/Documents for DailyProdReports_FY* folders
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

    checked: list[str] = []
    for candidate in _candidate_bases(config):
        checked.append(str(candidate))
        if candidate.is_dir():
            return candidate

    found = _find_pdf_root_by_search()
    if found is not None:
        print(f"Auto-found PDF folders at: {found}", file=sys.stderr)
        return found

    checked_list = "\n  ".join(checked)
    home = Path.home()
    raise FileNotFoundError(
        "Could not find your Google Drive PDF folders.\n\n"
        "Windows fix (pick one):\n"
        "  1. Edit drive_config.json and set drive_base to the full folder path, e.g.\n"
        '     "drive_base": "G:\\\\My Drive\\\\Blast Furnace Data\\\\BF-8\\\\'
        'Production and Quality\\\\PDF - Daily Production Reports"\n'
        "  2. PowerShell for this session only:\n"
        f'     $env:BF8_DRIVE_ROOT = "C:\\path\\to\\PDF - Daily Production Reports"\n'
        "     python extract_bf8_daily.py --verbose\n"
        "  3. Or pass folders directly:\n"
        "     python extract_bf8_daily.py --input-dir \"C:\\path\\to\\DailyProdReports_FY2024-25\" --verbose\n"
        "  4. Use Google Colab if PDFs are only in cloud Drive (not synced to PC)\n\n"
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
