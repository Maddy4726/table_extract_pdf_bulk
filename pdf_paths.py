"""Find daily production PDFs from a folder path on your PC."""

from __future__ import annotations

import glob
import os


def collect_pdf_paths(input_dirs: list[str], recursive: bool = False) -> list[str]:
    """Return sorted PDF paths from one or more input folders."""
    paths: list[str] = []
    pattern = "**/*.pdf" if recursive else "*.pdf"

    for directory in input_dirs:
        if not os.path.isdir(directory):
            raise FileNotFoundError(f"Input directory not found: {directory}")
        matched = glob.glob(os.path.join(directory, pattern), recursive=recursive)
        paths.extend(matched)

    return sorted(set(paths))
