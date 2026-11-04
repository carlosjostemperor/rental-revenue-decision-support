# Changelog

## 2.1.0

- Introduced an explicit decision gate: `VALIDATED` (zero WARN/FAIL), `REVIEW_REQUIRED` (any WARN) or `FAILED` (any FAIL); export folder names, human-readable review summary and manifest agree.
- Added `REVIEW_SUMMARY.md` with an actionable queue and `outstanding_review_items` in the manifest. The review summary is SHA-256 hashed with other outputs.
- Added `minimum_stay_sensitivity.csv`: rate-gap statistics and sample sizes for minimum-stay-matched, different and unknown dates. Zero/unknown sample sizes are shown transparently.
- Expanded duplicate screening: a secondary advisory signal spots nearly identical blocked-date patterns even when rate levels differ. Advisory signals can never auto-remove competitors.
- Improved notebook prompts and 6 new automated regression tests. Re-tested with the previous synthetic suite and a separate real-export validation (real exports excluded from the distributed ZIP).
- Documented that a public code repository must contain only synthetic/approved material; no repository changes were made.

## 2.0.0

- Calculations moved from the notebook into the tested `rm_analytics` package; the notebook is a thin Colab/Jupyter front end.
- Strict parsing of money, percentages and dates. Unparseable values stop the run instead of becoming NaN.
- Date handling: ISO and numeric day/month formats detected; time of day ignored in inclusive filters; calendar gaps and duplicates rejected.
- Booking status whitelist with explicit exclusions; unknown statuses stop the run.
- One listing-resolution rule across all files (exact match first, unique partial match otherwise).
- Duplicate-home detection in the comp set; the subject home inside the comp set is a FAIL.
- New metrics: RevPAR proxy vs market, weekly block-bootstrap CI for the median gap, geometric mean gap, availability-filter sensitivity, minimum-stay comparability, nights per week, lead-time quartiles.
- Reconciliation of bookings with Report Builder by stay date (detects wrong periods or filtered exports).
- Audit rewritten: no tautological checks; human verifications are recorded attestations.
- Evidence export: one immutable folder per run; manifest with input and output SHA-256, config, code and environment versions; failed runs labelled `_FAILED`.
- Synthetic data generator; 82 automated tests including error cases and full notebook execution.
- The confidential default property name was removed; `.gitignore` protects inputs and outputs.

## 1.0.0

- Initial notebook.
