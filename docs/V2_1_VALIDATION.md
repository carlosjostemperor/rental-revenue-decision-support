# Release 2.1.0 — Independent technical validation

## Scope

This release is a targeted improvement to v2.0.0. It does not connect to PriceLabs, modify listing prices or replace human revenue-management judgment.

## Changes verified

1. **Three-way decision gate:** `FAILED` for any FAIL; `REVIEW_REQUIRED` for any WARN and no FAIL; `VALIDATED` only when all checks PASS. Warnings no longer produce a status that could be misunderstood as approval. Export directories, the manifest and `REVIEW_SUMMARY.md` agree.
2. **Human-readable review queue:** each non-PASS check appears in `REVIEW_SUMMARY.md` and the manifest. This report is included in output hashes.
3. **Minimum-stay comparability:** `minimum_stay_sensitivity.csv` partitions eligible dates into matched / different / unknown stay restrictions. The report shows each group's sample size and pricing gap, rather than presenting the overall gap as if stay rules were uniform.
4. **Possible duplicate homes:** a second, cautious warning detects highly similar patterns of unavailable dates even if prices differ. This is **not a conclusive match**, and weak signals are never auto-dropped.
5. **Documentation:** updated public-repository guidance, run status definitions and notebook instructions.

## Automated validation

`python -m pytest -q` runs the original 82 tests plus 6 new regression tests. The suite includes a real Jupyter notebook execution against synthetic exports. Check the delivery validation notes for the current test result and runtime environment. Tests must be rerun after code changes.

## Separate original-export verification

A separate, independently executed run using previously supplied PriceLabs exports confirmed that the upgraded workflow could still reproduce the historical booking totals and the core daily benchmark statistics. Those files, property identifiers, and run outputs are deliberately **not included** in the distributed project ZIP.

**Outcome:** `REVIEW_REQUIRED` due to six outstanding checks, none of them FAIL:

- Two different display names for the subject listing across source exports (same underlying listing verified manually in the earlier analysis, but the audit does not assume they are identical).
- Minimum-stay restrictions differ on 15 of 43 eligible comparison dates.
- Four analyst/governance attestations have not been completed.

The original-export re-run is evidence of compatibility with that one export set, **not certification of all PriceLabs CSV variants or independent proof of pricing optimality**. There were no automatic pricing changes.

## Still requires human judgment

- Verify the property identity and stay-date windows using the PriceLabs user interface.
- Confirm comp-set physical identity (including parent/child and multi-channel listings); heuristics cannot prove listings share a home.
- Decide whether results on dates with mismatched minimum stays are comparable enough for a given decision.
- Investigate cleaning fees, reviews, property quality, listing age and booking conversion, which the four exports do not control.
- Approve any proposed pricing experiment separately with clearly defined metrics and stop conditions.

**Release recommendation:** suitable for supervised analytical pilots, not unattended company-wide pricing automation.
