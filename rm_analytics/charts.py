"""Charts derived from the current run (no hand-coded numbers)."""

from __future__ import annotations

import matplotlib.pyplot as plt
import pandas as pd

from .metrics import BANDS
from .pipeline import AnalysisResult


def build_figures(r: AnalysisResult) -> dict:
    cur = r.cfg.report_currency
    v = r.eligible_positions
    figs = {}

    fig, ax = plt.subplots(figsize=(8, 4))
    counts = v.price_band.value_counts().reindex(BANDS, fill_value=0)
    ax.bar(counts.index, counts.values)
    ax.set(title=f"Eligible dates by comp price band (n={len(v)})", ylabel="Dates")
    ax.tick_params(axis="x", rotation=15)
    fig.tight_layout()
    figs["pricing_bands"] = fig

    fig, ax = plt.subplots(figsize=(11, 4))
    p = r.positions
    ax.fill_between(p.index, p.comp_p25, p.comp_p75, alpha=0.25, label="Comp P25-P75 (available comps)")
    ax.plot(p.index, p.comp_median, label="Comp median (available comps)")
    ax.plot(p.index, p.our_price.where(p.our_available), marker=".", linestyle="", label="Our advertised rate (available dates)")
    ax.set(title="Daily advertised-rate position", ylabel=cur)
    ax.legend(loc="upper left")
    fig.autofmt_xdate()
    fig.tight_layout()
    figs["pricing_timeseries"] = fig

    fig, ax = plt.subplots(figsize=(8, 4))
    groups = [g.gap_vs_median_pct.values for _, g in v.groupby("day_group")]
    labels = [k for k, _ in v.groupby("day_group")]
    if groups:
        ax.boxplot(groups, tick_labels=labels) if _supports_tick_labels() else ax.boxplot(groups, labels=labels)
    ax.axhline(0, linewidth=0.8)
    ax.set(title="Daily gap vs comp median by day group", ylabel="Gap (%)")
    fig.tight_layout()
    figs["weekday_price_gap"] = fig

    fig, ax = plt.subplots(figsize=(11, 4))
    pace = r.window_bookings.groupby("booked_date").size().reindex(
        pd.date_range(r.cfg.booking_start, r.cfg.booking_end), fill_value=0)
    ax.bar(pace.index, pace.values)
    ax.set(title="Reservations created per day (Booked Date)", ylabel="Reservations")
    fig.autofmt_xdate()
    fig.tight_layout()
    figs["booking_pace"] = fig
    return figs


def _supports_tick_labels() -> bool:
    import matplotlib

    major, minor = (int(x) for x in matplotlib.__version__.split(".")[:2])
    return (major, minor) >= (3, 9)
