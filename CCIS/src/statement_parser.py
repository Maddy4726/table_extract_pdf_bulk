"""Parse credit card statement PDFs and update monthly spend totals."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pdfplumber
import yaml

from src.spend_tracker import load_spend_config, save_spend_config

ROOT = Path(__file__).resolve().parents[1]
STATEMENTS_CONFIG_PATH = ROOT / "config" / "statements.yaml"

AMOUNT_RE = re.compile(r"(?<!\d)(\d{1,3}(?:,\d{2,3})*(?:\.\d{2})?|\d+\.\d{2})(?!\d)")
DATE_LINE_RE = re.compile(
    r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b"
)
PERIOD_RE = re.compile(
    r"(?:statement\s+period|billing\s+period|statement\s+from|period\s*from)"
    r"[^\d]{0,40}(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})"
    r"[^\d]{0,20}(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})",
    re.IGNORECASE,
)
STATEMENT_DATE_RE = re.compile(
    r"(?:statement\s+date|bill\s+date|generated\s+on)"
    r"[^\d]{0,20}(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})",
    re.IGNORECASE,
)


@dataclass
class ParsedStatement:
    card_key: str
    month: str  # YYYY-MM
    total_spend_inr: float
    source_file: str
    method: str  # labeled_total | transaction_sum | filename_month
    confidence: str  # high | medium | low
    notes: str = ""


@dataclass
class ParseReport:
    parsed: list[ParsedStatement] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def load_statements_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or STATEMENTS_CONFIG_PATH
    with config_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _parse_amount(text: str) -> float | None:
    try:
        return float(text.replace(",", ""))
    except ValueError:
        return None


def _normalize_year(year: int) -> int:
    if year < 100:
        return 2000 + year
    return year


def _to_month_key(day: int, month: int, year: int) -> str:
    year = _normalize_year(year)
    return f"{year:04d}-{month:02d}"


def _month_from_filename(path: Path) -> str | None:
    """Infer YYYY-MM from names like axis_2026-04.pdf or stmt_202604.pdf."""
    name = path.stem.lower()
    match = re.search(r"(20\d{2})[-_]?(0[1-9]|1[0-2])", name)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    return None


def infer_statement_month(text: str, path: Path) -> str | None:
    period = PERIOD_RE.search(text)
    if period:
        _d1, m1, y1, d2, m2, y2 = map(int, period.groups())
        return _to_month_key(d2, m2, y2)

    stmt_date = STATEMENT_DATE_RE.search(text)
    if stmt_date:
        _d, m, y = map(int, stmt_date.groups())
        return _to_month_key(_d, m, y)

    return _month_from_filename(path)


def _line_excluded(line: str, exclude_keywords: list[str]) -> bool:
    lower = line.lower()
    return any(keyword in lower for keyword in exclude_keywords)


def _extract_labeled_total(text: str, patterns: list[str]) -> float | None:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            amount = _parse_amount(match.group(1))
            if amount is not None and amount > 0:
                return amount
    return None


def _extract_transaction_sum(text: str, exclude_keywords: list[str]) -> float | None:
    total = 0.0
    hits = 0
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if len(line) < 8 or _line_excluded(line, exclude_keywords):
            continue
        if not DATE_LINE_RE.search(line):
            continue
        amounts = AMOUNT_RE.findall(line)
        if not amounts:
            continue
        amount = _parse_amount(amounts[-1])
        if amount is None or amount <= 0:
            continue
        if amount > 5_000_000:
            continue
        total += amount
        hits += 1
    if hits >= 2:
        return round(total, 2)
    return None


def parse_statement_text(
    text: str,
    *,
    card_key: str,
    source_file: str,
    config: dict[str, Any] | None = None,
    path: Path | None = None,
) -> ParsedStatement | None:
    config = config or load_statements_config()
    month = infer_statement_month(text, path or Path(source_file))
    if not month:
        return None

    labeled = _extract_labeled_total(text, config.get("total_labels") or [])
    if labeled is not None:
        return ParsedStatement(
            card_key=card_key,
            month=month,
            total_spend_inr=labeled,
            source_file=source_file,
            method="labeled_total",
            confidence="high",
        )

    txn_sum = _extract_transaction_sum(text, config.get("exclude_keywords") or [])
    if txn_sum is not None:
        return ParsedStatement(
            card_key=card_key,
            month=month,
            total_spend_inr=txn_sum,
            source_file=source_file,
            method="transaction_sum",
            confidence="medium",
        )

    return None


def parse_statement_pdf(
    path: Path,
    card_key: str,
    config: dict[str, Any] | None = None,
) -> ParsedStatement | None:
    with pdfplumber.open(path) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]
    text = "\n".join(pages)
    if not text.strip():
        return None
    return parse_statement_text(
        text,
        card_key=card_key,
        source_file=str(path.name),
        config=config,
        path=path,
    )


def discover_statement_files(
    statements_root: Path,
    folder_map: dict[str, str],
) -> list[tuple[Path, str]]:
    files: list[tuple[Path, str]] = []
    for folder_name, card_key in folder_map.items():
        folder = statements_root / folder_name
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("**/*")):
            if path.suffix.lower() == ".pdf" and path.is_file():
                files.append((path, card_key))
    return files


def import_statements(
    statements_root: Path | None = None,
    *,
    rebuild_dashboard: bool = False,
) -> ParseReport:
    config = load_statements_config()
    root = statements_root or (ROOT / config.get("statements_root", "statements"))
    folder_map = config.get("folders") or {}
    report = ParseReport()

    candidates: dict[tuple[str, str], ParsedStatement] = {}
    for path, card_key in discover_statement_files(root, folder_map):
        try:
            parsed = parse_statement_pdf(path, card_key, config=config)
        except Exception as exc:  # noqa: BLE001 - surface per-file parse errors
            report.errors.append(f"{path.name}: {exc}")
            continue
        if parsed is None:
            report.skipped.append(f"{path.name}: could not detect month or spend total")
            continue
        key = (parsed.card_key, parsed.month)
        existing = candidates.get(key)
        if existing is None or _confidence_rank(parsed) > _confidence_rank(existing):
            candidates[key] = parsed

    report.parsed = sorted(candidates.values(), key=lambda item: (item.card_key, item.month))
    if report.parsed:
        apply_parsed_statements(report.parsed)
    return report


def _confidence_rank(parsed: ParsedStatement) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(parsed.confidence, 0)


def apply_parsed_statements(parsed: list[ParsedStatement]) -> dict[str, Any]:
    """Merge parsed statement totals into spend_tracker.yaml."""
    spend_config = load_spend_config()
    spends = spend_config.setdefault("spends", {})
    months = set(spend_config.get("months") or [])

    for item in parsed:
        months.add(item.month)
        card_spends = spends.setdefault(item.card_key, {})
        card_spends[item.month] = round(item.total_spend_inr, 2)

    sorted_months = sorted(months)
    if len(sorted_months) > 3:
        sorted_months = sorted_months[-3:]

    spend_config["months"] = sorted_months
    if sorted_months:
        start = sorted_months[0]
        end = sorted_months[-1]
        y1, m1 = map(int, start.split("-"))
        y2, m2 = map(int, end.split("-"))
        label = (
            f"{calendar.month_abbr[m1]}–{calendar.month_abbr[m2]} {y2} "
            f"(rolling {len(sorted_months)} calendar months)"
        )
        spend_config["period_label"] = label

    spend_config["last_import_at"] = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    save_spend_config(spend_config)
    return spend_config


def format_import_report(report: ParseReport) -> str:
    lines: list[str] = []
    if report.parsed:
        lines.append("Imported statements:")
        for item in report.parsed:
            lines.append(
                f"  {item.card_key:24} {item.month}  ₹{item.total_spend_inr:,.2f}  "
                f"({item.method}, {item.confidence})  <- {item.source_file}"
            )
    if report.skipped:
        lines.append("\nSkipped:")
        for msg in report.skipped:
            lines.append(f"  {msg}")
    if report.errors:
        lines.append("\nErrors:")
        for msg in report.errors:
            lines.append(f"  {msg}")
    if not lines:
        lines.append("No statement PDFs found. Add files under CCIS/statements/<bank>/.")
    return "\n".join(lines)
