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

### Pellet chemical and sieve analysis (table-by-table)

Use `extract_pellet_analysis.py` for the page-2 **PELLET CHEMICAL AND SEIVE ANALYSIS** table (BF # 8).

```powershell
python extract_pellet_analysis.py --input-dir . --verbose
python extract_pellet_analysis.py --from-config --recursive --verbose
```

Output: **`BF8_pellet_analysis.csv`** / **`.xlsx`** with `Pellet_Fe_pct`, `Pellet_SiO2_pct`, `Pellet_Al2O3_pct`, `Pellet_CaO_pct`, `Pellet_MgO_pct`, `Pellet_plus10mm`, `Pellet_minus5mm`, `Pellet_MSize`, `Pellet_Basicity`, plus date columns.

### Skip sinter chemical analysis (table-by-table)

Use `extract_skip_sinter.py` for the page-2 **SKIP SINTER** chemistry table (`% Fe`, `% SiO2`, `% Al2O3`, `% CaO`, `% MgO`, `Basicity`) on the BF # 8 row.

```powershell
python extract_skip_sinter.py --input-dir . --verbose
python extract_skip_sinter.py --from-config --recursive --verbose
```

Output: **`BF8_skip_sinter.csv`** / **`.xlsx`**

Note: many newer daily PDFs omit this chemical block and only show **% fines in BF skip sinter** (handled by `extract_skip_fines.py` below).

### Skip sinter and skip coke fines (table-by-table)

Use `extract_skip_fines.py` for the page-2 **% FINES IN BF SKIP SINTER** and **SKIP COKE** sieve tables (BF # 8).

```powershell
python extract_skip_fines.py --input-dir . --verbose
python extract_skip_fines.py --from-config --recursive --verbose
```

Output: **`BF8_skip_fines.csv`** / **`.xlsx`** with sinter columns (`SkipSinterFines_minus10mm`, `_minus5mm`, `_MSize`, optional `_ShiftA/B/C` or `_TotalFe`) and coke columns (`SkipCokeFines_minus40mm`, `_minus25mm`, `_MSize`), plus date columns.

Handles merged tables (sinter + coke on one row), split tables (separate sinter and coke blocks), and wide layouts that include iron ore sieve between sinter and coke.

### Coke quality (table-by-table)

Use `extract_coke_quality.py` for the page-2 **COKE QUALITY** table: proximate analysis, cold strength (M-40, M-10), and hot strength (CSR, CRI) for CSP-I through CSP-IV, plus BF # 8 stock-house surface mix coke CSR/CRI.

```powershell
python extract_coke_quality.py --input-dir . --verbose
python extract_coke_quality.py --from-config --recursive --verbose
```

Output: **`BF8_coke_quality.csv`** / **`.xlsx`** with `CokeQuality_CSP1_Moisture` … `CokeQuality_CSP4_CRI` and `CokeQuality_BF8_Mix_CSR`, `CokeQuality_BF8_Mix_CRI`, plus date columns.

### Sinter plant chemical analysis (table-by-table)

Use `extract_sinter_plant.py` for the page-2 **SINTER PLANT-2** and **SINTER PLANT-3** chemistry tables (% Fe, % FeO, % SiO2, % Al2O3, % CaO, % MgO, % MnO, CaO-SiO2, Basicity).

```powershell
python extract_sinter_plant.py --input-dir . --verbose
python extract_sinter_plant.py --from-config --recursive --verbose
```

Output: **`BF8_sinter_plant.csv`** / **`.xlsx`** with day-average and shift-sample columns such as `SinterPlant2_DayAvg_Fe_pct`, `SinterPlant2_AO_Basicity`, `SinterPlant3_C2_Fe_pct`, etc.

### Production parameters — complete page 1 table (recommended)

Use `extract_production_parameters.py` for the **full page-1 PARAMETERS table** for BF # 8 — not just the 23 summary fields from `extract_bf8_daily.py`.

```powershell
python extract_production_parameters.py --input-dir . --verbose
python extract_production_parameters.py --from-config --recursive --verbose
```

Output: **`BF8_production_parameters.csv`** / **`.xlsx`** with ~100+ columns such as:

- `Prod_01_production`, `Prod_01_1a_hMLoads`, `Prod_01_bestDailyProd`
- `Prod_07_a_cokeRt`, `Prod_07_a_cokeRt_till`, `Prod_07_a_cokeRt_yearlyRate`
- `Prod_11_11a_fuelRate`, `Prod_12_a_slagRate`, `Prod_13_a_ironOreRate`
- `Prod_20_burdenRatio`, `Prod_26_blastRate`, `Prod_32_tD`, `Prod_40_a_pctOxyEnrch`
- Till / Yearly Rate sub-rows, operating times, and more

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

**Pellet analysis (`extract_pellet_analysis.py`):** `Pellet_Fe_pct`, `Pellet_SiO2_pct`, `Pellet_Al2O3_pct`, `Pellet_CaO_pct`, `Pellet_MgO_pct`, `Pellet_plus10mm`, `Pellet_minus5mm`, `Pellet_MSize`, `Pellet_Basicity`

**Skip sinter chemistry (`extract_skip_sinter.py`):** `SkipSinter_Fe_pct`, `SkipSinter_SiO2_pct`, `SkipSinter_Al2O3_pct`, `SkipSinter_CaO_pct`, `SkipSinter_MgO_pct`, `SkipSinter_Basicity`

**Skip fines (`extract_skip_fines.py`):** `SkipSinterFines_minus10mm`, `SkipSinterFines_minus5mm`, `SkipSinterFines_MSize`, `SkipSinterFines_ShiftA/B/C`, `SkipSinterFines_TotalFe`, `SkipCokeFines_minus40mm`, `SkipCokeFines_minus25mm`, `SkipCokeFines_MSize`

**Coke quality (`extract_coke_quality.py`):** `CokeQuality_CSP1_Moisture` … `CokeQuality_CSP4_CRI`, `CokeQuality_BF8_Mix_CSR`, `CokeQuality_BF8_Mix_CRI`

**Sinter plant chemistry (`extract_sinter_plant.py`):** `SinterPlant2_DayAvg_Fe_pct`, `SinterPlant2_AO_Basicity`, `SinterPlant3_DayAvg_Fe_pct`, shift samples `AO`–`C2`, etc.

**Production parameters (`extract_production_parameters.py`):** complete page-1 PARAMETERS table — `Prod_01_production`, `Prod_07_a_cokeRt`, `Prod_11_11a_fuelRate`, `Prod_12_a_slagRate`, Till/Yearly Rate rows, blast, downtime, and ~100+ more columns.

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
