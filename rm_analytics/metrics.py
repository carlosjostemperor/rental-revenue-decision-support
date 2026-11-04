"""Statistical and financial metrics. Pure functions over validated data."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import AnalysisConfig
from .errors import DataValidationError
from .loaders import BookingsData, CalendarData, ReportBuilderRow
from .parsing import safe_log_ratio

BANDS = ["Below P25", "P25 to below P50", "P50 to P75", "Above P75"]


# --------------------------------------------------------------------------------------------
# Daily pricing position versus the manual comp set (forward window)
# --------------------------------------------------------------------------------------------
def compute_daily_positions(cal: CalendarData, frame: pd.DataFrame, comps: list, cfg: AnalysisConfig) -> pd.DataFrame:
    """One row per forward-window date with comp statistics and our position.

    Competitor statistics use only comps that are available with a price > 0 on that date
    (equal weight per listing). Sensitivity columns using every priced comp (available or not)
    quantify the selection bias of that filter.
    """
    lo, hi = cfg.ts("forward_start"), cfg.ts("forward_end")
    days = pd.date_range(lo, hi, freq="D")
    covered = pd.DatetimeIndex(frame.date.unique())
    missing = days.difference(covered)
    if len(missing):
        raise DataValidationError(
            f"Competitor calendar does not cover the forward window: {len(missing)} missing date(s), "
            f"first {missing[0].date()}, calendar spans {covered.min().date()} to {covered.max().date()}"
        )
    w = frame[frame.date.between(lo, hi)]
    ours = w[w.listing == cal.target].set_index("date").reindex(days)
    comp = w[w.listing.isin(comps)].copy()
    avail = comp.available.eq(1).fillna(False).astype(bool)
    priced = comp.advertised_price > 0
    comp["valid_price"] = comp.advertised_price.where(avail & priced)
    comp["priced_any"] = comp.advertised_price.where(priced)
    comp["valid_min_stay"] = comp.minimum_stay.where(avail & priced)

    def piv(col):
        return comp.pivot(index="date", columns="listing", values=col).reindex(days)

    prices, all_priced, min_stays = piv("valid_price"), piv("priced_any"), piv("valid_min_stay")

    pos = pd.DataFrame(index=days)
    pos.index.name = "date"
    pos["our_price"] = ours.advertised_price.astype(float)
    pos["our_available"] = ours.available.eq(1).fillna(False).astype(bool)
    pos["our_min_stay"] = ours.minimum_stay.astype(float)
    pos["n_comps"] = prices.notna().sum(axis=1)
    pos["n_comps_priced"] = all_priced.notna().sum(axis=1)
    pos["comp_available_share"] = pos.n_comps / len(comps)
    pos["comp_mean"] = prices.mean(axis=1)
    pos["comp_p25"] = prices.quantile(0.25, axis=1, interpolation="linear")
    pos["comp_median"] = prices.median(axis=1)
    pos["comp_p75"] = prices.quantile(0.75, axis=1, interpolation="linear")
    pos["comp_std"] = prices.std(axis=1, ddof=1)  # NaN when fewer than 2 comps
    pos["comp_min"] = prices.min(axis=1)
    pos["comp_max"] = prices.max(axis=1)
    pos["comp_median_all_priced"] = all_priced.median(axis=1)
    pos["comp_median_min_stay"] = min_stays.median(axis=1)
    pos["gap_vs_median_pct"] = (pos.our_price / pos.comp_median - 1) * 100
    pos["log_gap_vs_median"] = safe_log_ratio(pos.our_price, pos.comp_median)
    pos["gap_vs_all_priced_median_pct"] = (pos.our_price / pos.comp_median_all_priced - 1) * 100

    our_priced = pos.our_price.gt(0).fillna(False)
    enough = pos.n_comps >= cfg.min_active_comps
    pos["eligible"] = pos.our_available & our_priced & enough
    pos["exclusion_reason"] = np.select(
        [~pos.our_available, ~our_priced, ~enough],
        ["subject listing unavailable", "subject price missing or zero", f"fewer than {cfg.min_active_comps} available comps"],
        default="",
    )
    band = np.select(
        [pos.our_price < pos.comp_p25, pos.our_price < pos.comp_median, pos.our_price <= pos.comp_p75],
        BANDS[:3],
        default=BANDS[3],
    )
    pos["price_band"] = np.where(pos.eligible, band, "")
    pos["day_group"] = np.where(pos.index.dayofweek.isin([4, 5]), "Fri-Sat", "Sun-Thu")
    pos["day_name"] = pos.index.day_name()
    pos["min_stay_unknown"] = pos.eligible & (
        pos.our_min_stay.isna() | pos.comp_median_min_stay.isna()
    )
    pos["min_stay_matched"] = (
        pos.eligible & ~pos.min_stay_unknown &
        pos.our_min_stay.eq(pos.comp_median_min_stay)
    )
    pos["min_stay_differs"] = pos.eligible & ~pos.min_stay_unknown & ~pos.min_stay_matched
    return pos


def block_bootstrap_median_ci(values: pd.Series, iterations: int, seed: int, level: float = 0.95) -> tuple:
    """CI for the median using a weekly block bootstrap (dates within a week are not independent)."""
    v = values.dropna()
    if iterations == 0 or v.empty:
        return (np.nan, np.nan, 0)
    weeks = v.groupby(v.index.to_period("W-SUN"))
    blocks = [g.values for _, g in weeks]
    if len(blocks) < 4:
        return (np.nan, np.nan, len(blocks))
    rng = np.random.default_rng(seed)
    meds = np.empty(iterations)
    for i in range(iterations):
        idx = rng.integers(0, len(blocks), len(blocks))
        meds[i] = np.median(np.concatenate([blocks[j] for j in idx]))
    alpha = (1 - level) / 2
    return (float(np.quantile(meds, alpha)), float(np.quantile(meds, 1 - alpha)), len(blocks))


def summarize_positions(pos: pd.DataFrame, n_comps_total: int, cfg: AnalysisConfig) -> dict:
    v = pos[pos.eligible]
    available_days = int(pos.our_available.sum())
    counts = v.price_band.value_counts().reindex(BANDS, fill_value=0)
    lo, hi, n_weeks = block_bootstrap_median_ci(v.gap_vs_median_pct, cfg.bootstrap_iterations, cfg.random_seed)
    n = len(v)
    matched = v[v.min_stay_matched]
    differing = v[v.min_stay_differs]
    unknown = v[v.min_stay_unknown]
    return {
        "window_days": len(pos),
        "competitor_listings": n_comps_total,
        "subject_available_days": available_days,
        "eligible_comparison_days": n,
        "excluded_for_insufficient_comps": int((pos.our_available & (pos.n_comps < cfg.min_active_comps)).sum()),
        "median_available_comps": float(v.n_comps.median()) if n else np.nan,
        "min_available_comps": int(v.n_comps.min()) if n else 0,
        "days_below_p25": int(counts["Below P25"]),
        "days_below_median": int(counts["Below P25"] + counts["P25 to below P50"]),
        "share_below_median_pct": 100 * (counts["Below P25"] + counts["P25 to below P50"]) / n if n else np.nan,
        "share_below_p25_pct": 100 * counts["Below P25"] / n if n else np.nan,
        "median_daily_gap_pct": float(v.gap_vs_median_pct.median()) if n else np.nan,
        "median_daily_gap_ci95_low_pct": lo,
        "median_daily_gap_ci95_high_pct": hi,
        "bootstrap_weeks": n_weeks,
        "mean_daily_gap_pct": float(v.gap_vs_median_pct.mean()) if n else np.nan,
        "geometric_mean_gap_pct": float((np.exp(v.log_gap_vs_median.mean()) - 1) * 100) if n else np.nan,
        "median_gap_vs_all_priced_comps_pct": float(v.gap_vs_all_priced_median_pct.median()) if n else np.nan,
        "median_comp_available_share_pct": float(v.comp_available_share.median() * 100) if n else np.nan,
        "days_min_stay_differs": int(v.min_stay_differs.sum()),
        "days_min_stay_matched": len(matched),
        "days_min_stay_unknown": len(unknown),
        "min_stay_match_share_pct": (100 * len(matched) / n) if n else np.nan,
        "median_gap_min_stay_matched_pct": float(matched.gap_vs_median_pct.median()) if len(matched) else np.nan,
        "median_gap_min_stay_different_pct": float(differing.gap_vs_median_pct.median()) if len(differing) else np.nan,
        "days_below_median_min_stay_matched": int((matched.our_price < matched.comp_median).sum()),
        "days_below_median_min_stay_different": int((differing.our_price < differing.comp_median).sum()),
    }


def band_counts_by_day_group(pos: pd.DataFrame) -> pd.DataFrame:
    v = pos[pos.eligible]
    return pd.crosstab(v.day_group, v.price_band).reindex(columns=BANDS, fill_value=0)


# --------------------------------------------------------------------------------------------
# Bookings: booking-creation window (pace) and stay-date allocation
# --------------------------------------------------------------------------------------------
def booking_window_metrics(bd: BookingsData, cfg: AnalysisConfig) -> tuple[dict, pd.DataFrame]:
    b = bd.frame
    in_window = b.booked_date.between(cfg.ts("booking_start"), cfg.ts("booking_end"))
    valid = b[in_window & b.status_class.eq("valid")].copy()
    excluded = int((in_window & b.status_class.eq("excluded")).sum())
    days = cfg.days_in("booking_start", "booking_end")
    nights = int(valid.nights.sum())
    revenue = float(valid.rental_revenue.sum())
    lead = valid.lead_days
    if bd.has_booking_window:
        diff = (valid.lead_days - valid.booking_window_reported).abs()
        lead_exact = int((diff != 0).sum())
        lead_beyond_1 = int((diff > 1).sum())
    else:
        lead_exact = lead_beyond_1 = None
    if bd.reservation_id_column:
        dupes = int(valid.duplicated(subset=[bd.reservation_id_column]).sum())
    else:
        dupes = int(valid.duplicated(subset=["booked_date", "check_in", "check_out", "rental_revenue"]).sum())
    summary = {
        "booking_window_days": days,
        "reservations": len(valid),
        "excluded_status_reservations": excluded,
        "booked_nights": nights,
        "rental_revenue": revenue,
        "weighted_booking_adr": revenue / nights if nights else np.nan,
        "bookings_per_week": len(valid) * 7 / days,
        "nights_per_week": nights * 7 / days,
        "median_lead_days": float(lead.median()) if len(valid) else np.nan,
        "mean_lead_days": float(lead.mean()) if len(valid) else np.nan,
        "p25_lead_days": float(lead.quantile(0.25)) if len(valid) else np.nan,
        "p75_lead_days": float(lead.quantile(0.75)) if len(valid) else np.nan,
        "mean_los_nights": float(valid.nights.mean()) if len(valid) else np.nan,
        "median_los_nights": float(valid.nights.median()) if len(valid) else np.nan,
        "los_mismatches": int((valid.nights != valid.los_reported).sum()),
        "lead_mismatches_exact": lead_exact,
        "lead_mismatches_beyond_1_day": lead_beyond_1,
        "possible_duplicate_reservations": dupes,
    }
    return summary, valid


def stay_night_allocation(bd: BookingsData) -> pd.DataFrame:
    """One row per occupied night of every valid reservation, with revenue spread evenly per night."""
    v = bd.frame[bd.frame.status_class.eq("valid")]
    if v.empty:
        return pd.DataFrame(columns=["stay_date", "revenue", "booked_date"])
    rep = v.loc[v.index.repeat(v.nights)].copy()
    offset = rep.groupby(level=0).cumcount()
    rep["stay_date"] = rep.check_in + pd.to_timedelta(offset, unit="D")
    rep["revenue"] = rep.rental_revenue / rep.nights
    return rep[["stay_date", "revenue", "booked_date"]].reset_index(drop=True)


def stay_window_from_bookings(nights: pd.DataFrame, start: pd.Timestamp, end: pd.Timestamp) -> dict:
    w = nights[nights.stay_date.between(start, end)]
    booked = len(w)
    revenue = float(w.revenue.sum())
    overlaps = int(w.stay_date.duplicated().sum())
    return {
        "booked_nights": booked,
        "rental_revenue": revenue,
        "adr": revenue / booked if booked else np.nan,
        "overlapping_nights": overlaps,
    }


# --------------------------------------------------------------------------------------------
# PriceLabs Report Builder comparison (ADR, occupancy, RevPAR)
# --------------------------------------------------------------------------------------------
def market_comparison(rows: list[ReportBuilderRow]) -> pd.DataFrame:
    out = []
    for r in rows:
        v = r.values
        adr, madr = v["Rental ADR"], v["Market ADR"]
        occ, mocc = v["Adjusted Occupancy %"], v["Market Occupancy %"]
        revpar = adr * occ / 100 if pd.notna(adr) else np.nan
        mrevpar = madr * mocc / 100
        out.append(
            {
                "period": r.label,
                "rental_adr": adr,
                "market_adr": madr,
                "adr_gap_pct": (adr / madr - 1) * 100 if pd.notna(adr) else np.nan,
                "adjusted_occupancy_pct": occ,
                "market_occupancy_pct": mocc,
                "occupancy_gap_pp": occ - mocc,
                "revpar_proxy": revpar,
                "market_revpar_proxy": mrevpar,
                "revpar_gap_pct": (revpar / mrevpar - 1) * 100 if mrevpar and pd.notna(revpar) else np.nan,
                "reported_rental_revpar": v.get("Rental RevPAR", np.nan),
                "rental_revenue": v.get("Rental Revenue", np.nan),
                "booked_nights": v.get("Booked Nights", np.nan),
                "number_of_bookings": v.get("Number of Bookings", np.nan),
                "pickup_30d_nights": v.get("Booked Nights Pickup (30 Days)", np.nan),
                "pickup_7d_nights": v.get("Booked Nights Pickup (7 Days)", np.nan),
                "average_booking_window": v.get("Average Booking Window", np.nan),
                "average_los": v.get("Average LOS", np.nan),
            }
        )
    return pd.DataFrame(out)
