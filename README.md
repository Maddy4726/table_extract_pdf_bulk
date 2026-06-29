# table_extract_pdf_bulk

Extract **BF # 8** daily production data from blast furnace PDF reports using [pdfplumber](https://github.com/jsvine/pdfplumber), then stitch results into CSV/Excel files for analysis.

> **Learning branch:** see [LEARN.md](LEARN.md) for a walkthrough of the code and how each extractor fits together.

## Quick start

```bash
pip install -r requirements.txt

# One table (sample PDFs in repo root)
python extract_hot_metal_slag.py --input-dir . --verbose

# All tables at once
python run_all_extractors.py --input-dir . --output-dir output --format csv --verbose
```

On your PC, pass the folder that contains the daily PDFs:

```powershell
python run_all_extractors.py --input-dir "F:\...\DailyProdReports_FY2024-25" --recursive --output-dir output --format csv --verbose
```

For a tree with multiple financial-year subfolders (`DailyProdReports_FY2023-24`, `FY2024-25`, …), add `--recursive`.

## CLI options (all extractors)

| Flag | Meaning |
|------|---------|
| `--input-dir PATH [PATH ...]` | **Required.** Folder(s) on your PC with PDF files. |
| `--recursive` | Search subfolders for PDFs. |
| `--pdf-pattern` | Filename filter (default: `NEW P.D.*.pdf`). |
| `--output` / `--output-dir` | Where to write results (per-script default or `output/`). |
| `--format csv\|excel\|both` | Output format (default: `both`). |
| `--verbose` | Per-file progress and warnings. |
| `--keep-zero` | Keep literal `0` instead of converting to NA. |

## Extractors

| Script | Output | Content |
|--------|--------|---------|
| `extract_production_parameters.py` | `BF8_production_parameters` | Page 1 — full PARAMETERS table |
| `extract_hot_metal_slag.py` | `BF8_hot_metal_slag` | Hot metal / slag quality |
| `extract_skip_iron_ore.py` | `BF8_skip_iron_ore` | Skip iron ore chemistry & sieve |
| `extract_pellet_analysis.py` | `BF8_pellet_analysis` | Pellet chemistry & sieve |
| `extract_skip_sinter.py` | `BF8_skip_sinter` | Skip sinter chemistry |
| `extract_skip_fines.py` | `BF8_skip_fines` | Skip sinter & coke fines |
| `extract_coke_quality.py` | `BF8_coke_quality` | Coke quality (CSP-I–IV, BF mix) |
| `extract_sinter_plant.py` | `BF8_sinter_plant` | Sinter plant 2 & 3 chemistry |
| `extract_bf8_daily.py` | `BF8_merged_all.csv` | Legacy combined page 1+2 summary |
| `run_all_extractors.py` | `output/BF8_*` | Runs all eight table extractors |

## What the PDF contains

| Page | Content |
|------|---------|
| 1 | Main **PARAMETERS** table (production, fuel rate, blast, burden, etc.) |
| 2 | Hot metal / slag quality, skip materials, sieve analysis, coke, sinter plant |
| 3 | Stoppage log, skip counts, CDI records |

## Python API

```python
from extract_hot_metal_slag import extract_hot_metal_slag

record = extract_hot_metal_slag(r"F:\...\NEW P.D.14.02-12.pdf")
print(record["HM_Si_pct_avg"], record["Slag_Basicity_avg"])
```

## Requirements

- Python 3.10+
- `pdfplumber`, `pandas`, `openpyxl` (Excel output)

## Tests

```bash
pytest test_extraction_fixes.py -v
```
