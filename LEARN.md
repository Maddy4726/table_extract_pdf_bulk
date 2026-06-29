# Learning guide — BF-8 PDF extraction

This branch is a **simplified** version of the repo for reading and experimenting with the code. There is no Google Drive config, no `drive_config.json`, and no path-discovery helpers. You point each script at a folder on your PC that contains the daily PDF files.

## Setup

```bash
git checkout cursor/learn-simple-extract-555e
pip install -r requirements.txt
```

## Run extraction

Point `--input-dir` at your PDF folder (use quotes on Windows):

```powershell
# Sample PDFs in the repo root
python extract_hot_metal_slag.py --input-dir . --verbose

# Full archive — search subfolders for each financial year
python run_all_extractors.py --input-dir "F:\Fuel-Slag Rate Reduction Project\Blast Furnace Data\BF-8\Production and Quality\PDF - Daily Production Reports" --recursive --output-dir output --format csv --verbose
```

`run_all_extractors.py` runs all eight table extractors and writes one CSV/Excel file per table under `output/`.

## Repo layout

| File | Role |
|------|------|
| `pdf_paths.py` | Finds `*.pdf` files under `--input-dir` (optionally recursive). |
| `extract_cli.py` | Shared CLI: `--input-dir`, `--recursive`, `--pdf-pattern`, `--verbose`. |
| `extract_table_utils.py` | Date columns, CSV/Excel output, `stitch_records()` helper. |
| `extract_bf8_daily.py` | Original combined extractor (page 1 + 2 summary fields). |
| `extract_*.py` | One script per table — each has `extract_*()` and `stitch_*()`. |
| `run_all_extractors.py` | Runs every `stitch_*()` in one command. |
| `test_extraction_fixes.py` | Unit tests (run with `pytest`). |

## How one extractor works

Every table script follows the same pattern:

1. **Open PDF** with `pdfplumber`.
2. **Find the table** on page 2 (or page 1 for production parameters).
3. **Read the BF # 8 row** and map cells to named columns (`HM_Si_pct_avg`, `Pellet_Fe_pct`, …).
4. **Return a dict** with `report_date`, `source_file`, and the value columns.
5. **`stitch_*()`** collects one dict per PDF, sorts by date, builds a pandas DataFrame, and writes CSV/Excel.

Example — hot metal / slag (`extract_hot_metal_slag.py`):

```python
from extract_hot_metal_slag import extract_hot_metal_slag, stitch_hot_metal_slag

# One PDF
row = extract_hot_metal_slag(r"NEW P.D.14.01-01.pdf")
print(row["HM_Si_pct_avg"], row["Slag_Basicity_avg"])

# Many PDFs → CSV
stitch_hot_metal_slag(
    ["NEW P.D.14.01-01.pdf", "NEW P.D.14.01-02.pdf"],
    "BF8_hot_metal_slag",
    output_format="csv",
    verbose=True,
)
```

## All extractors

| Script | Output base name | PDF page / table |
|--------|------------------|------------------|
| `extract_production_parameters.py` | `BF8_production_parameters` | Page 1 — full PARAMETERS table (~100+ cols) |
| `extract_hot_metal_slag.py` | `BF8_hot_metal_slag` | Page 2 — HOT METAL AND SLAG QUALITY |
| `extract_skip_iron_ore.py` | `BF8_skip_iron_ore` | Page 2 — SKIP IRON ORE |
| `extract_pellet_analysis.py` | `BF8_pellet_analysis` | Page 2 — PELLET CHEMICAL AND SEIVE ANALYSIS |
| `extract_skip_sinter.py` | `BF8_skip_sinter` | Page 2 — SKIP SINTER chemistry |
| `extract_skip_fines.py` | `BF8_skip_fines` | Page 2 — % FINES IN BF SKIP SINTER + SKIP COKE |
| `extract_coke_quality.py` | `BF8_coke_quality` | Page 2 — COKE QUALITY |
| `extract_sinter_plant.py` | `BF8_sinter_plant` | Page 2 — SINTER PLANT-2 / SINTER PLANT-3 |

## Suggested reading order

1. `pdf_paths.py` and `extract_cli.py` — how input paths are resolved.
2. `extract_table_utils.py` — shared date handling and file output.
3. `extract_hot_metal_slag.py` — smallest complete table extractor (good first read).
4. `extract_production_parameters.py` — largest table; shows row-key building for page 1.
5. `extract_skip_fines.py` — handles merged/split/wide table layouts.
6. `run_all_extractors.py` — ties everything together.

## Tests

```bash
pytest test_extraction_fixes.py -v
```

Tests use the sample PDFs in the repo root (`NEW P.D.14.01-*.pdf`) when present.

## What was removed on this branch

- `drive_config.json`, `drive_paths.py`, `find_pdf_folders.py`
- `--from-config` CLI flag

Use `--input-dir` everywhere instead.
