# table_extract_pdf_bulk

Extract **BF # 8** daily production parameters from blast furnace PDF reports using [pdfplumber](https://github.com/jsvine/pdfplumber), then stitch them into a single CSV for data science work.

The original exploratory workflow lives in `bf8_extraction_tutorial_BSP_code_final (1).ipynb` (Google Colab). This repo adds a local command-line script that runs the same extraction across many PDF folders.

## What the PDF contains

Each daily report is typically **3 pages**:

| Page | Content |
|------|---------|
| 1 | Main **PARAMETERS** table (production, fuel rate, blast, burden, etc.) for BF # 4–8 |
| 2 | Hot metal / slag quality, raw material analysis, coke chemistry |
| 3 | Stoppage log, skip counts, CDI records, monthly summaries |

The script focuses on **page 1**, table 1 (the large ~120-row PARAMETERS grid). It finds the row containing `PARAMETERS` and `BF # 8`, then reads the BF # 8 column for each target parameter.

## Quick start

```bash
pip install -r requirements.txt

# One fiscal-year folder
python extract_bf8_daily.py \
  --input-dir "/path/to/DailyProdReports_FY2024-25" \
  --output BF8_24-25.csv \
  --verbose

# Stitch multiple years together
python extract_bf8_daily.py \
  --input-dir \
    "/path/to/DailyProdReports_FY2023-24" \
    "/path/to/DailyProdReports_FY2024-25" \
    "/path/to/DailyProdReports_FY2025-26" \
  --output BF8_merged.csv
```

## Extracted columns

| CSV column | PDF parameter |
|------------|---------------|
| `Date` | Header text `DATE- dd. Mon. yyyy` |
| `Production_T` | PRODUCTION |
| `CokeRate_kgTHM` | COKE Rt. |
| `CDI_Rate_kgTHM` | COAL DUST INJ. |
| `FuelRate_kgTHM` | FUEL RATE |
| `RAFT_C` | RAFT |
| `Iron_ore_rate_kgTHM` | IRON ORE RATE |
| `SinterRate_kgTHM` | SINTER Rt. |
| ... | (see `KEY_PARAMS` in `extract_bf8_daily.py`) |

Numeric columns are coerced with `pd.to_numeric`. Literal `0` values are converted to `NA` by default (BF # 8 was often idle on older reports). Use `--keep-zero` to preserve zeros.

## Notebook vs script

| | Notebook | `extract_bf8_daily.py` |
|---|----------|------------------------|
| Environment | Google Colab + Drive | Local / server |
| Scope | Tutorial + EDA + ML | Bulk PDF → CSV |
| Parameter matching | Exact string match | Text parse first, table fallback |

### Fixes applied in the script

The notebook had two parameter labels with extra spaces that never matched the PDF:

- `IRON  ORE RATE` → `IRON ORE RATE`
- `SLAG  RATE` → `SLAG RATE`

When BF # 5 is idle, pdfplumber sometimes leaves that table cell empty and shifts values. The script reads BF # 8 from page text first (5th furnace number on the parameter line), then falls back to the table.

## Test on a single PDF (Python)

```python
from extract_bf8_daily import extract_bf8

record = extract_bf8("sample_report.pdf", verbose=True)
print(record)
```

## Next steps for your 5-year dataset

1. Point `--input-dir` at each fiscal-year folder (or use `--recursive` on a parent directory).
2. Merge yearly CSVs with `pd.concat` if you prefer separate runs.
3. Extend `KEY_PARAMS` for additional rows from page 1, or add a second extractor for page 2 quality tables.
4. Use the notebook’s EDA / modeling cells on the stitched CSV.

## Requirements

- Python 3.10+
- `pdfplumber`, `pandas` (see `requirements.txt`)
