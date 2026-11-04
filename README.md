
## Run the Analysis in Google Colab

Launch the Revenue Management Decision Support notebook directly from GitHub.

[![Open in Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/carlosjostemperor/rental-revenue-decision-support/blob/main/Revenue_Management_EDA.ipynb)

The notebook provides a reusable analytical workflow for evaluating pricing, occupancy, revenue, booking pace, and competitive positioning across short-term rental properties.


# Revenue Management Analytics

**Release 2.1.0** — A tested, auditable pricing-position analysis for one short-term rental property, built on four PriceLabs exports. It complements PriceLabs: it does not set prices, connect to PriceLabs, or change anything in any system.

**What it answers**

- Where does the property's advertised rate sit against a hand-picked comp set, date by date, on the dates it is still available? (mean, median, P25, P75, standard deviation, sample count, confidence interval)
- How fast is it booking (pace, lead time, length of stay, booking ADR) in a given **Booked Date** window?
- How do ADR, occupancy and **RevPAR** compare with the PriceLabs market benchmark, historically and forward?
- Are the four exports consistent with each other? (reservations reconciled with Report Builder by stay date)

**What it does not answer**

- It does not estimate price elasticity or the revenue-maximizing rate.
- It does not prove that price caused bookings.
- It does not observe competitors' realized occupancy; competitor unavailability is not a sale.

See [docs/METHODOLOGY.md](docs/METHODOLOGY.md) for formulas and limitations.

---

## Quick start in Google Colab

1. Download the project ZIP (or clone the project repository into Colab). The public repository must contain code and synthetic examples only.
2. Open `Revenue_Management_EDA.ipynb` in Colab and run the first cell. If the project is not present, it asks for the ZIP and extracts it safely.
3. To try the tool without real data, uncomment the line in section 1 that creates `data/example_synthetic`, and set `DATA_DIR = 'data/example_synthetic'` and `property_name='SYNTHETIC 6BR Pool Home'`.
4. For a real property:
   - put the four exports in `data/input/` with the exact names below;
   - set `property_name` and the date windows in section 1.
5. Choose **Runtime → Run all**.
   - A structural problem stops the run with a clear message, for example an unparseable value, an unknown booking status, an ambiguous listing name or a missing calendar date. Fix the input; do not bypass the check.
6. Check the displayed **decision status** and every non-PASS item. Set the attestations (`attest_*`) and your name only after verifying them, then rerun. An unresolved WARN produces `REVIEW_REQUIRED`, not `VALIDATED`.
7. Download the folder `output/<run_id>/` before the Colab session ends, including `REVIEW_SUMMARY.md` and `run_manifest.json`. Do not use a `FAILED` or `REVIEW_REQUIRED` run as a validated pricing recommendation.

Colab already includes pandas, numpy and matplotlib. No installation step is required.

### Local use

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt            # runtime
pip install -r requirements-dev.txt        # tests + local Jupyter
python -m pytest                           # run the test suite
jupyter notebook Revenue_Management_EDA.ipynb
```

---

## Input contract (four files in `data/input/`)

| File | PriceLabs export | Required columns |
|---|---|---|
| `competitor_calendar.csv` | Competitor Calendar | 3 header rows: listing names, then `prices`, `available`, `min_stay` per listing, then `Date`. Must cover every date of the forward window with no gaps. |
| `bookings.csv` | Bookings Report | `Listing Name`, `Booked Date`, `Check-in Date`, `Check-out Date`, `Rental Revenue`, `Length of Stay (Days)`. Recommended: `Booking Status`, `Booking Window (Days)`, `Reservation ID`. **Export all bookings of the property**, not filtered by booked date, so stay-date reconciliation works. |
| `report_builder_historical.csv` | Report Builder, historical **Stay Date Range** | `Listing Name`, `Rental ADR`, `Market ADR`, `Adjusted Occupancy %`, `Market Occupancy %`. Recommended: `Rental Revenue`, `Booked Nights`, `Number of Bookings`, `Rental RevPAR`, pickups, `Average Booking Window`, `Average LOS`. |
| `report_builder_forward.csv` | Report Builder, forward **Stay Date Range** | Same as above. |

**Accepted formats**

- Money: `1234.5`, `$1,234.50`, `(45.00)`. European `1.234,50` is rejected.
- Percent: `65%` or `65`.
- Dates: ISO with or without time, or numeric day/month orders, detected automatically.
  - Day-first vs month-first is resolved automatically in the calendar.
  - In the bookings report, an ambiguous date stops the run and asks you to set `bookings_date_format`.

## Configuration (notebook section 1)

| Setting | Meaning |
|---|---|
| `property_name` | Exact listing name. An exact match wins; a partial match must be unique in every file. |
| `booking_start`, `booking_end` | **Booked Date** (creation) window, inclusive. Bookings made at any time on the last day are included. |
| `historical_stay_start/end`, `forward_start/end` | The Stay Date Ranges selected in Report Builder. They are cross-checked against the bookings file. |
| `min_active_comps` (default 5) | Minimum number of available comps for a date to be compared. |
| `valid_booking_statuses`, `excluded_booking_statuses` | Status whitelist. Any other status value stops the run. |
| `duplicate_policy` | `warn` (default) flags suspected duplicate listings; `drop` removes only strong price-and-availability matches. Similar blocked-day calendars alone are a review flag, **never** a reason for automatic removal. |
| `exclude_comps` | Comp names removed after review. |
| `attest_*`, `analyst`, `reviewer` | Human verifications recorded in the manifest. |

## Outputs (`output/<run_id>/`)

**Tables**

| File | Content |
|---|---|
| `daily_positions.csv` | Every forward date: our price and availability, comp statistics, gap, band, minimum-stay flags and exclusion reason |
| `minimum_stay_sensitivity.csv` | Separate rate-gap summaries for dates with matched, different or unknown minimum stays |
| `summary_metrics.csv` | Executive metrics |
| `market_comparison.csv` | ADR, occupancy and RevPAR versus the market |
| `reconciliation.csv` | Bookings versus Report Builder |
| `duplicate_listings.csv` | Probable duplicate homes |
| `band_by_day_group.csv` | Price bands by weekday group |
| `booking_window_reservations.csv` | Reservations in the booking window, without guest or listing identifiers |
| `audit_checks.csv` | All PASS / WARN / FAIL checks |

**Other files**

- `position_summary.json` and `booking_summary.json`
- `REVIEW_SUMMARY.md` — outstanding checks and required reviewer actions
- Four PNG charts
- `run_manifest.json`, which records:
  - status and decision-use label;
  - SHA-256 of every input and output;
  - full configuration;
  - code version (package hash and git commit when available);
  - Python and library versions.

Each run gets a new folder; earlier evidence is never overwritten. The audit status is an explicit governance gate:

| Status | Meaning | Folder suffix |
|---|---|---|
| `VALIDATED` | All machine checks **and required attestations** passed; a separate human pricing decision is still mandatory. | No suffix |
| `REVIEW_REQUIRED` | At least one WARN. The run is useful for investigation but **not validated** for pricing decisions until the issue is reviewed and resolved. | `_REVIEW_REQUIRED` |
| `FAILED` | At least one FAIL. Results must **not** support pricing decisions. | `_FAILED` |

The manifest contains the unresolved review items, and `REVIEW_SUMMARY.md` lists them in readable form. Each output other than the self-referential manifest has a SHA-256 recorded in the manifest. Human acceptance of a remaining warning must be documented; it does not silently transform the exported run into `VALIDATED`.

## Project structure

```text
revenue-management-analytics/
  Revenue_Management_EDA.ipynb   # thin Colab/Jupyter front end (no calculations)
  rm_analytics/                  # tested package
    config.py      parsing.py    loaders.py   duplicates.py
    metrics.py     audit.py      pipeline.py  export.py
    charts.py      synthetic.py
  tests/                         # pytest suite (synthetic data only)
  data/input/                    # real exports go here (git-ignored)
  data/example_synthetic/        # generated example data, no real information
  docs/                          # methodology, fix report, test results, migration guide
```

## Monthly operating procedure

1. **Define** the property, windows, comp set and analyst.
2. **Export** the four files with identical property filters. Screenshot the Report Builder date ranges.
3. **Run** the notebook top to bottom.
4. **Review** every WARN, inspect `minimum_stay_sensitivity.csv`, review flagged duplicate homes, spot-check five dates in the PriceLabs UI, and set the attestations after independent verification. Re-run to update the status. If any warning remains, document its limits and retain `REVIEW_REQUIRED`.
5. **Interpret** using the conclusion framework at the end of the notebook. Keep observations, hypotheses and decisions separate.
6. **Approve** any rate change as a pricing test (hypothesis, dates, magnitude, monitoring metric, rollback rule) in a separate decision.
7. **Archive** the run folder and the source files in approved restricted storage.

## Data policy

The **distributed project ZIP** contains no real booking, competitor or financial data. The project is suitable for hosting publicly **only with synthetic examples and approved documentation**. `data/input/` and `output/` are git-ignored. Never commit operational CSVs, run outputs, screenshots or nonapproved business reports. The test suite checks for certain known confidential identifiers and saved notebook outputs, but cannot identify all sensitive content. Historical Git commits are not erased by new `.gitignore` rules; confirm that any existing exposure is authorized by the data owner.

## Documentation

- [docs/METHODOLOGY.md](docs/METHODOLOGY.md): formulas, statistical choices, limitations
- [docs/FIX_REPORT.md](docs/FIX_REPORT.md): audit findings and how each was addressed
- [docs/TEST_RESULTS.md](docs/TEST_RESULTS.md): v2 synthetic test record
- [docs/V2_1_VALIDATION.md](docs/V2_1_VALIDATION.md): v2.1 enhancements, independent testing and remaining review items
- [docs/MIGRATION_GUIDE.md](docs/MIGRATION_GUIDE.md): replacing the previous version on GitHub
- [DATA_CHECKLIST.md](DATA_CHECKLIST.md): per-run checklist
- [CHANGELOG.md](CHANGELOG.md)
