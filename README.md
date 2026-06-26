# table_extract_pdf_bulk

Extract **BF # 8** daily production parameters from blast furnace PDF reports using [pdfplumber](https://github.com/jsvine/pdfplumber), then stitch them into a single CSV for data science work.

## Quick start

```bash
pip install -r requirements.txt
python extract_bf8_daily.py --verbose
```

That's it. The script reads PDFs from the path in `drive_config.json` and writes **`BF8_merged_all.csv`**.

### Hot metal and slag quality (table-by-table, recommended)

Use `extract_hot_metal_slag.py` to build a **day-by-day BF-8 file** from the page-2 **HOT METAL AND SLAG QUALITY** table only. One clean row per PDF with averages, min/max ranges, and Till % Si.

```powershell
# Sample PDFs in the repo root
python extract_hot_metal_slag.py --input-dir . --verbose

# Full 3-year archive on F: drive
python extract_hot_metal_slag.py --from-config --recursive --verbose
```

Output: **`BF8_hot_metal_slag.csv`** and **`.xlsx`** with a clear date block (`date`, `report_date`, `year`, `month`, `day`) plus quality columns such as `HM_Si_pct_avg`, `HM_S_pct_avg`, `Slag_Basicity_avg`, etc.

### Skip iron ore analysis (table-by-table)

Use `extract_skip_iron_ore.py` for the page-2 **SKIP IRON ORE** chemical and sieve tables (BF # 8 row only).

```powershell
python extract_skip_iron_ore.py --input-dir . --verbose
python extract_skip_iron_ore.py --from-config --recursive --verbose
```

Output: **`BF8_skip_iron_ore.csv`** / **`.xlsx`** with `SkipIronOre_Fe_pct`, `SkipIronOre_SiO2_pct`, `SkipIronOre_Al2O3_pct`, `SkipIronOre_Moist_pct`, `SkipIronOre_plus40mm`, `SkipIronOre_minus10mm`, `SkipIronOre_MSize`, plus the same date columns.

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

**Page 1 (`extract_bf8_daily.py`):** `Production_T`, `CokeRate_kgTHM`, `FuelRate_kgTHM`, `RAFT_C`, etc.

**Hot metal / slag (`extract_hot_metal_slag.py`):** `HM_Si_pct_avg/min/max`, `HM_S_pct_avg/min/max`, `Slag_MgO_pct_avg/min/max`, `Slag_Al2O3_pct_avg`, `Slag_FeO_pct_avg`, `Slag_K2O_pct_avg`, `Slag_Basicity_avg/min/max`, `HM_P_pct_avg/min/max`, `HM_Si_pct_till`

**Skip iron ore (`extract_skip_iron_ore.py`):** `SkipIronOre_Fe_pct`, `SkipIronOre_SiO2_pct`, `SkipIronOre_Al2O3_pct`, `SkipIronOre_Moist_pct`, `SkipIronOre_plus40mm`, `SkipIronOre_minus10mm`, `SkipIronOre_MSize`

**Page 2 (combined extractor):** `HM_Si_pct_avg`, `HM_S_pct_avg`, `Slag_Basicity_avg`, `SkipSinter_Fe_pct`, etc.

See `KEY_PARAMS` and `QUALITY_PARAMS` in `extract_bf8_daily.py` for the full list.

## Python API

```python
from extract_bf8_daily import extract_bf8_combined
from extract_hot_metal_slag import extract_hot_metal_slag

record = extract_hot_metal_slag(r"F:\...\NEW P.D.14.02-12.pdf")
```

## Requirements

- Python 3.10+
- `pdfplumber`, `pandas`, `openpyxl` (Excel output)
