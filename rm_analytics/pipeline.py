"""End-to-end analysis: load -> validate -> compute -> audit. Used by the notebook and the tests."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .audit import FAIL, PASS, WARN, AuditLog, pct_diff
from .config import AnalysisConfig
from .duplicates import apply_duplicate_policy, detect_duplicate_listings
from .loaders import BookingsData, CalendarData, ReportBuilderRow, load_bookings, load_calendar, load_report_builder
from .metrics import (
    band_counts_by_day_group,
    booking_window_metrics,
    compute_daily_positions,
    market_comparison,
    stay_night_allocation,
    stay_window_from_bookings,
    summarize_positions,
)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass
class AnalysisResult:
    cfg: AnalysisConfig
    project_root: Path
    input_paths: dict
    input_hashes: dict
    calendar: CalendarData
    bookings: BookingsData
    report_historical: ReportBuilderRow
    report_forward: ReportBuilderRow
    duplicates: pd.DataFrame
    dropped_comps: list
    comps: list
    positions: pd.DataFrame
    position_summary: dict
    band_by_day_group: pd.DataFrame
    booking_summary: dict
    window_bookings: pd.DataFrame
    reconciliation: pd.DataFrame
    market: pd.DataFrame
    audit: AuditLog
    summary_table: pd.DataFrame = field(default=None)

    @property
    def eligible_positions(self) -> pd.DataFrame:
        return self.positions[self.positions.eligible]


def run_analysis(cfg: AnalysisConfig, project_root: Path | str = ".") -> AnalysisResult:
    root = Path(project_root)
    paths = cfg.input_paths(root)
    missing = [str(p) for p in paths.values() if not p.is_file()]
    if missing:
        from .errors import DataValidationError

        raise DataValidationError(f"Missing input file(s): {missing}")
    hashes = {k: sha256_file(p) for k, p in paths.items()}
    audit = AuditLog()

    # ---- Load (structural problems raise immediately) -----------------------------------
    cal = load_calendar(paths["calendar"], cfg)
    bookings = load_bookings(paths["bookings"], cfg)
    rb_h = load_report_builder(paths["historical"], cfg, "historical")
    rb_f = load_report_builder(paths["forward"], cfg, "forward")
    audit.add("inputs", "Subject listing resolved in every file", PASS,
              f"calendar={cal.target!r}; bookings={bookings.listing!r}; report builder={rb_h.listing!r}/{rb_f.listing!r}")
    names = {cal.target, bookings.listing, rb_h.listing, rb_f.listing}
    audit.require("inputs", "Subject listing name identical across exports", len(names) == 1,
                  f"names found: {sorted(names)}", WARN)
    audit.add("inputs", "Date formats detected", PASS,
              f"calendar={cal.date_format}; bookings={bookings.date_format}")
    for note in cal.notes + bookings.notes + rb_h.notes + rb_f.notes:
        audit.add("inputs", "Input note", WARN, note)
    if cfg.is_synthetic_example:
        audit.add("inputs", "Synthetic example data", WARN, "SYNTHETIC DATA - results are illustrative, not for pricing decisions")

    # ---- Comp set and duplicates ----------------------------------------------------------
    dups = detect_duplicate_listings(cal.frame, cal.target, cfg)
    frame, comps, dropped = apply_duplicate_policy(cal.frame, cal.comps, cal.target, dups, cfg)
    target_dups = dups[dups.involves_target & dups.match_basis.eq("price_and_availability")] if len(dups) else dups
    if dups.empty:
        audit.add("comp set", "Probable duplicate homes", PASS, "no near-identical price/availability series found")
    else:
        pairs = "; ".join(
            f"{r.listing_a} ~ {r.listing_b} ({r.match_basis}; corr {r.price_corr}, "
            f"median diff {r.median_abs_diff_pct}%; shared blocked {r.shared_blocked_days})"
            for r in dups.itertuples(index=False)
        )
        if len(target_dups) and cfg.duplicate_policy == "warn":
            audit.add("comp set", "Comp set contains the subject home", FAIL,
                      f"{pairs}. A comp looks like our own listing; exclude it or set duplicate_policy='drop'")
        else:
            action = f"dropped strong matches {dropped}; review remaining signals" if dropped else "kept; investigate possible physical duplicates manually"
            audit.add("comp set", "Probable duplicate homes", WARN, f"{pairs}; {action}")
    audit.require("comp set", "Comp set size >= min_active_comps", len(comps) >= cfg.min_active_comps,
                  f"{len(comps)} comps; min_active_comps={cfg.min_active_comps}")
    audit.require("comp set", "min_active_comps >= 3", cfg.min_active_comps >= 3,
                  f"min_active_comps={cfg.min_active_comps}; percentiles from fewer than 3 prices are unstable", WARN)

    # ---- Daily positions ------------------------------------------------------------------
    pos = compute_daily_positions(cal, frame, comps, cfg)
    psum = summarize_positions(pos, len(comps), cfg)
    eligible, available = psum["eligible_comparison_days"], psum["subject_available_days"]
    audit.require("pricing", "At least one eligible comparison date", eligible > 0,
                  f"{eligible} eligible of {available} available dates")
    audit.require("pricing", "Eligible dates cover >= 50% of available dates",
                  available == 0 or eligible / available >= 0.5,
                  f"{eligible}/{available}; {psum['excluded_for_insufficient_comps']} dates dropped for insufficient comps", WARN)
    if eligible:
        bias = psum["median_gap_vs_all_priced_comps_pct"] - psum["median_daily_gap_pct"]
        audit.require("pricing", "Availability-filter sensitivity < 5 pp", abs(bias) < 5,
                      f"median gap {psum['median_daily_gap_pct']:.2f}% (available comps) vs "
                      f"{psum['median_gap_vs_all_priced_comps_pct']:.2f}% (all priced comps)", WARN)
        audit.require("pricing", "Minimum stay comparable on >= 75% of eligible dates",
                      psum["days_min_stay_matched"] >= 0.75 * eligible,
                      f"{psum['days_min_stay_matched']} matched, {psum['days_min_stay_differs']} different, "
                      f"{psum['days_min_stay_unknown']} unknown of {eligible} eligible dates; "
                      "see minimum_stay_sensitivity.csv. This does not control cleaning fees or LOS discounts", WARN)

    # ---- Bookings -------------------------------------------------------------------------
    bsum, window_bookings = booking_window_metrics(bookings, cfg)
    audit.require("bookings", "Booking Status column present", bookings.has_status_column,
                  "cancellations excluded by status" if bookings.has_status_column else "cancellations cannot be excluded", WARN)
    audit.require("bookings", "Reservations found in booking window", bsum["reservations"] > 0,
                  f"{bsum['reservations']} valid, {bsum['excluded_status_reservations']} excluded by status", WARN)
    audit.require("bookings", "Length of stay reconciles with check-in/check-out", bsum["los_mismatches"] == 0,
                  f"{bsum['los_mismatches']} mismatches")
    if bookings.has_booking_window:
        audit.require("bookings", "Booking Window field reconciles with computed lead time (+/-1 day)",
                      bsum["lead_mismatches_beyond_1_day"] == 0,
                      f"{bsum['lead_mismatches_exact']} differ, {bsum['lead_mismatches_beyond_1_day']} by more than 1 day", WARN)
    audit.require("bookings", "No probable duplicate reservations", bsum["possible_duplicate_reservations"] == 0,
                  f"{bsum['possible_duplicate_reservations']} possible duplicates "
                  f"(key: {bookings.reservation_id_column or 'dates + revenue'})", WARN)

    # ---- Reconciliation: bookings vs Report Builder by stay date ---------------------------
    nights = stay_night_allocation(bookings)
    recon_rows = []
    tol = cfg.reconciliation_tolerance_pct
    for rb, (s, e) in ((rb_h, ("historical_stay_start", "historical_stay_end")),
                       (rb_f, ("forward_start", "forward_end"))):
        stay = stay_window_from_bookings(nights, cfg.ts(s), cfg.ts(e))
        audit.require("reconciliation", f"No overlapping reservations ({rb.label})", stay["overlapping_nights"] == 0,
                      f"{stay['overlapping_nights']} nights booked more than once")
        v = rb.values
        rb_nights, rb_rev, rb_adr = v["Booked Nights"], v["Rental Revenue"], v["Rental ADR"]
        if pd.notna(rb_nights) and pd.notna(rb_rev) and rb_nights > 0 and pd.notna(rb_adr):
            d = pct_diff(rb_rev / rb_nights, rb_adr)
            audit.require("reconciliation", f"Report Builder ADR = revenue / nights ({rb.label})", d <= tol,
                          f"revenue/nights={rb_rev / rb_nights:.2f} vs Rental ADR={rb_adr:.2f} ({d:.2f}% diff)", WARN)
        d_n = pct_diff(stay["booked_nights"], rb_nights) if pd.notna(rb_nights) else np.nan
        d_r = pct_diff(stay["rental_revenue"], rb_rev) if pd.notna(rb_rev) else np.nan
        for label, d, ours, theirs in (("booked nights", d_n, stay["booked_nights"], rb_nights),
                                       ("rental revenue", d_r, stay["rental_revenue"], rb_rev)):
            if pd.isna(theirs):
                audit.add("reconciliation", f"Bookings vs Report Builder {label} ({rb.label})", WARN,
                          "Report Builder column missing; period cannot be cross-checked")
            elif theirs == 0 and ours == 0:
                audit.add("reconciliation", f"Bookings vs Report Builder {label} ({rb.label})", PASS, "both zero")
            else:
                ok = pd.notna(d) and d <= tol
                audit.require("reconciliation", f"Bookings vs Report Builder {label} ({rb.label})", ok,
                              f"bookings={ours:,.2f} vs report builder={theirs:,.2f} ({d:.2f}% diff). A mismatch can mean "
                              "a wrong Stay Date Range, a filtered Bookings export, or status differences", WARN)
        recon_rows.append({"period": rb.label, "bookings_stay_nights": stay["booked_nights"],
                           "report_builder_nights": rb_nights, "nights_diff_pct": d_n,
                           "bookings_stay_revenue": stay["rental_revenue"], "report_builder_revenue": rb_rev,
                           "revenue_diff_pct": d_r, "bookings_stay_adr": stay["adr"], "report_builder_adr": rb_adr})
        if rb.missing_optional:
            audit.add("inputs", f"Optional Report Builder columns missing ({rb.label})", WARN, ", ".join(rb.missing_optional))

    market = market_comparison([rb_h, rb_f])

    # ---- Governance attestations ----------------------------------------------------------
    audit.require("governance", "Report Builder stay-date ranges verified in PriceLabs (attested)",
                  cfg.attest_report_periods_verified, "set attest_report_periods_verified=True after checking screenshots", WARN)
    audit.require("governance", "Comp set and duplicates reviewed (attested)", cfg.attest_comp_set_reviewed,
                  "set attest_comp_set_reviewed=True after review", WARN)
    audit.require("governance", "Storage location approved (attested)", cfg.attest_storage_approved,
                  "set attest_storage_approved=True once inputs/outputs are in approved restricted storage", WARN)
    audit.require("governance", "Analyst identified", bool(cfg.analyst.strip()), f"analyst={cfg.analyst!r}", WARN)

    result = AnalysisResult(
        cfg=cfg, project_root=root, input_paths=paths, input_hashes=hashes, calendar=cal, bookings=bookings,
        report_historical=rb_h, report_forward=rb_f, duplicates=dups, dropped_comps=dropped, comps=comps,
        positions=pos, position_summary=psum, band_by_day_group=band_counts_by_day_group(pos),
        booking_summary=bsum, window_bookings=window_bookings, reconciliation=pd.DataFrame(recon_rows),
        market=market, audit=audit,
    )
    result.summary_table = build_summary_table(result)
    return result


def build_summary_table(r: AnalysisResult) -> pd.DataFrame:
    p, b, m = r.position_summary, r.booking_summary, r.market.set_index("period")
    rows = [
        ("pricing", "Forward window days", p["window_days"], "days"),
        ("pricing", "Competitor listings used", p["competitor_listings"], "listings"),
        ("pricing", "Subject available days", p["subject_available_days"], "days"),
        ("pricing", "Eligible comparison days", p["eligible_comparison_days"], "days"),
        ("pricing", "Median available comps per eligible day", p["median_available_comps"], "listings"),
        ("pricing", "Days below comp P25", p["days_below_p25"], "days"),
        ("pricing", "Days below comp median", p["days_below_median"], "days"),
        ("pricing", "Share below comp median", p["share_below_median_pct"], "%"),
        ("pricing", "Median daily gap vs comp median", p["median_daily_gap_pct"], "%"),
        ("pricing", "Median daily gap 95% CI low (weekly block bootstrap)", p["median_daily_gap_ci95_low_pct"], "%"),
        ("pricing", "Median daily gap 95% CI high (weekly block bootstrap)", p["median_daily_gap_ci95_high_pct"], "%"),
        ("pricing", "Mean daily gap", p["mean_daily_gap_pct"], "%"),
        ("pricing", "Minimum-stay matched comparison dates", p["days_min_stay_matched"], "days"),
        ("pricing", "Minimum-stay different comparison dates", p["days_min_stay_differs"], "days"),
        ("pricing", "Minimum-stay unknown comparison dates", p["days_min_stay_unknown"], "days"),
        ("pricing", "Median price gap on matched-minimum-stay dates", p["median_gap_min_stay_matched_pct"], "%"),
        ("pricing", "Median price gap on different-minimum-stay dates", p["median_gap_min_stay_different_pct"], "%"),
        ("pricing", "Geometric mean gap", p["geometric_mean_gap_pct"], "%"),
        ("pricing", "Median gap vs all priced comps (bias sensitivity)", p["median_gap_vs_all_priced_comps_pct"], "%"),
        ("bookings", "Reservations created in booking window", b["reservations"], "bookings"),
        ("bookings", "Booked nights (booking window)", b["booked_nights"], "nights"),
        ("bookings", "Rental revenue (booking window)", b["rental_revenue"], r.cfg.report_currency),
        ("bookings", "Weighted booking ADR", b["weighted_booking_adr"], r.cfg.report_currency),
        ("bookings", "Bookings per week", b["bookings_per_week"], "bookings"),
        ("bookings", "Median lead time", b["median_lead_days"], "days"),
        ("bookings", "Mean length of stay", b["mean_los_nights"], "nights"),
    ]
    for period in ("historical", "forward"):
        rows += [
            ("market", f"ADR vs market ADR ({period})", m.loc[period, "adr_gap_pct"], "%"),
            ("market", f"Occupancy gap ({period})", m.loc[period, "occupancy_gap_pp"], "pp"),
            ("market", f"RevPAR proxy vs market ({period})", m.loc[period, "revpar_gap_pct"], "%"),
        ]
    table = pd.DataFrame(rows, columns=["section", "metric", "value", "unit"])
    table["value"] = pd.to_numeric(table["value"], errors="raise").astype(float).round(4)
    return table
