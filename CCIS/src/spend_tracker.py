"""Load monthly spends and compute lounge / milestone progress."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

import yaml

from src.import_data import load_portfolio_config

ROOT = Path(__file__).resolve().parents[1]
SPEND_CONFIG_PATH = ROOT / "config" / "spend_tracker.yaml"


def load_spend_config(path: Path | None = None) -> dict[str, Any]:
    config_path = path or SPEND_CONFIG_PATH
    if not config_path.exists():
        return {
            "period_label": "Not configured",
            "months": [],
            "spends": {},
        }
    with config_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def save_spend_config(data: dict[str, Any], path: Path | None = None) -> Path:
    config_path = path or SPEND_CONFIG_PATH
    with config_path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, default_flow_style=False, sort_keys=False, allow_unicode=True)
    return config_path


def _month_amount(card_spends: dict[str, Any], month: str) -> float:
    value = card_spends.get(month, 0) if card_spends else 0
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def rolling_spend_for_card(card_key: str, spend_config: dict[str, Any]) -> float:
    months = spend_config.get("months") or []
    card_spends = (spend_config.get("spends") or {}).get(card_key) or {}
    return sum(_month_amount(card_spends, month) for month in months)


def build_spend_tracker_rows(
    spend_config: dict[str, Any] | None = None,
    portfolio: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """One row per card with monthly breakdown and rolling total."""
    spend_config = spend_config or load_spend_config()
    portfolio = portfolio or load_portfolio_config()
    months = spend_config.get("months") or []
    spends = spend_config.get("spends") or {}

    rows: list[dict[str, Any]] = []
    for card in portfolio["cards"]:
        key = card["key"]
        card_spends = spends.get(key) or {}
        month_values = [_month_amount(card_spends, month) for month in months]
        rolling = sum(month_values)

        row: dict[str, Any] = {
            "card_key": key,
            "card_name": card["name"],
            "period_label": spend_config.get("period_label", ""),
        }
        for idx, month in enumerate(months):
            row[f"month_{idx + 1}"] = month
            row[f"spend_month_{idx + 1}_inr"] = month_values[idx] if idx < len(month_values) else 0
        row["rolling_3mo_total_inr"] = rolling
        rows.append(row)
    return rows


def build_milestone_rows(
    spend_config: dict[str, Any] | None = None,
    portfolio: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Lounge eligibility and progress toward spend thresholds."""
    spend_config = spend_config or load_spend_config()
    portfolio = portfolio or load_portfolio_config()
    months = spend_config.get("months") or []

    rows: list[dict[str, Any]] = []
    for card in portfolio["cards"]:
        key = card["key"]
        rolling = rolling_spend_for_card(key, spend_config)
        target = card.get("lounge_spend_inr")
        spend_required = bool(card.get("lounge_spend_required"))
        remaining = None
        pct = None
        eligible = "N/A"

        if spend_required and target:
            remaining = max(float(target) - rolling, 0)
            pct = min(100.0, round(100.0 * rolling / float(target), 1))
            eligible = "Yes" if rolling >= float(target) else "No"
        elif not spend_required:
            eligible = "Yes (no spend)"

        card_spends = (spend_config.get("spends") or {}).get(key) or {}
        row: dict[str, Any] = {
            "card_key": key,
            "card_name": card["name"],
            "period_label": spend_config.get("period_label", ""),
            "rolling_3mo_total_inr": rolling,
            "lounge_target_inr": target,
            "remaining_inr": remaining,
            "pct_to_lounge": pct,
            "lounge_eligible": eligible,
            "lounge_visits_per_quarter": card.get("lounge_visits_per_quarter"),
            "spend_window_months": card.get("lounge_spend_window_months"),
        }
        for idx, month in enumerate(months):
            row[f"{month}_inr"] = _month_amount(card_spends, month)
        rows.append(row)
    return rows


def sync_spends_to_db(
    conn: sqlite3.Connection,
    spend_config: dict[str, Any] | None = None,
    portfolio: dict[str, Any] | None = None,
) -> None:
    """Update spend_tracker table from YAML config."""
    spend_config = spend_config or load_spend_config()
    portfolio = portfolio or load_portfolio_config()
    period = spend_config.get("period_label", "current_quarter")

    for card in portfolio["cards"]:
        key = card["key"]
        rolling = rolling_spend_for_card(key, spend_config)
        target = card.get("lounge_spend_inr")
        eligible = 0
        if not card.get("lounge_spend_required"):
            eligible = 1
        elif target and rolling >= float(target):
            eligible = 1

        conn.execute(
            """
            INSERT INTO spend_tracker (card_key, current_spend_inr, target_spend_inr, period_label, lounge_eligible)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(card_key) DO UPDATE SET
                current_spend_inr = excluded.current_spend_inr,
                target_spend_inr = excluded.target_spend_inr,
                period_label = excluded.period_label,
                lounge_eligible = excluded.lounge_eligible
            """,
            (key, rolling, target, period, eligible),
        )
    conn.commit()


def set_card_month_spend(
    card_key: str,
    month: str,
    amount: float,
    spend_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Update one month spend for a card and persist YAML."""
    data = dict(spend_config or load_spend_config())
    spends = data.setdefault("spends", {})
    card_spends = spends.setdefault(card_key, {})
    card_spends[month] = amount
    save_spend_config(data)
    return data


def set_card_rolling_spend(
    card_key: str,
    amount: float,
    spend_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Put entire rolling total into the last configured month."""
    data = dict(spend_config or load_spend_config())
    months = data.get("months") or []
    if not months:
        raise ValueError("No months configured in spend_tracker.yaml")
    spends = data.setdefault("spends", {})
    card_spends = spends.setdefault(card_key, {})
    for month in months[:-1]:
        card_spends[month] = 0
    card_spends[months[-1]] = amount
    save_spend_config(data)
    return data
