> **v2.1 follow-up:** The original v2 fixes remain in place. The improvements to review gating, minimum-stay sensitivity and duplicate detection are documented in [V2_1_VALIDATION.md](V2_1_VALIDATION.md). The v2 statement that real-data validation was pending was accurate at delivery time; the independent v2.1 review has since executed the study using available operational exports without bundling those exports into the public project.

# Fix Report (v1 → v2.0.0)

This report maps every finding of the independent technical audit of the previous version (commit `3dde02b`) to what changed. Each fix is covered by an automated test. The test names listed can be run with `python -m pytest -k <name>`.

**Status legend**
- **Fixed:** resolved in code and covered by tests.
- **Mitigated:** reduced and made visible; not fully resolvable in code.
- **Open:** requires action outside this repository or real data.

## A. Code and data-handling findings

| # | Severity | Finding (v1) | Status | What changed | Tests |
|---|---|---|---|---|---|
| 1 | Critical | Public repository; subject property address hard-coded as default; a deleted HTML findings report remains in git history; company e-mail in commit metadata | **Mitigated / Open** | The address is removed from all files (default is now `YOUR LISTING NAME`). `.gitignore` blocks `data/input/*` and `output/`. A hygiene test fails on known confidential identifiers or saved notebook outputs. **History rewrite and visibility change require the owner's action**; see MIGRATION_GUIDE.md. | `test_no_confidential_identifiers_in_tracked_files`, `test_notebook_has_no_saved_outputs`, `test_gitignore_protects_real_data` |
| 2 | High | `to_numeric(errors='coerce')` turned `"$1,234.00"` into NaN and `.sum()` skipped it: revenue and ADR understated silently | **Fixed** | Strict `parse_currency`: accepts `$`, thousands separators, `USD`, `(negative)`; rejects anything else, including European formats, with an error listing examples | `test_currency_formats_are_parsed_not_dropped`, `test_currency_rejects_*`, `test_bookings_garbage_revenue_rejected` |
| 3 | High | `Booked Date.between(start, end)` excluded bookings made after 00:00 on the last day | **Fixed** | All dates are normalized to calendar days before filtering | `test_dates_with_time_are_normalized_and_inclusive_filter_works`, `test_last_day_booking_with_time_is_counted` |
| 4 | High | `pd.to_datetime(errors='coerce')` without a format turned mixed formats into NaT; rows vanished | **Fixed** | `parse_dates` detects ISO or numeric orders; any unparseable or missing required date raises | `test_mixed_date_and_datetime_strings_do_not_become_nat`, `test_missing_and_garbage_dates_raise`, `test_bookings_missing_checkout_rejected` |
| 5 | High | Calendar format hard-coded `%d/%m/%Y`: US dates were swapped (Nov 5 → May 11) or dropped | **Fixed** | Day-first vs month-first auto-detected; ambiguity resolved by the daily-sequence rule or reported; gaps and duplicate dates raise; an explicit format can be configured | `test_calendar_us_date_format_is_detected`, `test_ambiguous_dates_raise_unless_consecutive_sequence_resolves_them`, `test_calendar_missing_date_row_is_rejected`, `test_calendar_duplicate_date_is_rejected` |
| 6 | High | Historical and forward stay windows in the config were never used; a Report Builder export for the wrong period passed unnoticed | **Fixed (detective control)** | Reservations are allocated to stay nights and reconciled per period with Report Builder nights and revenue (WARN on mismatch). Report Builder internal ADR consistency is checked. The analyst attests that the ranges were verified. | `test_wrong_report_builder_period_is_caught_by_reconciliation`, `test_report_builder_internal_adr_inconsistency_warns`, `test_stay_allocation_splits_reservation_across_window_boundary` |
| 7 | Medium | Bookings filtered with `str.contains` without a uniqueness check (parent/child listings mixed) | **Fixed** | One `resolve_listing` rule for all files: an exact match wins; a partial match must be unique; otherwise raise. Name mismatches across files WARN. | `test_exact_match_preferred_over_partial`, `test_bookings_ambiguous_listing_rejected` |
| 8 | Medium | Missing check-out produced NaN nights while revenue still counted, inflating ADR | **Fixed** | Missing dates raise; check-out ≤ check-in raises | `test_bookings_missing_checkout_rejected`, `test_bookings_checkout_before_checkin_rejected` |
| 9 | Medium | Status filter `== 'booked'` could drop every row or, without the column, include cancellations | **Fixed** | Configurable valid/excluded status lists; unknown statuses raise; a missing column WARNs; excluded reservations are counted | `test_bookings_unknown_status_rejected`, `test_bookings_custom_status_whitelist`, `test_bookings_missing_status_column_is_reported` |
| 10 | Medium | Report Builder `%`/`$` values became NaN in the exported comparison table | **Fixed** | Strict parsers for required and optional fields. Missing optional columns are listed in the audit. Occupancy given as a fraction is detected and reported. | `test_report_builder_parses_formatted_values`, `test_report_builder_missing_optional_is_reported_not_silent`, `test_occupancy_*` |
| 11 | Medium | `min_active_comps = 1`: P25 = P50 = P75 and dates still counted in bands | **Fixed** | Default 5; WARN when below 3; FAIL when the comp set is smaller than the minimum; eligibility reasons per date | `test_min_active_comps_and_our_availability_gate_eligibility`, `test_single_comp_std_is_nan`, `test_too_few_comps_fail` |
| 12 | Medium | Tautological audit checks (duplicate keys already blocked, filter re-tested) and three permanent hard-coded WARNs | **Fixed** | Tautologies replaced by real controls: reconciliation, overlapping reservations, LOS and lead-time reconciliation, duplicate reservations, sensitivity, coverage, input-unchanged hashes. Permanent WARNs replaced by explicit attestations. | `test_attestations_change_governance_status`, `test_overlapping_reservations_fail`, `test_input_modified_during_run_is_detected` |
| 13 | Medium | Only exact `date+listing` duplicates detected; the same home on two channels counted twice | **Fixed** | Near-identical price/availability detection; a comp matching the subject home is FAIL; `duplicate_policy='drop'` available | `test_duplicate_detection_and_drop_policy`, `test_target_duplicated_in_comp_set_is_flagged`, `test_subject_home_inside_comp_set_fails` |
| 14 | Medium | `minimum_stay` loaded but unused; nightly rates not like-for-like | **Mitigated** | Comp median minimum stay per date; WARN when ours differs on > 25% of eligible dates. Cleaning fees are not in the exports (see Open items). | covered in the end-to-end run (`Minimum stay comparable` check) |
| 15 | Low | `data/input/` missing from the repository; `projects[0]` IndexError in the Colab cell | **Fixed** | `data/input/.gitkeep`; robust project discovery and path-safe ZIP extraction | `test_notebook_runs_end_to_end` |
| 16 | Low | No version pinning; `output/` overwritten on every run | **Fixed** | Bounded `requirements.txt` tested on two pandas majors; `requirements-dev.txt`; one immutable folder per run (collision-safe); the manifest records versions | `test_export_writes_manifest_with_hashes_and_no_guest_columns` |
| 17 | Low | Monolithic notebook without tests | **Fixed** | `rm_analytics` package with pure functions; the notebook is a thin front end; 82 automated tests | whole suite |

## B. Statistical findings

| Finding | Status | What changed |
|---|---|---|
| Availability filter biases the gap (sold comps excluded) | **Mitigated** | Sensitivity gap against all priced comps, with a WARN when ≥ 5 pp; available-share per date exported |
| Dates treated as independent ("47 of 51") | **Fixed** | 95% CI for the median gap via a weekly block bootstrap (deterministic seed) |
| Arithmetic mean of % gaps is asymmetric | **Fixed** | Geometric mean gap (log ratios) added; the median remains primary |
| RevPAR never compared with market | **Fixed** | RevPAR proxy and gap for both periods in the summary and in `market_comparison.csv` |
| Booking-window ADR vs stay-window ADR could be confused | **Mitigated** | Separate sections, explicit labels and definitions in the manifest and methodology |
| Percentiles: verify formula | **Verified** | Matches Excel `PERCENTILE.INC` (`test_percentiles_match_excel_percentile_inc`) |
| Equal weighting | **Documented** | Kept as the default for homogeneous comp sets; limits documented |
| No control for reviews, listing age, capacity, cleaning fees | **Open** | Not in the four exports; documented as the main alternative explanation |

## C. Additional defects found while testing v2

| Defect | Fix |
|---|---|
| Two exports within the same second collided (`FileExistsError`) | Collision-safe run folders (`_2`, `_3`, ...) |
| `DataFrame.style` required `jinja2`, which is not installed in every environment | Replaced by plain tables |
| Duplicate-home heuristic gives false positives if availability agreement is ignored, because comps priced by identical rules correlate | Kept the availability-agreement condition (default 0.90) and documented that flagged pairs need review |

## D. Open items (not resolvable in code without further input)

1. **Validation with real data is pending.** No real exports were available. All tests use synthetic data shaped to the documented contract. The first real run must be compared manually with the PriceLabs UI. Expected friction points:
   - exact Bookings status labels;
   - date formats;
   - whether the Bookings export includes all reservations.
2. **The numbers of the original case study have not been re-computed** from source files.
3. **Repository governance:** private visibility, git-history rewrite and a review of the commit author e-mail need the owner's action (see MIGRATION_GUIDE.md).
4. **Real format of the PriceLabs Competitor Calendar header.** The loader follows the 3-row layout documented in v1. If PriceLabs changes it, the run stops with a clear error rather than mis-parsing.
5. **Comparability:** cleaning fees, reviews, listing age and capacity are not available in these exports.
6. **Portfolio scale:** the tool analyzes one property per run. Scaling to 100+ properties needs portfolio-wide exports or the PriceLabs API, scheduled runs and a database. This is out of scope for this release.
