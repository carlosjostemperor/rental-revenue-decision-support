import numpy as np
import pandas as pd
import pytest

from rm_analytics.errors import DataValidationError
from rm_analytics.parsing import (
    parse_currency,
    parse_dates,
    parse_number,
    parse_occupancy_pct,
    resolve_listing,
)


# ---- Currency (audit finding #2: "$1,234.00" silently became NaN) -------------------------
def test_currency_formats_are_parsed_not_dropped():
    s = pd.Series(["$1,234.00", "500", " USD 2,000.50 ", "(45.00)", "-$10", "$0.99"])
    out = parse_currency(s, "rev")
    assert out.tolist() == [1234.0, 500.0, 2000.5, -45.0, -10.0, 0.99]
    assert out.sum() == pytest.approx(3680.49)


def test_currency_rejects_unparseable_values():
    with pytest.raises(DataValidationError, match="not valid numbers"):
        parse_currency(pd.Series(["$100", "abc"]), "rev")


def test_currency_rejects_european_format_instead_of_misreading():
    with pytest.raises(DataValidationError):
        parse_currency(pd.Series(["1.234,50"]), "rev")
    with pytest.raises(DataValidationError):
        parse_currency(pd.Series(["12,34"]), "rev")


def test_currency_missing_policy():
    assert np.isnan(parse_currency(pd.Series(["", "100"]), "rev").iloc[0])
    with pytest.raises(DataValidationError, match="missing"):
        parse_currency(pd.Series(["", "100"]), "rev", allow_missing=False)


def test_number_rejects_currency_symbols():
    with pytest.raises(DataValidationError):
        parse_number(pd.Series(["$5"]), "nights")


# ---- Occupancy ----------------------------------------------------------------------------
def test_occupancy_percent_strings_and_numbers():
    v, notes = parse_occupancy_pct(pd.Series(["65%", "54.5"]), "occ")
    assert v.tolist() == [65.0, 54.5] and notes == []


def test_occupancy_fraction_detected_and_reported():
    v, notes = parse_occupancy_pct(pd.Series(["0.65"]), "occ")
    assert v.iloc[0] == pytest.approx(65.0) and notes


def test_occupancy_out_of_range():
    with pytest.raises(DataValidationError, match="outside"):
        parse_occupancy_pct(pd.Series(["120%"]), "occ")


# ---- Dates (findings #3, #4, #5) ------------------------------------------------------------
def test_dates_with_time_are_normalized_and_inclusive_filter_works():
    d, _ = parse_dates(pd.Series(["2026-11-02 14:30:00"]), "booked")
    assert d.iloc[0] == pd.Timestamp("2026-11-02")
    assert d.between(pd.Timestamp("2026-10-11"), pd.Timestamp("2026-11-02")).all()


def test_mixed_date_and_datetime_strings_do_not_become_nat():
    d, fmt = parse_dates(pd.Series(["2026-11-02 14:30", "2026-11-02", "2026-10-01T08:00:00"]), "booked")
    assert d.notna().all() and fmt == "%Y-%m-%d"


def test_us_dates_parsed_month_first_when_unambiguous():
    d, fmt = parse_dates(pd.Series(["11/05/2026", "11/25/2026"]), "x")
    assert fmt == "%m/%d/%Y"
    assert d.tolist() == [pd.Timestamp("2026-11-05"), pd.Timestamp("2026-11-25")]


def test_day_first_dates_parsed_when_unambiguous():
    d, fmt = parse_dates(pd.Series(["25/11/2026", "05/12/2026"]), "x")
    assert fmt == "%d/%m/%Y" and d.iloc[1] == pd.Timestamp("2026-12-05")


def test_ambiguous_dates_raise_unless_consecutive_sequence_resolves_them():
    s = pd.Series(["01/02/2026", "02/02/2026", "03/02/2026"])  # day-first is consecutive
    with pytest.raises(DataValidationError, match="ambiguous"):
        parse_dates(s, "x")
    d, fmt = parse_dates(s, "x", expect_consecutive=True)
    assert fmt == "%d/%m/%Y" and d.iloc[0] == pd.Timestamp("2026-02-01")


def test_explicit_format_mismatch_raises():
    with pytest.raises(DataValidationError, match="do not match"):
        parse_dates(pd.Series(["11/25/2026"]), "x", fmt="%d/%m/%Y")


def test_missing_and_garbage_dates_raise():
    with pytest.raises(DataValidationError, match="missing"):
        parse_dates(pd.Series(["2026-01-01", ""]), "x")
    with pytest.raises(DataValidationError, match="unsupported"):
        parse_dates(pd.Series(["Nov 3 2026"]), "x")
    with pytest.raises(DataValidationError, match="mixes"):
        parse_dates(pd.Series(["2026-01-01", "01/02/2026"]), "x")


# ---- Listing resolution (finding #7) --------------------------------------------------------
def test_exact_match_preferred_over_partial():
    assert resolve_listing(["Home A", "Home A - Unit B"], "home a", "src") == "Home A"


def test_ambiguous_and_missing_listing_raise():
    with pytest.raises(DataValidationError, match="several"):
        resolve_listing(["Home A1", "Home A2"], "Home A", "src")
    with pytest.raises(DataValidationError, match="no listing"):
        resolve_listing(["Other"], "Home A", "src")
