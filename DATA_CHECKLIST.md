# Data Input Checklist (every run)

**Before running**

- [ ] The four exports use the same property filter, and `property_name` matches the listing name exactly.
- [ ] The Bookings Report is exported **without** a booked-date filter (all reservations of the property).
- [ ] `booking_start` / `booking_end` represent **Booked Date**, not stay date.
- [ ] The historical Report Builder **Stay Date Range** matches `historical_stay_start/end`. A screenshot is saved.
- [ ] The forward Report Builder **Stay Date Range** matches `forward_start/end`. A screenshot is saved.
- [ ] The Competitor Calendar covers every date of the forward window.
- [ ] The comp set is current, geographically comparable and similar in bedrooms, capacity and amenities.
- [ ] Files are stored only in approved restricted storage (never in the repository).

**After running**

- [ ] No FAIL checks. The notebook stops on FAIL, and the export folder ends in `_FAILED`.
- [ ] Every WARN is resolved or explained in the reviewer notes, especially:
  - [ ] Reconciliation (bookings vs Report Builder nights and revenue)
  - [ ] Probable duplicate homes / subject home in the comp set
  - [ ] Availability-filter sensitivity
  - [ ] Minimum-stay comparability
- [ ] Five dates verified against the PriceLabs UI, including a weekend and a low-comp date.
- [ ] Attestations (`attest_*`), `analyst` and `reviewer` are set truthfully, and the notebook is re-run.
- [ ] The `output/<run_id>/` folder is downloaded and archived with the source files.
- [ ] Research conclusions are kept separate from pricing approval. Any rate change is documented as a pricing test.
