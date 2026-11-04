"""Deterministic synthetic PriceLabs-style exports for tests and demonstrations.

Contains no real listings, prices or reservations. Values are generated from a seeded RNG so the
same seed always produces byte-identical files.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SYNTHETIC_TARGET = "SYNTHETIC 6BR Pool Home"
SYNTHETIC_OTHER = "SYNTHETIC Other Portfolio Home"

DEFAULT_WINDOWS = {
    "booking_start": "2026-10-11",
    "booking_end": "2026-11-02",
    "historical_stay_start": "2026-10-11",
    "historical_stay_end": "2026-11-02",
    "forward_start": "2026-11-03",
    "forward_end": "2027-01-31",
}


def _money(x: float) -> str:
    return f"${x:,.2f}"


def _base_rate(day: pd.Timestamp) -> float:
    rate = 420.0
    if day.dayofweek in (4, 5):
        rate *= 1.25
    if (day.month == 12 and day.day >= 20) or (day.month == 1 and day.day <= 2):
        rate *= 1.45
    if day.month == 11 and 25 <= day.day <= 29:
        rate *= 1.20
    return rate


def generate_synthetic_dataset(
    out_dir: Path | str,
    seed: int = 7,
    n_comps: int = 10,
    target_price_ratio: float = 0.75,
    windows: dict | None = None,
    calendar_date_format: str = "%d/%m/%Y",
) -> dict:
    """Write the four input CSVs into out_dir and return the ground truth used to build them."""
    w = {**DEFAULT_WINDOWS, **(windows or {})}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    hist_lo, hist_hi = pd.Timestamp(w["historical_stay_start"]), pd.Timestamp(w["historical_stay_end"])
    fwd_lo, fwd_hi = pd.Timestamp(w["forward_start"]), pd.Timestamp(w["forward_end"])
    today = fwd_lo - pd.Timedelta(days=1)

    # ---- Subject reservations: non-overlapping stays across both windows -------------------
    reservations = []
    day = hist_lo
    rid = 1000
    while day <= fwd_hi:
        p_start = 0.55 if day <= hist_hi else max(0.08, 0.30 - 0.0025 * (day - fwd_lo).days)
        if rng.random() < p_start:
            los = int(rng.integers(2, 7))
            check_out = min(day + pd.Timedelta(days=los), fwd_hi + pd.Timedelta(days=1))
            los = (check_out - day).days
            if los >= 1:
                lead = int(rng.integers(3, 90))
                booked = day - pd.Timedelta(days=lead)
                if booked > today:
                    booked = today - pd.Timedelta(days=int(rng.integers(0, 20)))
                    lead = (day - booked).days
                nightly = [_base_rate(day + pd.Timedelta(days=i)) * target_price_ratio for i in range(los)]
                revenue = round(float(np.sum(nightly)), 2)
                hour, minute = int(rng.integers(0, 24)), int(rng.integers(0, 60))
                reservations.append({
                    "Reservation ID": f"SYN-{rid}",
                    "Listing Name": SYNTHETIC_TARGET,
                    "Booked Date": f"{booked:%Y-%m-%d} {hour:02d}:{minute:02d}:00",
                    "Check-in Date": f"{day:%Y-%m-%d}",
                    "Check-out Date": f"{check_out:%Y-%m-%d}",
                    "Rental Revenue": _money(revenue),
                    "Length of Stay (Days)": los,
                    "Booking Window (Days)": lead,
                    "Booking Status": "Booked",
                    "_revenue": revenue,
                })
                rid += 1
                day = check_out + pd.Timedelta(days=int(rng.integers(0, 3)))
                continue
        day += pd.Timedelta(days=1)

    # Cancelled reservations (must be excluded) and another listing (must be filtered out).
    for i in range(3):
        ci = fwd_lo + pd.Timedelta(days=10 + 7 * i)
        reservations.append({
            "Reservation ID": f"SYN-C{i}", "Listing Name": SYNTHETIC_TARGET,
            "Booked Date": f"{today - pd.Timedelta(days=i + 1):%Y-%m-%d} 09:00:00",
            "Check-in Date": f"{ci:%Y-%m-%d}", "Check-out Date": f"{ci + pd.Timedelta(days=3):%Y-%m-%d}",
            "Rental Revenue": _money(999.0), "Length of Stay (Days)": 3, "Booking Window (Days)": 0,
            "Booking Status": "Cancelled", "_revenue": 0.0,
        })
    for i in range(4):
        ci = hist_lo + pd.Timedelta(days=4 * i)
        reservations.append({
            "Reservation ID": f"SYN-O{i}", "Listing Name": SYNTHETIC_OTHER,
            "Booked Date": f"{ci - pd.Timedelta(days=20):%Y-%m-%d} 12:00:00",
            "Check-in Date": f"{ci:%Y-%m-%d}", "Check-out Date": f"{ci + pd.Timedelta(days=2):%Y-%m-%d}",
            "Rental Revenue": _money(500.0), "Length of Stay (Days)": 2, "Booking Window (Days)": 20,
            "Booking Status": "Booked", "_revenue": 500.0,
        })
    bookings = pd.DataFrame(reservations)
    bookings.drop(columns="_revenue").to_csv(out / "bookings.csv", index=False)

    valid = bookings[(bookings["Listing Name"] == SYNTHETIC_TARGET) & (bookings["Booking Status"] == "Booked")]
    occupied: dict = {}
    for _, r in valid.iterrows():
        ci, co = pd.Timestamp(r["Check-in Date"]), pd.Timestamp(r["Check-out Date"])
        n = (co - ci).days
        for k in range(n):
            occupied[ci + pd.Timedelta(days=k)] = r["_revenue"] / n

    # ---- Competitor calendar (3 header rows) ---------------------------------------------
    days = pd.date_range(fwd_lo, fwd_hi, freq="D")
    comp_names = [f"Synthetic Comp {i:02d}" for i in range(1, n_comps + 1)]
    multipliers = rng.uniform(0.85, 1.20, n_comps)
    header0, header1 = [""], [""]
    for name in [SYNTHETIC_TARGET, *comp_names]:
        header0 += [name, "", ""]
        header1 += ["prices", "available", "min_stay"]
    rows = [header0, header1, ["Date"] + [""] * (3 * (n_comps + 1))]
    for d in days:
        row = [f"{d:{calendar_date_format}}"]
        base = _base_rate(d)
        row += [f"{round(base * target_price_ratio):d}", "0" if d in occupied else "1", "2"]
        for m in multipliers:
            price = round(base * m * rng.uniform(0.97, 1.03))
            available = "1" if rng.random() < 0.72 else "0"
            row += [f"{price:d}", available, "3" if d.dayofweek in (4, 5) else "2"]
        rows.append(row)
    pd.DataFrame(rows).to_csv(out / "competitor_calendar.csv", index=False, header=False)

    # ---- Report Builder rows, consistent with the reservations ---------------------------
    def rb_row(lo, hi, market_adr, market_occ, pickup):
        nights = [d for d in occupied if lo <= d <= hi]
        revenue = round(sum(occupied[d] for d in nights), 2)
        n_days = (hi - lo).days + 1
        adr = revenue / len(nights) if nights else 0.0
        stays = valid[(pd.to_datetime(valid["Check-in Date"]) <= hi) & (pd.to_datetime(valid["Check-out Date"]) > lo)]
        return {
            "Listing Name": SYNTHETIC_TARGET,
            "Rental ADR": _money(adr),
            "Market ADR": _money(market_adr),
            "Adjusted Occupancy %": f"{100 * len(nights) / n_days:.1f}%",
            "Market Occupancy %": f"{market_occ:.1f}%",
            "Number of Bookings": len(stays),
            "Booked Nights": len(nights),
            "Booked Nights Pickup (30 Days)": pickup,
            "Booked Nights Pickup (7 Days)": pickup // 4,
            "Rental Revenue": _money(revenue),
            "Rental RevPAR": _money(revenue / n_days),
            "Average Booking Window": round(float(stays["Booking Window (Days)"].mean()), 1) if len(stays) else 0,
            "Average LOS": round(float(stays["Length of Stay (Days)"].mean()), 1) if len(stays) else 0,
        }, {"nights": len(nights), "revenue": revenue, "adr": adr}

    other = {"Listing Name": SYNTHETIC_OTHER, "Rental ADR": "$300.00", "Market ADR": "$310.00",
             "Adjusted Occupancy %": "50.0%", "Market Occupancy %": "52.0%", "Number of Bookings": 4,
             "Booked Nights": 8, "Booked Nights Pickup (30 Days)": 2, "Booked Nights Pickup (7 Days)": 0,
             "Rental Revenue": "$2,400.00", "Rental RevPAR": "$150.00", "Average Booking Window": 20,
             "Average LOS": 2}
    hist_row, hist_truth = rb_row(hist_lo, hist_hi, 540.0, 54.0, 6)
    fwd_row, fwd_truth = rb_row(fwd_lo, fwd_hi, 600.0, 25.0, 18)
    pd.DataFrame([other, hist_row]).to_csv(out / "report_builder_historical.csv", index=False)
    pd.DataFrame([other, fwd_row]).to_csv(out / "report_builder_forward.csv", index=False)

    return {
        "target": SYNTHETIC_TARGET,
        "comps": comp_names,
        "comp_multipliers": multipliers.tolist(),
        "target_price_ratio": target_price_ratio,
        "valid_target_reservations": len(valid),
        "historical": hist_truth,
        "forward": fwd_truth,
        "windows": w,
    }
