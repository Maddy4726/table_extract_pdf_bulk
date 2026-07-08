# Drop monthly statement PDFs here (one folder per bank).

Subfolders:

- `axis/` → Axis Rewards
- `hdfc/` → HDFC Diners Privilege
- `icici/` → ICICI Rubyx
- `au/` → AU Spont
- `dbs/` → DBS SuperCard
- `indusind/` → IndusInd Tiger

Then run from the CCIS directory:

```bash
python main.py statements import --rebuild
```

Tip: include the statement month in the filename, e.g. `axis_2026-05.pdf`.
