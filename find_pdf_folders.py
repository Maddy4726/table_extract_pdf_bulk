#!/usr/bin/env python3
"""Print where the script will look for PDF folders (run this if auto-detect fails)."""

from __future__ import annotations

import sys

from drive_paths import (
    _candidate_bases,
    _find_pdf_root_by_search,
    discover_fiscal_year_dirs,
    load_drive_config,
    resolve_drive_base,
)


def main() -> int:
    config = load_drive_config()
    print("=== drive_config.json ===")
    print(f"  drive_base : {config.get('drive_base') or '(not set)'}")
    print(f"  drive_root : {config['drive_root']}")
    print()

    print("=== Paths that will be checked ===")
    for path in _candidate_bases(config):
        exists = "FOUND" if path.is_dir() else "missing"
        print(f"  [{exists}] {path}")
    print()

    found = _find_pdf_root_by_search()
    if found:
        print(f"=== Auto-search result ===\n  {found}\n")

    try:
        base = resolve_drive_base(config)
        folders = discover_fiscal_year_dirs(base, config)
        print("=== Ready to extract from ===")
        print(f"  Base: {base}")
        for folder in folders:
            print(f"  - {folder}")
        return 0
    except FileNotFoundError as exc:
        print("=== Not ready ===")
        print(exc)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
