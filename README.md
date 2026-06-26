# table_extract_pdf_bulk

Extract **BF # 8** daily production parameters from blast furnace PDF reports using [pdfplumber](https://github.com/jsvine/pdfplumber), then stitch them into a single CSV for data science work.

## Quick start

```bash
pip install -r requirements.txt
python extract_bf8_daily.py --verbose
```

That's it. The script reads PDFs from the path in `drive_config.json` and writes **`BF8_merged_all.csv`**.

### Extract every table row (for EDA cleanup)

Use `extract_all_tables.py` to dump **all rows from all PDF tables** (pages 1–3) into CSV and/or Excel. Each row keeps metadata (`date`, `source_file`, `page`, `table_index`, `table_title`, `row_index`) plus the extracted cell values.

```bash
# Sample PDFs in the repo root (NEW P.D.*.pdf)
python extract_all_tables.py --input-dir . --verbose

# Wide layout (default): one output row per table row -> bf8_all_rows.csv / .xlsx
python extract_all_tables.py --input-dir . --output bf8_all_rows --format both

# Long layout: one row per non-empty cell (good for filtering in Excel)
python extract_all_tables.py --input-dir . --layout long --output bf8_all_rows_long --format csv

# Both layouts at once
python extract_all_tables.py --input-dir . --layout both --output bf8_all_rows --format both
```

When you pass `--input-dir`, only files matching `NEW P.D.*.pdf` are used by default. Override with `--pdf-pattern "*.pdf"`.

For your full archive on `F:\`, use config mode (same folders as the curated extractor):

```powershell
python extract_all_tables.py --from-config --recursive --verbose
```

### Default PDF folder (your local PC)

```
F:\Fuel-Slag Rate Reduction Project\Blast Furnace Data\BF-8\Production and Quality\PDF - Daily Production Reports\
  DailyProdReports_FY2023-24\
  DailyProdReports_FY2024-25\
  DailyProdReports_FY2025-26\
```

To change the path, edit `pdf_root` in `drive_config.json`.

### Verify the path before extracting

```powershell
python find_pdf_folders.py
```

## What the PDF contains

| Page | Content |
|------|---------|
| 1 | Main **PARAMETERS** table (production, fuel rate, blast, burden, etc.) |
| 2 | Hot metal / slag quality, skip sinter, sieve analysis |
| 3 | Stoppage log, skip counts, CDI records |

Default extraction uses **pages 1 + 2** (`--page all`).

## Manual folder override (optional)

```powershell
python extract_bf8_daily.py --input-dir "F:\...\DailyProdReports_FY2024-25" --page all --verbose
```

## Output columns

**Page 1:** `Production_T`, `CokeRate_kgTHM`, `FuelRate_kgTHM`, `RAFT_C`, etc.

**Page 2:** `HM_Si_pct_avg`, `HM_S_pct_avg`, `Slag_Basicity_avg`, `SkipSinter_Fe_pct`, etc.

See `KEY_PARAMS` and `QUALITY_PARAMS` in `extract_bf8_daily.py` for the full list.

## Python API

```python
from extract_bf8_daily import extract_bf8_combined

record = extract_bf8_combined(r"F:\...\NEW P.D.14.02-12.pdf")
```

## Requirements

- Python 3.10+
- `pdfplumber`, `pandas`, `openpyxl` (Excel output)
