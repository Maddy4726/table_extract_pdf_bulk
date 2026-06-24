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

The script extracts **page 1** production parameters and **page 2** hot-metal / slag quality data for BF # 8.

## Quick start (Google Drive — recommended)

One-time setup:

```bash
pip install -r requirements.txt
cp drive_config.json.example drive_config.json   # edit if your Drive path differs
```

Then run with **no arguments** — the script finds all `DailyProdReports_FY*` folders in Drive, extracts every PDF, and writes `BF8_merged_all.csv`:

```bash
python extract_bf8_daily.py --verbose
```

### Where it looks for your PDFs

| Environment | How Drive is accessed |
|-------------|----------------------|
| **Google Colab** | Auto-mounts Drive at `/content/drive`, then uses `drive_root` from config |
| **Local PC (Drive desktop app)** | `~/Google Drive/My Drive/...` or macOS `CloudStorage/GoogleDrive-*/My Drive/...` |
| **Any machine** | Set `BF8_DRIVE_ROOT` to the full path of the parent folder containing `DailyProdReports_FY*` |

Your notebook used this path inside Drive:

```
Blast Furnace Data/BF-8/Production and Quality/PDF - Daily Production Reports/
  DailyProdReports_FY2023-24/
  DailyProdReports_FY2024-25/
  DailyProdReports_FY2025-26/
  ... (any folder matching DailyProdReports_FY*)
```

Override with environment variable if needed:

```bash
export BF8_DRIVE_ROOT="/content/drive/MyDrive/Blast Furnace Data/BF-8/Production and Quality/PDF - Daily Production Reports"
python extract_bf8_daily.py --verbose
```

### Windows (if auto-detect fails)

Your PDFs may be on the **`G:` drive** (common with Google Drive for desktop) or not synced locally at all.

**Option A — set full path in `drive_config.json`:**

```json
{
  "drive_base": "G:\\My Drive\\Blast Furnace Data\\BF-8\\Production and Quality\\PDF - Daily Production Reports",
  "drive_root": "Blast Furnace Data/BF-8/Production and Quality/PDF - Daily Production Reports"
}
```

**Option B — PowerShell env var (one session):**

```powershell
$env:BF8_DRIVE_ROOT = "G:\My Drive\Blast Furnace Data\BF-8\Production and Quality\PDF - Daily Production Reports"
python extract_bf8_daily.py --verbose
```

**Option C — point directly at one fiscal-year folder:**

```powershell
python extract_bf8_daily.py --input-dir "G:\My Drive\...\DailyProdReports_FY2024-25" --page all --verbose
```

**Find where your folders are:**

```powershell
python find_pdf_folders.py
```

If PDFs exist only in cloud Drive (not on your PC), use **Google Colab** instead.

### Google Colab

```python
!pip install pdfplumber pandas
!git clone https://github.com/Maddy4726/table_extract_pdf_bulk.git
%cd table_extract_pdf_bulk
!python extract_bf8_daily.py --verbose
# Output: BF8_merged_all.csv
```

## Manual folder paths (optional)

```bash
# Page 1 only (production parameters)
python extract_bf8_daily.py \
  --input-dir "/path/to/DailyProdReports_FY2024-25" \
  --output BF8_24-25.csv \
  --page 1 \
  --verbose

# Pages 1 + 2 merged
python extract_bf8_daily.py \
  --input-dir \
    "/path/to/DailyProdReports_FY2023-24" \
    "/path/to/DailyProdReports_FY2024-25" \
  --output BF8_merged.csv \
  --page all \
  --verbose
```

## Page 1 columns (production)

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

## Page 2 columns (quality)

| CSV column | Source on page 2 |
|------------|------------------|
| `HM_Si_pct_avg` | Hot metal & slag quality table — Avg. % 'Si' |
| `HM_S_pct_avg` | Avg. % 'S' |
| `HM_P_pct_avg` | Avg. % 'P' |
| `Slag_MgO_pct_avg` | Avg. % MgO |
| `Slag_Al2O3_pct_avg` | Avg. % Al2O3 |
| `Slag_FeO_pct_avg` | Avg. % FeO |
| `Slag_K2O_pct_avg` | Avg. % K2O |
| `Slag_Basicity_avg` | BASICITY(-) |
| `SkipSinter_Fe_pct` | Skip sinter table — BF # 8 row |
| `SkipSinter_SiO2_pct` | ... |
| `SkipSinter_Basicity` | ... |
| `Seive_minus10mm` | Sieve / fines table — BF # 8 row |
| `Pellet_plus10mm` | Pellet chemical table — BF # 8 => row |

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
from extract_bf8_daily import extract_bf8, extract_bf8_page2, extract_bf8_combined

record = extract_bf8("sample_report.pdf")
quality = extract_bf8_page2("sample_report.pdf")
merged = extract_bf8_combined("sample_report.pdf")
```

## Next steps for your 5-year dataset

1. Run with `--page all` to get one modeling-ready CSV with production + quality features.
2. Point `--input-dir` at each fiscal-year folder (or use `--recursive` on a parent directory).
3. Extend `KEY_PARAMS` / `QUALITY_PARAMS` for additional rows.
4. Page 3 (stoppage log) can be added next if you need downtime features.

## Requirements

- Python 3.10+
- `pdfplumber`, `pandas` (see `requirements.txt`)
