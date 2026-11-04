"""Detection of probable duplicate physical homes in the competitor calendar.

The same home listed on two channels (or as parent/child listings) would be counted twice under
equal weighting. Exact duplicate keys are rejected at load time; this module flags listings whose
price and availability series are near-identical.
"""

from __future__ import annotations

from itertools import combinations

import numpy as np
import pandas as pd

from .config import AnalysisConfig

COLUMNS = [
    "listing_a",
    "listing_b",
    "overlap_days",
    "price_corr",
    "median_abs_diff_pct",
    "availability_agreement",
    "involves_target",
    "match_basis",
    "shared_blocked_days",
    "blocked_day_jaccard",
]


def detect_duplicate_listings(frame: pd.DataFrame, target: str, cfg: AnalysisConfig) -> pd.DataFrame:
    priced = frame[frame.advertised_price > 0]
    prices = priced.pivot(index="date", columns="listing", values="advertised_price")
    avail = frame.pivot(index="date", columns="listing", values="available").astype("float")
    pairs = []
    for a, b in combinations(prices.columns, 2):
        both = prices[[a, b]].dropna()
        n = len(both)
        if n < cfg.duplicate_min_overlap_days:
            continue
        pa, pb = both[a].astype(float), both[b].astype(float)
        if pa.std() == 0 or pb.std() == 0:
            corr = 1.0 if (pa.values == pb.values).all() else 0.0
        else:
            corr = float(np.corrcoef(pa, pb)[0, 1])
        mad = float((pa / pb - 1).abs().median() * 100)
        av = avail[[a, b]].dropna()
        agreement = float((av[a] == av[b]).mean()) if len(av) else np.nan
        strong_price_match = (
            corr >= cfg.duplicate_corr_threshold
            and mad <= cfg.duplicate_max_median_abs_diff_pct
            and (np.isnan(agreement) or agreement >= cfg.duplicate_min_availability_agreement)
        )
        # Advisory, not proof: near-identical blocked-date patterns can suggest the
        # same physical home even when parent/child or OTA markups differ. Requiring
        # actual blocked days avoids false positives from calendars that are all open.
        # Never auto-drop a comp on the basis of this weaker signal.
        if len(av):
            ab, bb = av[a].eq(0), av[b].eq(0)
            shared = int((ab & bb).sum())
            blocked_union = int((ab | bb).sum())
            jaccard = shared / blocked_union if blocked_union else 0.0
        else:
            shared, jaccard = 0, 0.0
        shared_blocked_match = (
            shared >= 5 and jaccard >= 0.95
            and agreement >= max(0.98, cfg.duplicate_min_availability_agreement)
            and not strong_price_match
        )
        if strong_price_match or shared_blocked_match:
            basis = "price_and_availability" if strong_price_match else "shared_unavailability_review"
            pairs.append([a, b, n, round(corr, 4), round(mad, 2), round(agreement, 3),
                          target in (a, b), basis, shared, round(jaccard, 3)])
    return pd.DataFrame(pairs, columns=COLUMNS)


def apply_duplicate_policy(
    frame: pd.DataFrame, comps: list, target: str, duplicates: pd.DataFrame, cfg: AnalysisConfig
) -> tuple[pd.DataFrame, list, list]:
    """Return (frame, comps, dropped). Under 'drop', for each pair the non-target / second listing is removed."""
    if cfg.duplicate_policy != "drop" or duplicates.empty:
        return frame, comps, []
    dropped: list = []
    for _, row in duplicates.iterrows():
        # Never delete a listing based solely on calendar similarity.
        if row.match_basis != "price_and_availability":
            continue
        a, b = row.listing_a, row.listing_b
        if a in dropped or b in dropped:
            continue
        victim = b if a == target else a if b == target else b
        dropped.append(victim)
    frame = frame[~frame.listing.isin(dropped)].reset_index(drop=True)
    comps = [c for c in comps if c not in dropped]
    return frame, comps, dropped
