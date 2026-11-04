import numpy as np
import pandas as pd
import pytest

from rm_analytics.duplicates import apply_duplicate_policy, detect_duplicate_listings
from rm_analytics.loaders import load_bookings, load_calendar
from rm_analytics.metrics import (
    block_bootstrap_median_ci,
    booking_window_metrics,
    compute_daily_positions,
    market_comparison,
    stay_night_allocation,
    stay_window_from_bookings,
    summarize_positions,
)

from conftest import make_cfg, read_raw

WIN = dict(
    booking_start="2026-10-01", booking_end="2026-10-31",
    historical_stay_start="2026-10-01", historical_stay_end="2026-10-31",
    forward_start="2026-11-02", forward_end="2026-11-04",
)


def write_calendar(path, start, listings):
    """listings: {name: (prices, availability, min_stay)} with equal-length lists."""
    n = len(next(iter(listings.values()))[0])
    dates = pd.date_range(start, periods=n)
    h0, h1 = [""], [""]
    for name in listings:
        h0 += [name, "", ""]
        h1 += ["prices", "available", "min_stay"]
    rows = [h0, h1, ["Date"] + [""] * (3 * len(listings))]
    for i, d in enumerate(dates):
        row = [d.strftime("%Y-%m-%d")]
        for prices, avail, ms in listings.values():
            row += [str(prices[i]), str(avail[i]), str(ms[i])]
        rows.append(row)
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_csv(path, index=False, header=False)
    return path


def positions_for(tmp_path, listings, **cfg_over):
    cfg = make_cfg(tmp_path, property_name="Ours", **{**WIN, **cfg_over})
    path = write_calendar(tmp_path / "cal.csv", WIN["forward_start"], listings)
    cal = load_calendar(path, cfg)
    return compute_daily_positions(cal, cal.frame, cal.comps, cfg), cfg, cal


def test_percentiles_match_excel_percentile_inc(tmp_path):
    comp_prices = [100, 200, 300, 400, 1000]
    listings = {"Ours": ([150] * 3, [1] * 3, [2] * 3)}
    for i, p in enumerate(comp_prices):
        listings[f"C{i}"] = ([p] * 3, [1] * 3, [2] * 3)
    pos, cfg, _ = positions_for(tmp_path, listings, min_active_comps=3)
    row = pos.iloc[0]
    # Excel PERCENTILE.INC({100,200,300,400,1000}, 0.25) = 200; 0.75 = 400
    assert row.comp_p25 == 200 and row.comp_median == 300 and row.comp_p75 == 400
    assert row.comp_mean == pytest.approx(400)
    assert row.comp_std == pytest.approx(np.std(comp_prices, ddof=1))
    assert row.gap_vs_median_pct == pytest.approx((150 / 300 - 1) * 100)
    assert row.price_band == "Below P25"


def test_unavailable_and_zero_priced_comps_excluded_and_sensitivity_reported(tmp_path):
    listings = {
        "Ours": ([200] * 3, [1] * 3, [2] * 3),
        "A": ([100] * 3, [1] * 3, [2] * 3),
        "B": ([300] * 3, [1] * 3, [2] * 3),
        "C": ([900] * 3, [0] * 3, [2] * 3),  # unavailable: excluded from stats, kept in sensitivity
        "D": ([0] * 3, [1] * 3, [2] * 3),  # zero price: excluded everywhere
    }
    pos, _, _ = positions_for(tmp_path, listings, min_active_comps=2)
    row = pos.iloc[0]
    assert row.n_comps == 2 and row.comp_median == 200
    assert row.n_comps_priced == 3 and row.comp_median_all_priced == 300


def test_band_boundaries(tmp_path):
    comps = [100, 200, 300, 400, 500]  # P25=200, P50=300, P75=400
    for ours, band in [(199, "Below P25"), (200, "P25 to below P50"), (300, "P50 to P75"), (400, "P50 to P75"), (401, "Above P75")]:
        listings = {"Ours": ([ours] * 3, [1] * 3, [2] * 3)}
        listings.update({f"C{i}": ([p] * 3, [1] * 3, [2] * 3) for i, p in enumerate(comps)})
        pos, _, _ = positions_for(tmp_path, listings, min_active_comps=3)
        assert pos.iloc[0].price_band == band, ours


def test_min_active_comps_and_our_availability_gate_eligibility(tmp_path):
    listings = {
        "Ours": ([200, 200, 200], [1, 0, 1], [2] * 3),
        "A": ([100] * 3, [1, 1, 0], [2] * 3),
        "B": ([300] * 3, [1, 1, 0], [2] * 3),
    }
    pos, cfg, _ = positions_for(tmp_path, listings, min_active_comps=2)
    assert pos.eligible.tolist() == [True, False, False]
    assert pos.exclusion_reason.tolist() == ["", "subject listing unavailable", "fewer than 2 available comps"]
    s = summarize_positions(pos, 2, cfg)
    assert s["eligible_comparison_days"] == 1 and s["excluded_for_insufficient_comps"] == 1


def test_single_comp_std_is_nan(tmp_path):
    listings = {"Ours": ([200] * 3, [1] * 3, [2] * 3), "A": ([100] * 3, [1] * 3, [2] * 3)}
    pos, _, _ = positions_for(tmp_path, listings, min_active_comps=1)
    assert np.isnan(pos.iloc[0].comp_std)


def test_calendar_must_cover_forward_window(tmp_path):
    from rm_analytics.errors import DataValidationError

    listings = {"Ours": ([200] * 2, [1] * 2, [2] * 2), "A": ([100] * 2, [1] * 2, [2] * 2)}
    with pytest.raises(DataValidationError, match="does not cover"):
        positions_for(tmp_path, listings, min_active_comps=1)


def test_block_bootstrap_is_deterministic_and_brackets_median():
    idx = pd.date_range("2026-11-02", periods=56)
    vals = pd.Series(np.linspace(-30, -20, 56), index=idx)
    a = block_bootstrap_median_ci(vals, 500, 1)
    b = block_bootstrap_median_ci(vals, 500, 1)
    assert a == b
    assert a[0] <= vals.median() <= a[1] and a[2] == 8
    assert np.isnan(block_bootstrap_median_ci(vals.iloc[:10], 500, 1)[0])  # < 4 weeks


# ---- Duplicates (finding #13) ---------------------------------------------------------------
def _dup_listings(n=20):
    rng = np.random.default_rng(0)
    base = (300 + 50 * rng.standard_normal(n)).round()
    avail = (rng.random(n) > 0.3).astype(int)
    return {
        "Ours": (list((base * 0.8).round().astype(int)), [1] * n, [2] * n),
        "A": (list(base.astype(int)), list(avail), [2] * n),
        "A on other channel": (list(base.astype(int)), list(avail), [2] * n),
        "B": (list((300 + 50 * rng.standard_normal(n)).round().astype(int)), [1] * n, [2] * n),
    }


def test_duplicate_detection_and_drop_policy(tmp_path):
    cfg = make_cfg(tmp_path, property_name="Ours", **{**WIN, "forward_end": "2026-11-21"})
    cal = load_calendar(write_calendar(tmp_path / "c.csv", WIN["forward_start"], _dup_listings()), cfg)
    dups = detect_duplicate_listings(cal.frame, cal.target, cfg)
    assert len(dups) == 1 and set(dups.iloc[0][["listing_a", "listing_b"]]) == {"A", "A on other channel"}
    assert not dups.iloc[0].involves_target
    cfg_drop = make_cfg(tmp_path, property_name="Ours", duplicate_policy="drop", **{**WIN, "forward_end": "2026-11-21"})
    _, comps, dropped = apply_duplicate_policy(cal.frame, cal.comps, cal.target, dups, cfg_drop)
    assert len(dropped) == 1 and len(comps) == 2


def test_target_duplicated_in_comp_set_is_flagged(tmp_path):
    listings = _dup_listings()
    listings["Our home on VRBO"] = listings["Ours"]
    cfg = make_cfg(tmp_path, property_name="Ours", **{**WIN, "forward_end": "2026-11-21"})
    cal = load_calendar(write_calendar(tmp_path / "c.csv", WIN["forward_start"], listings), cfg)
    dups = detect_duplicate_listings(cal.frame, cal.target, cfg)
    assert dups.involves_target.any()


# ---- Bookings metrics (findings #2, #3, #8) ---------------------------------------------------
def test_booking_window_metrics_match_hand_calculation(dataset):
    path = dataset["data_dir"] / "bookings.csv"
    df = read_raw(path)
    bd = load_bookings(path, dataset["cfg"])
    s, valid = booking_window_metrics(bd, dataset["cfg"])
    # Independent hand calculation from the raw CSV
    raw = df[(df["Listing Name"] == dataset["truth"]["target"]) & (df["Booking Status"] == "Booked")].copy()
    booked = pd.to_datetime(raw["Booked Date"].str[:10])
    raw = raw[(booked >= "2026-10-11") & (booked <= "2026-11-02")]
    rev = raw["Rental Revenue"].str.replace("[$,]", "", regex=True).astype(float).sum()
    nights = (pd.to_datetime(raw["Check-out Date"]) - pd.to_datetime(raw["Check-in Date"])).dt.days.sum()
    assert s["reservations"] == len(raw)
    assert s["rental_revenue"] == pytest.approx(rev)
    assert s["booked_nights"] == nights
    assert s["weighted_booking_adr"] == pytest.approx(rev / nights)
    assert s["bookings_per_week"] == pytest.approx(len(raw) * 7 / 23)
    assert s["excluded_status_reservations"] == 3
    assert s["los_mismatches"] == 0


def test_last_day_booking_with_time_is_counted(dataset):
    path = dataset["data_dir"] / "bookings.csv"
    df = read_raw(path)
    before, _ = booking_window_metrics(load_bookings(path, dataset["cfg"]), dataset["cfg"])
    new = df.iloc[[0]].copy()
    new["Reservation ID"] = "SYN-LAST"
    new["Booked Date"] = "2026-11-02 23:59:00"
    new["Check-in Date"], new["Check-out Date"] = "2027-03-01", "2027-03-03"
    new["Length of Stay (Days)"], new["Booking Window (Days)"] = "2", "119"
    pd.concat([df, new]).to_csv(path, index=False)
    after, _ = booking_window_metrics(load_bookings(path, dataset["cfg"]), dataset["cfg"])
    assert after["reservations"] == before["reservations"] + 1


def test_los_mismatch_and_duplicate_reservations_are_counted(dataset):
    path = dataset["data_dir"] / "bookings.csv"
    df = read_raw(path)
    bd0 = load_bookings(path, dataset["cfg"])
    in_win = bd0.frame[bd0.frame.booked_date.between("2026-10-11", "2026-11-02") & bd0.frame.status_class.eq("valid")]
    rid = in_win["Reservation ID"].iloc[0]
    i = df.index[df["Reservation ID"] == rid][0]
    df.loc[i, "Length of Stay (Days)"] = "99"
    pd.concat([df, df.loc[[i]]]).to_csv(path, index=False)
    s, _ = booking_window_metrics(load_bookings(path, dataset["cfg"]), dataset["cfg"])
    assert s["los_mismatches"] >= 1 and s["possible_duplicate_reservations"] == 1


def test_stay_allocation_splits_reservation_across_window_boundary(dataset):
    bd = load_bookings(dataset["data_dir"] / "bookings.csv", dataset["cfg"])
    f = bd.frame
    f.loc[:, "status_class"] = "excluded"
    f.loc[0, ["status_class", "check_in", "check_out", "nights", "rental_revenue"]] = [
        "valid", pd.Timestamp("2026-10-30"), pd.Timestamp("2026-11-05"), 6, 600.0]
    nights = stay_night_allocation(bd)
    hist = stay_window_from_bookings(nights, pd.Timestamp("2026-10-11"), pd.Timestamp("2026-11-02"))
    fwd = stay_window_from_bookings(nights, pd.Timestamp("2026-11-03"), pd.Timestamp("2027-01-31"))
    assert hist["booked_nights"] == 4 and hist["rental_revenue"] == pytest.approx(400)
    assert fwd["booked_nights"] == 2 and fwd["adr"] == pytest.approx(100)


def test_market_comparison_revpar(dataset):
    from rm_analytics.loaders import ReportBuilderRow

    vals = {"Rental ADR": 205.03, "Market ADR": 312.78, "Adjusted Occupancy %": 65.0, "Market Occupancy %": 54.0}
    m = market_comparison([ReportBuilderRow("historical", "x", vals, [])]).iloc[0]
    assert m.revpar_proxy == pytest.approx(133.2695)
    assert m.market_revpar_proxy == pytest.approx(168.9012)
    assert m.revpar_gap_pct == pytest.approx((133.2695 / 168.9012 - 1) * 100)
    assert m.adr_gap_pct == pytest.approx((205.03 / 312.78 - 1) * 100)
    assert m.occupancy_gap_pp == pytest.approx(11.0)
