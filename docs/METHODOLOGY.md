# Methodology

## 1. Data definitions

| Term | Source | Meaning |
|---|---|---|
| Advertised rate | Competitor Calendar `prices` | Nightly rate shown for a date. It is not realized ADR, and it excludes cleaning fees and length-of-stay discounts. |
| Available | Competitor Calendar `available` | The date can be booked. Unavailable can mean booked, blocked or owner use. It is **not** a confirmed sale. |
| Booking window | Bookings `Booked Date` | Reservations **created** between `booking_start` and `booking_end` (inclusive, time ignored). |
| Stay window | Report Builder Stay Date Range | Nights **stayed** in the range. This is a different population from the booking window. |
| Market ADR / occupancy | Report Builder | The PriceLabs market benchmark. It is independent of the manual comp set. |

The booking-window ADR and the stay-window ADR describe different reservations and must not be compared with each other.

## 2. Daily pricing position (forward window)

For each date *d* in the forward window:

- **Comp sample:** comps that are available on *d* and have a price > 0. Each listing has equal weight.
- **Statistics:**
  - mean;
  - median;
  - P25 and P75 by linear interpolation (identical to Excel `PERCENTILE.INC`);
  - sample standard deviation (`ddof=1`, undefined with fewer than 2 comps);
  - min and max.
- **Gap:** `gap_vs_median_pct = (our_price / comp_median - 1) × 100`. The log ratio is also stored.
- **Eligibility:** a date is compared only if our listing is available, our price is > 0 and at least `min_active_comps` comps are available (default 5). Every excluded date keeps an `exclusion_reason`.
- **Bands:**
  - `Below P25` if our price < P25;
  - `P25 to below P50` if < median;
  - `P50 to P75` if ≤ P75;
  - otherwise `Above P75`.

**Summary statistics over eligible dates**

- Median daily gap (primary metric). The median of daily ratios is not the ratio of medians.
- **95% CI of the median gap** from a weekly block bootstrap (2,000 resamples, fixed seed). Dates within a week share the same pricing logic and are not independent, so a date-level bootstrap or a sign test would overstate certainty. The CI is not computed with fewer than 4 weeks.
- Mean daily gap and **geometric mean gap**, `exp(mean(log ratio)) − 1`. The geometric mean is symmetric for increases and decreases.
- Share of dates below the median and below P25.

### Selection bias of the availability filter

Comps that are unavailable are often already sold, and the best-value homes sell first. The remaining available comps can therefore be more expensive than the full comp set, which makes our gap look more negative. The tool reports the same gap against **all priced comps**, available or not, and WARNs when the two differ by 5 percentage points or more. These are sensitivity scenarios, **not guaranteed upper and lower bounds** on a true or optimal price gap. Unavailable comps may be booked, blocked or owner-held.

### Comparability limits (not corrected)

The advertised nightly rate ignores:

- cleaning fees;
- length-of-stay discounts;
- review count and rating;
- listing age;
- capacity differences.

Minimum stays are compared: dates are partitioned into **matched**, **different** and **unknown** groups against the daily comp median. Their median pricing gaps and sample sizes are exported to `minimum_stay_sensitivity.csv`. A WARN is raised when fewer than 75% of eligible dates have a matched minimum stay. These are descriptive sensitivity summaries, not causal adjustments; cleaning fees and LOS discounts remain uncontrolled. A new listing with few reviews is usually expected to price below established comps. This is the main alternative explanation for any negative gap.

### Weighting

Equal weight per listing is a reasonable default when comps are homogeneous (same bedrooms, pool, area). Prefer similarity weights or a hedonic adjustment when comps differ materially in capacity, quality, review volume or distance. This is not implemented; the comp set should be kept homogeneous instead.

### Duplicate homes

The same home on two channels, or as parent and child listings, counts twice under equal weight. Exact duplicate rows are rejected at load time.

Duplicate screening has **two independent flag types**:

- `price_and_availability` (stronger): price correlation ≥ 0.98, median absolute price difference ≤ 3%, availability agreement ≥ 90%, and ≥ 14 overlapping priced dates. Under `duplicate_policy='drop'`, only this stronger match may be removed automatically. A strong match to the **subject** home is a FAIL under `warn`.
- `shared_unavailability_review` (advisory): at least 5 shared unavailable dates, blocked-day Jaccard similarity ≥ 0.95, availability agreement ≥ 98%, and at least 14 overlapping priced dates, even when prices differ. These pairs are **never auto-dropped**. This catches some multiple-channel or parent/child listings that use different rate plans.

Both are heuristics, **not proof that two listings are the same physical home**. Identical booking patterns can arise from shared calendar restrictions. Review listing URLs, property characteristics and host management before excluding a comparable. Different physical homes may also escape both checks.

## 3. Bookings (booking window)

- Valid reservations: status in `valid_booking_statuses`. Statuses in `excluded_booking_statuses` are counted separately. Any other status stops the run.
- Nights = check-out − check-in. They are reconciled with `Length of Stay (Days)`; any mismatch is a FAIL.
- Lead time = check-in − booked date in days. It is reconciled with `Booking Window (Days)`; a difference above 1 day is a WARN.

| Metric | Formula |
|---|---|
| Weighted booking ADR | Σ rental revenue / Σ nights |
| Bookings per week | reservations × 7 / inclusive days in the window |
| Nights per week | nights × 7 / inclusive days in the window |
| Lead time | median, mean, P25, P75 per reservation |
| Length of stay | mean and median |

Possible duplicate reservations are counted by `Reservation ID` when present, otherwise by booked date, check-in, check-out and revenue.

There is no market pace benchmark in the inputs. "High pace" is a judgment unless compared with the property's own history or with market pickup.

## 4. Market comparison (Report Builder)

For each period (historical, forward):

| Metric | Formula |
|---|---|
| ADR gap | `Rental ADR / Market ADR − 1` |
| Occupancy gap | `Adjusted Occupancy % − Market Occupancy %` (percentage points) |
| **RevPAR proxy** | `ADR × occupancy / 100` for us and for the market; gap = ratio − 1 |

RevPAR answers whether a lower rate was compensated by higher occupancy. Adjusted occupancy and market occupancy may use different bases (blocked nights, bedroom filters); verify them in PriceLabs.

Forward figures are *on the books* at the run date. A property that sells earlier than the market will show higher forward occupancy even if final occupancy is the same.

## 5. Reconciliation (the period check)

PriceLabs CSV exports do not state the Stay Date Range they were run for. The tool therefore allocates every valid reservation to its stay nights, spreading revenue evenly per night. It then compares booked nights and revenue per period with the Report Builder totals, within `reconciliation_tolerance_pct` (default 2%).

A mismatch WARNs and forces `REVIEW_REQUIRED` rather than a validated result. Possible causes:
- the wrong Stay Date Range was used in Report Builder;
- the Bookings export was filtered;
- status differences;
- revenue allocation rules differ.

Report Builder internal consistency (`Rental Revenue / Booked Nights ≈ Rental ADR`) is also checked. Overlapping valid reservations on the same night are a FAIL.

## 6. Audit status

Audit **checks** have `PASS`, `WARN` or `FAIL`. The **overall run** has a separate, stricter decision status:

| Run status | Condition | Decision use |
|---|---|---|
| `FAILED` | At least one FAIL | Do not use for pricing decisions; evidence exported to `_FAILED` directory. |
| `REVIEW_REQUIRED` | No FAIL but at least one WARN | Do not treat as validated. See `REVIEW_SUMMARY.md` and resolve the issue or document limitations. |
| `VALIDATED` | All checks PASS | Analytical checks passed; any pricing change still needs independent human approval. |

The generated manifest includes a review-item list and always specifies `approved_for_automated_price_changes: false`. Human verifications are configuration attestations recorded in the manifest and must not be set without performing the check. Synthetic example data are never intended for actual pricing decisions.

## 7. What is needed for pricing decisions beyond this tool

To estimate price elasticity and revenue-maximizing rates, the following would be needed:

- daily price snapshots for the subject and the comps over time (to observe availability transitions);
- funnel data (search impressions, views, conversion);
- deliberate price tests across comparable date blocks;
- a panel of several properties.

A model of booking probability by date as a function of relative price, lead time, seasonality and market demand can then be fitted. Until then, recommendations on the *magnitude* of a rate change are judgment, and should be framed as monitored tests.
