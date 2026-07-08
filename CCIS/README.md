# Credit Card Intelligence System (CCIS)

Personal credit card portfolio manager focused on **maximizing domestic airport lounge coverage** across your active cards.

Built from official issuer lounge lists (Axis PDF, ICICI consolidated list, HDFC/AU HOI portals, DBS T&C page, IndusInd program PDF).

## Your portfolio (configured)

| Card | Lounge visits | Spend for lounge |
|------|---------------|------------------|
| DBS SuperCard | 2/qtr | None |
| IndusInd Tiger | 2/qtr | None |
| HDFC Diners Privilege | Eligible after spend | ₹60,000 / 3 months |
| ICICI Rubyx | 2/qtr after spend | ₹75,000 / 3 months |
| AU Spont | 2/qtr after spend | ₹50,000 / 3 months |
| Axis Rewards | 2/qtr (Set A) | ₹50,000 / 3 months |

SBI Prime is excluded (add-on, inactive).

## Quick start

```bash
cd CCIS
pip install -r requirements.txt
python main.py build
```

This creates:

- `database/ccis.db` — SQLite database
- `dashboard/Credit_Card_Intelligence_System.xlsx` — Excel workbook with Dashboard, Card Master, Airport Matrix, Frequent Airports, Spend Priority sheets

## v1.1 — Spend tracking & analysis

### Update your spends

Edit `config/spend_tracker.yaml` with monthly amounts per card, then rebuild:

```bash
python main.py build
```

Or set a rolling total from the CLI:

```bash
python main.py spend set axis_rewards 31250
python main.py spend set hdfc_diners_privilege 42000 --month 2026-06
python main.py milestones
```

### New Excel sheets

| Sheet | Purpose |
|-------|---------|
| **Spend Tracker** | Monthly spends per card + rolling 3-month total |
| **Milestones** | Progress vs lounge threshold, eligible Yes/No |
| **Unique Airports** | Airports each card adds beyond DBS + Tiger |
| **Redundancy** | % overlap between card networks |

The **Dashboard** sheet now includes lounge eligibility at a glance.

## CLI commands

```bash
python main.py build          # Rebuild DB + Excel
python main.py milestones     # Lounge spend progress
python main.py spend set axis_rewards 31250
python main.py coverage       # Spend priority ranking
python main.py lounge Raipur  # Airport lookup
python main.py matrix         # Airport × card table
```

## Spend priority (for max airports)

Based on official lounge lists and **total domestic airport coverage**:

1. **ICICI Rubyx** — widest airport set in your portfolio (includes Raipur, Nagpur, Trichy, Ayodhya, Navi Mumbai)
2. **HDFC Diners Privilege** — very close second; strongest overall Diners/HOI network
3. **AU Spont** — strong Tier-2 coverage
4. **Axis Rewards** — Set A metros only (lowest priority for spend)

Use **DBS + Tiger** first (no spend). For spend-qualified cards, prioritize **Rubyx** if you fly via Raipur/Nagpur; otherwise **HDFC** and **Rubyx** together give near-maximum domestic coverage.

## Project structure

```
CCIS/
├── config/portfolio.yaml    # Your cards and spend thresholds
├── data/sources/            # Reference PDFs (optional)
├── database/ccis.db         # Generated SQLite DB
├── dashboard/               # Generated Excel workbook
├── src/                     # Import, lounge engine, dashboard
├── tests/
└── main.py                  # CLI
```

## Data sources

| Card | Source |
|------|--------|
| Axis Rewards | Axis Set A official PDF |
| HDFC Diners Privilege | HOI HDFC Diners lounge list |
| ICICI Rubyx | ICICI domestic consolidated PDF |
| AU Spont | HOI AU credit card lounge list |
| DBS SuperCard | DBS official lounge T&C page |
| IndusInd Tiger | IndusInd airport lounge program PDF |

## Roadmap

- **v1.2** — Statement PDF parser for automatic spend updates
- Category reward optimizer (fuel, IRCTC, insurance, etc.)
- Card advisor for new applications

## Tests

```bash
python -m unittest discover -s tests -v
```
