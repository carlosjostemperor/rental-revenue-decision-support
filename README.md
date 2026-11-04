
# Rental Revenue Decision Support

**A Python-based, auditable Revenue Management analytics framework for short-term rental properties.**

[![Open in Google Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/carlosjostemperor/rental-revenue-decision-support/blob/main/Revenue_Management_EDA.ipynb)

## Overview

Rental Revenue Decision Support is a reusable analytical framework designed to support evidence-based pricing and revenue decisions for short-term rental properties.

Built with Python and Google Colab, the system combines PriceLabs booking reports, market benchmarks, and competitor pricing data into a structured and auditable analysis.

The project is designed to **complement PriceLabs, not replace it**.

Its purpose is to help Revenue Managers investigate property performance, identify potential pricing opportunities, evaluate booking behavior, and document the evidence supporting their recommendations.

The same analytical workflow can be reused across different properties.

## Key Business Questions

The framework helps answer:

1. How is a property priced compared with the market and similar homes?
2. How do ADR, occupancy, and RevPAR compare with market benchmarks?
3. Is booking activity unusually strong or weak?
4. What do booking lead time and length of stay reveal?
5. How do minimum-stay requirements affect price comparisons?
6. Are there indications of potential underpricing or overpricing?
7. What evidence supports a pricing recommendation?
8. Can the results be reproduced and independently audited?

The framework does not automatically change prices or calculate a guaranteed optimal nightly rate.

---

## Quick Start — Google Colab

**No project ZIP download or installation is required.**

### Step 1 — Open the notebook

Click the button below:

[![Open in Google Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/carlosjostemperor/rental-revenue-decision-support/blob/main/Revenue_Management_EDA.ipynb)

The notebook opens directly from this repository.

### Step 2 — Connect GitHub to Colab

Run:

`0 | Connect GitHub and Colab (automatic)`

The notebook automatically:

- Clones the public GitHub repository into the Colab runtime.
- Loads the `rm_analytics` Python package.
- Checks the current GitHub code revision.
- Refreshes the code when the setup cell is run again.

There is no need to upload the project source code.

**Important:** This is a one-way GitHub-to-Colab code synchronization. The notebook does not automatically upload data, results, or code changes to GitHub.

### Step 3 — Select your data source

Two modes are available.

#### Option A — Demonstration with synthetic data

To explore the system without real company data:

Skip section `0B`.

In section `1 | Configure this run`, set:

~~~python
DATA_DIR = 'data/example_synthetic'
~~~

Inside `AnalysisConfig`, set:

~~~python
property_name='SYNTHETIC 6BR Pool Home',
~~~

Keep the example analysis dates and run the remaining notebook sections.

The example dataset is already included in the repository.

No CSV upload is required for this demonstration.

#### Option B — Analyze a real property

In section `0B | Upload the four PriceLabs CSVs`, set:

~~~python
UPLOAD_CSVS = True
~~~

Run the section and upload the four PriceLabs exports when prompted.

The notebook places the uploaded files in the Colab runtime.

In section `1 | Configure this run`, set:

~~~python
DATA_DIR = 'data/input'
~~~

Then configure the exact property name and the appropriate analysis windows.

For a new property, use its own data and dates. Do not reuse the synthetic listing name or assume that the previous property's dates are suitable.

### Step 4 — Execute the analysis

Run the notebook sections in order:

| Section | Purpose |
|---|---|
| 0 | GitHub connection and Python setup |
| 0B | Optional CSV upload |
| 1 | Property and date configuration |
| 2 | Load, validate, compute and audit |
| 3 | Executive metrics |
| 4 | ADR, occupancy and RevPAR benchmarks |
| 5 | Daily competitor pricing analysis |
| 6 | Statistical charts |
| 7 | Export evidence |

### Step 5 — Review the results

Examine the executive metrics, market comparisons, daily competitor positioning and audit findings.

Review every warning before using the results to support a pricing decision.

### Step 6 — Export and preserve the evidence

Run section `7 | Export evidence`.

The framework creates a dated output folder containing:

- Analytical tables.
- Competitor pricing comparisons.
- Statistical charts.
- Booking performance metrics.
- Revenue reconciliation.
- Audit findings.
- Execution metadata and file hashes.

Download the evidence before closing the Colab session. Colab runtime storage is temporary.

---

## Required Data

A real analysis requires four PriceLabs CSV exports.

| File | Source | Purpose |
|---|---|---|
| `bookings.csv` | PriceLabs Bookings Report | Booking pace, revenue, ADR, lead time and length of stay |
| `competitor_calendar.csv` | PriceLabs Competitor Calendar | Competitor prices, availability and minimum-stay requirements |
| `report_builder_historical.csv` | PriceLabs Report Builder | Historical ADR, occupancy, revenue and market comparison |
| `report_builder_forward.csv` | PriceLabs Report Builder | Forward ADR, occupancy, revenue and market comparison |

The booking report should include all relevant reservations needed for stay-date reconciliation, not only reservations created inside the selected booking window.

The Report Builder exports must match the historical and forward stay-date periods configured in the notebook.

Consult [DATA_CHECKLIST.md](DATA_CHECKLIST.md) for detailed export requirements.

---

## Analytical Capabilities

### 1. Competitive Pricing Analysis

The framework compares advertised nightly prices against a manually selected group of comparable properties.

Metrics include:

- Mean competitor price.
- Median competitor price (P50).
- P25 and P75 price levels.
- Standard deviation.
- Daily percentage price gaps.
- Weekday and weekend comparisons.
- Minimum available competitor counts.
- Minimum-stay sensitivity.
- Availability-based sensitivity analysis.
- Weekly block-bootstrap confidence intervals.

Dates without sufficient comparable pricing data are flagged or excluded from the primary comparison.

### 2. Revenue Performance

The framework analyzes:

- Average Daily Rate (ADR).
- Occupancy.
- Revenue per Available Room (RevPAR), or the corresponding property-level benchmark.
- Rental revenue.
- Booking pace.
- Booking pickup where available.
- Booking lead time.
- Length of stay.
- Historical and forward market benchmarks.

Metrics are calculated within clearly defined booking-creation or stay-date periods.

### 3. Data Validation and Reconciliation

The system includes:

- Input-schema validation.
- Strict monetary and date parsing.
- Property identification checks.
- Booking-status validation.
- Booking-to-Report Builder reconciliation.
- Possible duplicate competitor detection.
- Minimum-stay comparisons.
- Documented data-quality warnings.

Invalid or inconsistent inputs may stop the analysis rather than silently produce misleading figures.

### 4. Auditable Evidence

Each execution generates its own output directory.

The system records:

- Analysis configuration.
- Data-quality results.
- Source-file SHA-256 hashes.
- Output-file hashes.
- Code revision information where available.
- Software environment metadata.

This provides traceability for future review.

---

## Understanding Audit Status

Every execution receives a decision-review status.

| Status | Meaning | Required action |
|---|---|---|
| `VALIDATED` | All required checks and attestations passed | Review findings and make a separate pricing decision |
| `REVIEW_REQUIRED` | One or more warnings remain | Investigate and document each material warning |
| `FAILED` | One or more critical checks failed | Do not use the results for pricing decisions |

**Operational rule:**

A `FAILED` analysis must not support pricing decisions.

An analysis marked `REVIEW_REQUIRED` may inform a supervised decision only after each relevant warning has been reviewed, its impact understood, and any remaining limitations explicitly documented.

Human acceptance of a warning does not automatically change the system status to `VALIDATED`.

Warnings related to competitor comparability do not necessarily indicate incorrect calculations. They may identify limitations that require Revenue Management judgment.

---

## Interpreting Results Responsibly

The framework is designed for decision support, not automatic price optimization.

Important limitations include:

- Lower prices than competitors do not prove economic underpricing.
- Higher occupancy does not prove that lower prices caused additional bookings.
- Competitor advertised rates are not realized competitor ADR.
- Unavailable competitor dates do not necessarily represent confirmed bookings.
- Differences in property size, quality, reviews, amenities and stay requirements can affect comparability.
- Historical and forward performance should not be compared without considering their different date windows and demand conditions.

The system does not estimate price elasticity or guarantee revenue-maximizing rates.

Pricing recommendations should distinguish:

**Observation:** What the data directly show.

**Hypothesis:** What may explain the observed performance.

**Proposed action:** A pricing adjustment or test supported by the available evidence.

**Monitoring:** How the impact of the decision will be evaluated.

---

## Recommended Revenue Management Workflow

1. Identify a specific property-performance question.
2. Select appropriate comparable properties.
3. Export the four PriceLabs reports.
4. Configure the property and analysis periods.
5. Execute the notebook.
6. Review metrics, comparisons and audit warnings.
7. Investigate any material inconsistencies.
8. Document findings and recommendations.
9. Define any proposed pricing change as a controlled test.
10. Monitor booking pickup, ADR, occupancy and RevPAR after implementation.

**The objective is better decisions, not more analysis for its own sake.**

A pricing adjustment should only be implemented after the appropriate business approval.

---

## Project Structure

~~~text
rental-revenue-decision-support/
├── README.md
├── Revenue_Management_EDA.ipynb
├── DATA_CHECKLIST.md
├── requirements.txt
├── requirements-dev.txt
├── pyproject.toml
├── CHANGELOG.md
├── rm_analytics/
│   ├── config.py
│   ├── parsing.py
│   ├── loaders.py
│   ├── metrics.py
│   ├── duplicates.py
│   ├── audit.py
│   ├── pipeline.py
│   ├── export.py
│   ├── charts.py
│   └── synthetic.py
├── tests/
├── docs/
└── data/
    └── example_synthetic/
~~~

The analytical calculations reside in the `rm_analytics` package.

The Jupyter notebook provides the configuration, execution, visualization and export interface.

This separation supports maintainability and reuse without requiring a new notebook for each property.

---

## Local Development and Testing

The recommended interface is Google Colab.

For developers who prefer running the project locally:

~~~bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
python -m pytest
jupyter notebook Revenue_Management_EDA.ipynb
~~~

The repository includes a synthetic test dataset and an automated test suite.

Test coverage does not eliminate the need to review real PriceLabs exports, business assumptions and competitor selection.

---

## Data Confidentiality

The public repository is intended for source code, technical documentation, automated tests and synthetic examples.

Operational booking exports and property-level financial evidence should be stored according to the company's approved data-handling procedures.

The Colab runtime does not automatically publish uploaded CSVs or generated outputs to GitHub.

Do not commit confidential reports, real reservation data or sensitive notebook outputs without appropriate authorization.

The `.gitignore` file helps prevent accidental inclusion of operational files, but it does not remove information previously committed to Git history.

---

## Documentation

- [Data Checklist](DATA_CHECKLIST.md) — Required exports and preparation.
- [Methodology](docs/METHODOLOGY.md) — Formulas, statistical methods and limitations.
- [Colab Integration Guide](docs/COLAB_GITHUB_GUIDE.md) — Google Colab setup and troubleshooting.
- [Validation Notes](docs/V2_1_VALIDATION.md) — Validation history and known limitations.
- [Test Results](docs/TEST_RESULTS.md) — Automated test information.
- [Changelog](CHANGELOG.md) — Project development history.

---

## Project Status

**Version:** 2.1.0

**Status:** Operational pilot — supervised analytical use.

The core workflow has been exercised using synthetic data, including GitHub-to-Colab synchronization, calculations, reconciliation, charts and evidence export.

Real-property findings require current, valid input files and review of the audit results.

The project is ready for practical Revenue Management investigations, subject to data-quality checks and human judgment.

## Final Principle

**Analyze with evidence. Recommend with discipline. Measure the outcome.**

Rental Revenue Decision Support is designed to make property-level pricing investigations consistent, reproducible and actionable.
