"""Loaders for the four PriceLabs exports. Each returns clean, typed data or raises DataValidationError."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

from .config import AnalysisConfig
from .errors import DataValidationError
from .parsing import (
    _as_clean_strings,
    parse_currency,
    parse_dates,
    parse_number,
    parse_occupancy_pct,
    read_csv_text,
    resolve_listing,
)

CALENDAR_FIELDS = ["prices", "available", "min_stay"]
AVAILABILITY_MAP = {
    "1": 1, "1.0": 1, "true": 1, "yes": 1, "y": 1, "available": 1, "t": 1,
    "0": 0, "0.0": 0, "false": 0, "no": 0, "n": 0, "unavailable": 0, "booked": 0, "blocked": 0, "f": 0,
}


@dataclass
class CalendarData:
    frame: pd.DataFrame  # long format: date, listing, advertised_price, available, minimum_stay
    target: str
    comps: list
    date_format: str
    notes: list = field(default_factory=list)


@dataclass
class BookingsData:
    frame: pd.DataFrame  # all reservations of the subject listing, typed, with status_class
    listing: str
    date_format: str
    has_status_column: bool
    has_booking_window: bool
    reservation_id_column: str | None
    notes: list = field(default_factory=list)


@dataclass
class ReportBuilderRow:
    label: str
    listing: str
    values: dict
    missing_optional: list
    notes: list = field(default_factory=list)


# --------------------------------------------------------------------------------------------
# Competitor calendar
# --------------------------------------------------------------------------------------------
def load_calendar(path: Path | str, cfg: AnalysisConfig) -> CalendarData:
    raw = read_csv_text(path, header=None)
    raw = raw.replace("", np.nan).dropna(axis=1, how="all").dropna(axis=0, how="all").reset_index(drop=True)
    notes: list = []
    if raw.shape[0] < 4 or raw.shape[1] < 4:
        raise DataValidationError("Competitor calendar: too few rows/columns for the 3-row PriceLabs header")
    if str(raw.iloc[2, 0]).strip().casefold() != "date":
        raise DataValidationError("Competitor calendar: 'Date' header not found in row 3, column 1")
    if (raw.shape[1] - 1) % 3 != 0:
        raise DataValidationError(
            f"Competitor calendar: {raw.shape[1] - 1} data columns is not a multiple of 3 "
            "(prices, available, min_stay per listing)"
        )

    body = raw.iloc[3:].reset_index(drop=True)
    dates, fmt = parse_dates(
        body.iloc[:, 0], "Competitor calendar Date", cfg.calendar_date_format, expect_consecutive=True
    )
    if dates.duplicated().any():
        raise DataValidationError(f"Competitor calendar: duplicated dates {_dup_examples(dates)}")
    if not dates.is_monotonic_increasing:
        order = dates.sort_values()
        if not (order.diff().dropna() == pd.Timedelta(days=1)).all():
            raise DataValidationError("Competitor calendar: dates are not a continuous daily sequence")
        notes.append("Calendar rows were not in date order; they were sorted")
    elif not (dates.diff().dropna() == pd.Timedelta(days=1)).all():
        gaps = dates[dates.diff() > pd.Timedelta(days=1)]
        raise DataValidationError(
            f"Competitor calendar: missing dates before {[d.date().isoformat() for d in gaps[:5]]}"
        )

    names: list = []
    records = []
    for start in range(1, raw.shape[1], 3):
        name = str(raw.iloc[0, start]).strip() if pd.notna(raw.iloc[0, start]) else ""
        if not name:
            raise DataValidationError(f"Competitor calendar: blank listing name at column {start + 1}")
        fields = [str(raw.iloc[1, j]).strip().casefold() for j in range(start, start + 3)]
        if fields != CALENDAR_FIELDS:
            raise DataValidationError(f"Competitor calendar: fields for {name!r} are {fields}; expected {CALENDAR_FIELDS}")
        if name in names:
            raise DataValidationError(f"Competitor calendar: listing name {name!r} appears twice")
        names.append(name)

        price = parse_currency(body.iloc[:, start], f"{name} prices")
        avail_txt, avail_missing = _as_clean_strings(body.iloc[:, start + 1])
        available = avail_txt.str.casefold().map(AVAILABILITY_MAP)
        bad = ~avail_missing & available.isna()
        if bad.any():
            raise DataValidationError(
                f"Competitor calendar: invalid availability values for {name!r}: "
                f"{avail_txt[bad].unique().tolist()[:5]}"
            )
        min_stay = parse_number(body.iloc[:, start + 2], f"{name} min_stay")
        if (min_stay.dropna() < 0).any():
            raise DataValidationError(f"Competitor calendar: negative min_stay for {name!r}")
        if (price.dropna() < 0).any():
            raise DataValidationError(f"Competitor calendar: negative price for {name!r}")
        records.append(
            pd.DataFrame(
                {
                    "date": dates.values,
                    "listing": name,
                    "advertised_price": price.values,
                    "available": pd.array(available, dtype="Int64"),
                    "minimum_stay": min_stay.values,
                }
            )
        )

    frame = pd.concat(records, ignore_index=True).sort_values(["date", "listing"]).reset_index(drop=True)
    target = resolve_listing(names, cfg.property_name, "Competitor calendar")
    unknown_excl = [c for c in cfg.exclude_comps if c not in names]
    if unknown_excl:
        raise DataValidationError(f"exclude_comps not found in calendar: {unknown_excl}")
    if target in cfg.exclude_comps:
        raise DataValidationError("exclude_comps cannot contain the subject listing")
    if cfg.exclude_comps:
        frame = frame[~frame.listing.isin(cfg.exclude_comps)].reset_index(drop=True)
        notes.append(f"Excluded by configuration: {list(cfg.exclude_comps)}")
    comps = [n for n in names if n != target and n not in cfg.exclude_comps]
    if not comps:
        raise DataValidationError("Competitor calendar: no competitor listings")
    return CalendarData(frame=frame, target=target, comps=comps, date_format=fmt, notes=notes)


def _dup_examples(dates: pd.Series) -> list:
    return [d.date().isoformat() for d in dates[dates.duplicated()].unique()[:5]]


# --------------------------------------------------------------------------------------------
# Bookings report
# --------------------------------------------------------------------------------------------
BOOKING_REQUIRED = ["Listing Name", "Booked Date", "Check-in Date", "Check-out Date", "Rental Revenue", "Length of Stay (Days)"]
RESERVATION_ID_CANDIDATES = ["Reservation ID", "Reservation Id", "Booking ID", "Booking Id", "Confirmation Code"]


def load_bookings(path: Path | str, cfg: AnalysisConfig) -> BookingsData:
    df = read_csv_text(path)
    missing_cols = [c for c in BOOKING_REQUIRED if c not in df.columns]
    if missing_cols:
        raise DataValidationError(f"Bookings report: missing required columns {missing_cols}")
    notes: list = []

    listing = resolve_listing(df["Listing Name"], cfg.property_name, "Bookings report")
    b = df[df["Listing Name"].astype(str).str.strip() == listing].copy().reset_index(drop=True)
    b["source_row"] = b.index + 2  # 1-based incl. header, approximate after filtering
    if b.empty:
        raise DataValidationError(f"Bookings report: no rows for {listing!r}")

    fmt_used = None
    for col, key in (("Booked Date", "booked_date"), ("Check-in Date", "check_in"), ("Check-out Date", "check_out")):
        parsed, fmt = parse_dates(b[col], f"Bookings {col}", cfg.bookings_date_format)
        b[key] = parsed
        fmt_used = fmt_used or fmt
    b["rental_revenue"] = parse_currency(b["Rental Revenue"], "Bookings Rental Revenue", allow_missing=False)
    b["los_reported"] = parse_number(b["Length of Stay (Days)"], "Bookings Length of Stay (Days)", allow_missing=False)

    has_window = "Booking Window (Days)" in b.columns
    if has_window:
        b["booking_window_reported"] = parse_number(b["Booking Window (Days)"], "Bookings Booking Window (Days)")
    else:
        b["booking_window_reported"] = np.nan
        notes.append("Bookings report has no 'Booking Window (Days)' column; lead time is computed only")

    has_status = "Booking Status" in b.columns
    if has_status:
        status, status_missing = _as_clean_strings(b["Booking Status"])
        status_cf = status.str.casefold()
        b["status_class"] = np.select(
            [status_cf.isin(cfg.valid_booking_statuses).fillna(False), status_cf.isin(cfg.excluded_booking_statuses).fillna(False)],
            ["valid", "excluded"],
            default="unknown",
        )
        unknown = b["status_class"].eq("unknown")
        if unknown.any():
            raise DataValidationError(
                "Bookings report: unrecognised Booking Status values "
                f"{status[unknown].fillna('<blank>').unique().tolist()}. Add them to valid_booking_statuses "
                "or excluded_booking_statuses."
            )
    else:
        b["status_class"] = "valid"
        notes.append("Bookings report has no 'Booking Status' column; cancellations cannot be excluded")

    b["nights"] = (b["check_out"] - b["check_in"]).dt.days
    bad_nights = b["nights"] <= 0
    if bad_nights.any():
        raise DataValidationError(
            f"Bookings report: check-out not after check-in on rows {b.loc[bad_nights, 'source_row'].tolist()[:10]}"
        )
    b["lead_days"] = (b["check_in"] - b["booked_date"]).dt.days
    neg_lead = (b["lead_days"] < 0) & b["status_class"].eq("valid")
    if neg_lead.any():
        raise DataValidationError(
            f"Bookings report: booked after check-in on rows {b.loc[neg_lead, 'source_row'].tolist()[:10]}"
        )
    neg_rev = (b["rental_revenue"] < 0) & b["status_class"].eq("valid")
    if neg_rev.any():
        raise DataValidationError(
            f"Bookings report: negative Rental Revenue on valid reservations, rows {b.loc[neg_rev, 'source_row'].tolist()[:10]}"
        )

    id_col = next((c for c in RESERVATION_ID_CANDIDATES if c in b.columns), None)
    return BookingsData(
        frame=b,
        listing=listing,
        date_format=fmt_used,
        has_status_column=has_status,
        has_booking_window=has_window,
        reservation_id_column=id_col,
        notes=notes,
    )


# --------------------------------------------------------------------------------------------
# Report Builder
# --------------------------------------------------------------------------------------------
RB_REQUIRED_MONEY = ["Rental ADR", "Market ADR"]
RB_REQUIRED_OCC = ["Adjusted Occupancy %", "Market Occupancy %"]
RB_OPTIONAL_MONEY = ["Rental Revenue", "Rental RevPAR"]
RB_OPTIONAL_NUMBER = [
    "Booked Nights",
    "Number of Bookings",
    "Booked Nights Pickup (30 Days)",
    "Booked Nights Pickup (7 Days)",
    "Average Booking Window",
    "Average LOS",
]


def load_report_builder(path: Path | str, cfg: AnalysisConfig, label: str) -> ReportBuilderRow:
    df = read_csv_text(path)
    source = f"Report Builder ({label})"
    required = ["Listing Name", *RB_REQUIRED_MONEY, *RB_REQUIRED_OCC]
    missing = [c for c in required if c not in df.columns]
    if missing:
        raise DataValidationError(f"{source}: missing required columns {missing}")
    listing = resolve_listing(df["Listing Name"], cfg.property_name, source)
    rows = df[df["Listing Name"].astype(str).str.strip() == listing]
    if len(rows) != 1:
        raise DataValidationError(f"{source}: expected exactly one row for {listing!r}, found {len(rows)}")
    row = rows.iloc[[0]]
    values: dict = {}
    notes: list = []
    for col in RB_REQUIRED_MONEY:
        values[col] = float(parse_currency(row[col], f"{source} {col}", allow_missing=False).iloc[0])
    for col in RB_REQUIRED_OCC:
        v, n = parse_occupancy_pct(row[col], f"{source} {col}", allow_missing=False)
        values[col] = float(v.iloc[0])
        notes.extend(n)
    missing_optional = []
    for col in RB_OPTIONAL_MONEY + RB_OPTIONAL_NUMBER:
        if col not in df.columns:
            missing_optional.append(col)
            values[col] = np.nan
            continue
        parser = parse_currency if col in RB_OPTIONAL_MONEY else parse_number
        values[col] = float(parser(row[col], f"{source} {col}").iloc[0])
    if values["Market ADR"] <= 0:
        raise DataValidationError(f"{source}: Market ADR must be > 0, got {values['Market ADR']}")
    if values["Rental ADR"] < 0:
        raise DataValidationError(f"{source}: Rental ADR is negative ({values['Rental ADR']})")
    if values["Rental ADR"] == 0:
        values["Rental ADR"] = np.nan
        notes.append(f"{source}: Rental ADR is 0 (no booked nights?); ADR comparison is undefined for this period")
    return ReportBuilderRow(label=label, listing=listing, values=values, missing_optional=missing_optional, notes=notes)
