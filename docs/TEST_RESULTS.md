# Test Results — v2.1.0

**Independent execution:** 2026-11-03

| Item | Result |
|---|---|
| Python | 3.13.5 |
| pandas | 2.2.3 |
| numpy | 2.3.5 |
| matplotlib | 3.10.8 |
| pytest | 9.0.2 |
| Command | `python -m pytest -q --disable-warnings` |
| Outcome | **88 passed, 0 failed** |

The tests include a real Jupyter notebook kernel execution using **synthetic exports**, parsing/validation failures, reconciliation, output SHA-256, duplicate detectors, minimum-stay subgroups, and export review gates. The v2.0.0 suite had 82 tests; v2.1.0 adds six.

## Additional export compatibility check

The updated package was also executed against the four original PriceLabs CSV files previously supplied for one operational case, **outside this distributable**. The headline booking and benchmark metrics were unchanged. The resulting audit status was:

| PASS | WARN | FAIL | Decision status |
|---:|---:|---:|---|
| 25 | 6 | 0 | `REVIEW_REQUIRED` |

The outstanding warnings cover a harmless but unverified listing-display-name variation, the fact that minimum stay differs on 15 of 43 eligible dates, and four uncompleted human attestations. The detailed financial outputs and original CSVs are **not committed or bundled**.

**Scope caveat:** this confirms execution on one real export set and the synthetic test suite. It does not guarantee compatibility with every PriceLabs export variation or establish optimal pricing.
