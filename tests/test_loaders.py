import pandas as pd
import pytest

from rm_analytics.errors import ConfigError, DataValidationError
from rm_analytics.loaders import load_bookings, load_calendar, load_report_builder
from rm_analytics.synthetic import SYNTHETIC_TARGET

from conftest import make_cfg, read_calendar_raw, read_raw


# ---- Config --------------------------------------------------------------------------------
@pytest.mark.parametrize(
    "override, match",
    [
        ({"booking_start": "2026-11-05"}, "after"),
        ({"forward_start": "11/03/2026"}, "ISO"),
        ({"forward_start": "2026-02-30"}, "valid calendar date"),
        ({"min_active_comps": 0}, "min_active_comps"),
        ({"duplicate_policy": "ignore"}, "duplicate_policy"),
        ({"property_name": " "}, "property_name"),
        ({"historical_stay_end": "2026-11-05"}, "overlap"),
        ({"excluded_booking_statuses": ("booked",)}, "both valid and excluded"),
    ],
)
def test_invalid_config_rejected(tmp_path, override, match):
    with pytest.raises(ConfigError, match=match):
        make_cfg(tmp_path, **override)


# ---- Calendar ------------------------------------------------------------------------------
def test_calendar_loads_and_identifies_target(dataset):
    cal = load_calendar(dataset["data_dir"] / "competitor_calendar.csv", dataset["cfg"])
    assert cal.target == SYNTHETIC_TARGET
    assert len(cal.comps) == 10
    assert cal.date_format == "%d/%m/%Y"
    assert cal.frame.date.nunique() == 90


def test_calendar_us_date_format_is_detected(tmp_path):
    from rm_analytics.synthetic import generate_synthetic_dataset

    generate_synthetic_dataset(tmp_path, calendar_date_format="%m/%d/%Y")
    cal = load_calendar(tmp_path / "competitor_calendar.csv", make_cfg(tmp_path))
    assert cal.date_format == "%m/%d/%Y"
    assert cal.frame.date.min() == pd.Timestamp("2026-11-03")


def _mutate_calendar(dataset, fn):
    path = dataset["data_dir"] / "competitor_calendar.csv"
    raw = read_calendar_raw(path)
    raw = fn(raw)
    raw.to_csv(path, index=False, header=False)
    return path


def test_calendar_missing_date_row_is_rejected(dataset):
    path = _mutate_calendar(dataset, lambda r: r.drop(index=20))
    with pytest.raises(DataValidationError, match="missing dates"):
        load_calendar(path, dataset["cfg"])


def test_calendar_duplicate_date_is_rejected(dataset):
    path = _mutate_calendar(dataset, lambda r: pd.concat([r, r.iloc[[10]]]))
    with pytest.raises(DataValidationError):
        load_calendar(path, dataset["cfg"])


def test_calendar_bad_header_and_triplets(dataset):
    def bad_field(r):
        r.iloc[1, 2] = "availability"
        return r

    with pytest.raises(DataValidationError, match="expected"):
        load_calendar(_mutate_calendar(dataset, bad_field), dataset["cfg"])


def test_calendar_incomplete_triplet(dataset):
    with pytest.raises(DataValidationError, match="multiple of 3"):
        load_calendar(_mutate_calendar(dataset, lambda r: r.iloc[:, :-1]), dataset["cfg"])


def test_calendar_invalid_availability_and_price(dataset):
    def bad_avail(r):
        r.iloc[5, 5] = "maybe"
        return r

    with pytest.raises(DataValidationError, match="availability"):
        load_calendar(_mutate_calendar(dataset, bad_avail), dataset["cfg"])


def test_calendar_invalid_price_is_not_silently_dropped(tmp_path):
    from rm_analytics.synthetic import generate_synthetic_dataset

    generate_synthetic_dataset(tmp_path)
    path = tmp_path / "competitor_calendar.csv"
    raw = read_calendar_raw(path)
    raw.iloc[5, 4] = "four hundred"
    raw.to_csv(path, index=False, header=False)
    with pytest.raises(DataValidationError, match="prices"):
        load_calendar(path, make_cfg(tmp_path))


def test_calendar_duplicate_listing_name(dataset):
    def dup(r):
        r.iloc[0, 7] = r.iloc[0, 4]
        return r

    with pytest.raises(DataValidationError, match="appears twice"):
        load_calendar(_mutate_calendar(dataset, dup), dataset["cfg"])


def test_calendar_exclude_comps(dataset):
    cfg = make_cfg(dataset["data_dir"], exclude_comps=("Synthetic Comp 03",))
    cal = load_calendar(dataset["data_dir"] / "competitor_calendar.csv", cfg)
    assert "Synthetic Comp 03" not in cal.comps and len(cal.comps) == 9
    with pytest.raises(DataValidationError, match="not found"):
        load_calendar(dataset["data_dir"] / "competitor_calendar.csv", make_cfg(dataset["data_dir"], exclude_comps=("Nope",)))


# ---- Bookings ------------------------------------------------------------------------------
def _mutate_bookings(dataset, fn):
    path = dataset["data_dir"] / "bookings.csv"
    df = fn(read_raw(path))
    df.to_csv(path, index=False)
    return path


def test_bookings_currency_and_status(dataset):
    bd = load_bookings(dataset["data_dir"] / "bookings.csv", dataset["cfg"])
    assert bd.listing == SYNTHETIC_TARGET
    assert (bd.frame.status_class == "excluded").sum() == 3
    assert bd.frame.rental_revenue.notna().all()
    assert bd.frame["booked_date"].dt.hour.eq(0).all()  # normalized


def test_bookings_unknown_status_rejected(dataset):
    def f(df):
        df.loc[0, "Booking Status"] = "Pending review"
        return df

    with pytest.raises(DataValidationError, match="unrecognised Booking Status"):
        load_bookings(_mutate_bookings(dataset, f), dataset["cfg"])


def test_bookings_custom_status_whitelist(dataset):
    def f(df):
        df["Booking Status"] = df["Booking Status"].replace({"Booked": "Confirmed"})
        return df

    bd = load_bookings(_mutate_bookings(dataset, f), dataset["cfg"])
    assert (bd.frame.status_class == "valid").sum() == dataset["truth"]["valid_target_reservations"]


def test_bookings_missing_status_column_is_reported(dataset):
    bd = load_bookings(_mutate_bookings(dataset, lambda df: df.drop(columns="Booking Status")), dataset["cfg"])
    assert not bd.has_status_column and bd.notes


def test_bookings_missing_checkout_rejected(dataset):
    def f(df):
        df.loc[0, "Check-out Date"] = ""
        return df

    with pytest.raises(DataValidationError, match="missing"):
        load_bookings(_mutate_bookings(dataset, f), dataset["cfg"])


def test_bookings_checkout_before_checkin_rejected(dataset):
    def f(df):
        df.loc[0, "Check-out Date"] = df.loc[0, "Check-in Date"]
        return df

    with pytest.raises(DataValidationError, match="check-out not after"):
        load_bookings(_mutate_bookings(dataset, f), dataset["cfg"])


def test_bookings_booked_after_checkin_rejected(dataset):
    def f(df):
        df.loc[0, "Booked Date"] = "2027-03-01 10:00:00"
        return df

    with pytest.raises(DataValidationError, match="booked after check-in"):
        load_bookings(_mutate_bookings(dataset, f), dataset["cfg"])


def test_bookings_garbage_revenue_rejected(dataset):
    def f(df):
        df.loc[0, "Rental Revenue"] = "n/a dollars"
        return df

    with pytest.raises(DataValidationError, match="Rental Revenue"):
        load_bookings(_mutate_bookings(dataset, f), dataset["cfg"])


def test_bookings_ambiguous_listing_rejected(dataset):
    def f(df):
        extra = df.iloc[[0]].copy()
        extra["Listing Name"] = SYNTHETIC_TARGET + " - Unit B"
        return pd.concat([df, extra])

    cfg = make_cfg(dataset["data_dir"], property_name="SYNTHETIC 6BR")
    with pytest.raises(DataValidationError, match="several"):
        load_bookings(_mutate_bookings(dataset, f), cfg)


def test_bookings_missing_column_rejected(dataset):
    with pytest.raises(DataValidationError, match="missing required columns"):
        load_bookings(_mutate_bookings(dataset, lambda df: df.drop(columns="Rental Revenue")), dataset["cfg"])


# ---- Report Builder ------------------------------------------------------------------------
def test_report_builder_parses_formatted_values(dataset):
    rb = load_report_builder(dataset["data_dir"] / "report_builder_historical.csv", dataset["cfg"], "historical")
    assert rb.values["Rental ADR"] == pytest.approx(round(dataset["truth"]["historical"]["adr"], 2))
    assert rb.values["Market ADR"] == 540.0
    assert rb.values["Market Occupancy %"] == 54.0
    assert rb.missing_optional == []


def test_report_builder_missing_optional_is_reported_not_silent(dataset):
    path = dataset["data_dir"] / "report_builder_forward.csv"
    read_raw(path).drop(columns=["Rental RevPAR", "Average LOS"]).to_csv(path, index=False)
    rb = load_report_builder(path, dataset["cfg"], "forward")
    assert set(rb.missing_optional) == {"Rental RevPAR", "Average LOS"}


def test_report_builder_missing_required_and_bad_values(dataset):
    path = dataset["data_dir"] / "report_builder_forward.csv"
    df = read_raw(path)
    df.drop(columns=["Market ADR"]).to_csv(path, index=False)
    with pytest.raises(DataValidationError, match="missing required"):
        load_report_builder(path, dataset["cfg"], "forward")
    df.loc[1, "Market Occupancy %"] = "abc"
    df.to_csv(path, index=False)
    with pytest.raises(DataValidationError):
        load_report_builder(path, dataset["cfg"], "forward")


def test_report_builder_duplicate_rows_rejected(dataset):
    path = dataset["data_dir"] / "report_builder_forward.csv"
    df = read_raw(path)
    pd.concat([df, df.iloc[[1]]]).to_csv(path, index=False)
    with pytest.raises(DataValidationError, match="exactly one row"):
        load_report_builder(path, dataset["cfg"], "forward")
