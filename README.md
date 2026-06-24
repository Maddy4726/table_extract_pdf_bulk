# table_extract_pdf_bulk

Extract **BF # 8** daily production parameters from blast furnace PDF reports using [pdfplumber](https://github.com/jsvine/pdfplumber), then stitch them into a single CSV for data science work.

## Quick start

```bash
pip install -r requirements.txt
python extract_bf8_daily.py --verbose
```

That's it. The script reads PDFs from the path in `drive_config.json` and writes **`BF8_merged_all.csv`**.

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
- `pdfplumber`, `pandas`
