#!/usr/bin/env python3
"""Print the configured PDF folder path and fiscal-year subfolders."""

from __future__ import annotations

import sys

from drive_paths import discover_fiscal_year_dirs, load_drive_config, resolve_pdf_root


def main() -> int:
    config = load_drive_config()
    print("=== drive_config.json ===")
    print(f"  pdf_root : {config.get('pdf_root')}")
    print()

    try:
        base = resolve_pdf_root(config)
        folders = discover_fiscal_year_dirs(base, config)
        print("=== Ready to extract from ===")
        print(f"  {base}")
        for folder in folders:
            print(f"  - {folder}")
        return 0
    except FileNotFoundError as exc:
        print("=== Not ready ===")
        print(exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
