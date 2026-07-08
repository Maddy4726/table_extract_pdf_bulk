"""Generate the CCIS Excel dashboard."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from src.import_data import airport_coverage_summary, card_airport_counts, load_portfolio_config
from src.lounge_engine import spend_recommendations

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "dashboard" / "Credit_Card_Intelligence_System.xlsx"


def _autosize_columns(writer_sheet) -> None:
    for column_cells in writer_sheet.columns:
        length = 0
        column = column_cells[0].column
        for cell in column_cells:
            if cell.value is not None:
                length = max(length, len(str(cell.value)))
        writer_sheet.column_dimensions[get_column_letter(column)].width = min(max(length + 2, 12), 40)


def build_dashboard(conn: sqlite3.Connection, output_path: Path | str | None = None) -> Path:
    output = Path(output_path or DEFAULT_OUTPUT)
    output.parent.mkdir(parents=True, exist_ok=True)
    config = load_portfolio_config()

    cards_df = pd.read_sql_query(
        "SELECT * FROM cards ORDER BY spend_priority_rank IS NULL, spend_priority_rank, card_name",
        conn,
    )
    counts = card_airport_counts(conn)
    cards_df["domestic_airports"] = cards_df["card_key"].map(counts)
    cards_df["lounge_spend_required"] = cards_df["lounge_spend_required"].map({1: "Yes", 0: "No"})

    matrix = pd.DataFrame(airport_coverage_summary(conn))
    card_keys = [card["key"] for card in config["cards"]]
    for key in card_keys:
        if key not in matrix.columns:
            matrix[key] = ""
    matrix = matrix[["airport", *card_keys, "best_free", "best_spend"]]

    spend_df = pd.DataFrame(spend_recommendations(conn))
    frequent = config.get("frequent_airports", [])
    frequent_df = matrix[matrix["airport"].isin([a.title() if a.islower() else a for a in frequent]) | matrix["airport"].isin(frequent)].copy()

    summary_rows = []
    for card in config["cards"]:
        key = card["key"]
        summary_rows.append(
            {
                "card": card["name"],
                "free_lounge_visits": "2/qtr, no spend" if key in ("dbs_supercard", "indusind_tiger") else "",
                "spend_for_lounge": card.get("lounge_spend_inr"),
                "spend_window_months": card.get("lounge_spend_window_months"),
                "domestic_airports": counts.get(key, 0),
                "spend_priority": card.get("spend_priority_rank"),
            }
        )
    summary_df = pd.DataFrame(summary_rows)

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary_df.to_excel(writer, sheet_name="Dashboard", index=False)
        cards_df.to_excel(writer, sheet_name="Card Master", index=False)
        matrix.to_excel(writer, sheet_name="Airport Matrix", index=False)
        frequent_df.to_excel(writer, sheet_name="Frequent Airports", index=False)
        spend_df.to_excel(writer, sheet_name="Spend Priority", index=False)

        for sheet_name in writer.sheets:
            sheet = writer.sheets[sheet_name]
            for cell in sheet[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="1F4E79")
                cell.alignment = Alignment(horizontal="center")
            _autosize_columns(sheet)

    return output
