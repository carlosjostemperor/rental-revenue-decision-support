"""Strict parsers for the value formats found in PriceLabs exports.

Design rule: a non-empty value that cannot be parsed unambiguously raises DataValidationError.
Nothing is silently converted to NaN (the root cause of several audit findings).
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .errors import DataValidationError

MISSING_TOKENS = {"", "nan", "none", "null", "n/a", "na", "-", "--"}

_PLAIN_NUMBER = re.compile(r"^-?\d+(\.\d+)?$")
_THOUSANDS_NUMBER = re.compile(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$")


def _examples(values: pd.Series, limit: int = 5) -> list:
    return values.dropna().astype(str).unique().tolist()[:limit]


def _as_clean_strings(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    """Return stripped strings and a mask of values that count as missing."""
    s = series.astype("string").str.strip()
    missing = s.isna() | s.str.casefold().isin(MISSING_TOKENS)
    return s, missing.fillna(True).astype(bool)


def read_csv_text(path: Path | str, header: str | None = "infer") -> pd.DataFrame:
    """Read a CSV as strings with delimiter detection (',' or ';') and BOM handling."""
    path = Path(path)
    if not path.is_file():
        raise DataValidationError(f"Input file not found: {path}")
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        sample = fh.read(16384)
    if not sample.strip():
        raise DataValidationError(f"Input file is empty: {path}")
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=";,").delimiter
    except csv.Error:
        delimiter = ";" if sample.count(";") > sample.count(",") else ","
    frame = pd.read_csv(
        path,
        header=0 if header == "infer" else None,
        sep=delimiter,
        dtype=str,
        encoding="utf-8-sig",
        keep_default_na=False,
        skip_blank_lines=True,
    )
    if header == "infer":
        frame.columns = [str(c).strip() for c in frame.columns]
        dupes = frame.columns[frame.columns.duplicated()].tolist()
        if dupes:
            raise DataValidationError(f"{path.name}: duplicated column names {dupes}")
    return frame


def parse_number(series: pd.Series, field: str, allow_missing: bool = True) -> pd.Series:
    """Parse plain numbers (thousands separators allowed). Currency or % symbols are rejected."""
    return _parse_numeric(series, field, allow_missing, strip_symbols="")


def parse_currency(series: pd.Series, field: str, allow_missing: bool = True) -> pd.Series:
    """Parse money values such as '1234.5', '$1,234.50', 'USD 1,234', '(45.00)' (negative).

    European formats like '1.234,50' are rejected instead of being misread.
    """
    return _parse_numeric(series, field, allow_missing, strip_symbols="$€£")


def _parse_numeric(series: pd.Series, field: str, allow_missing: bool, strip_symbols: str) -> pd.Series:
    s, missing = _as_clean_strings(series)
    cleaned = s.copy()
    if strip_symbols:
        cleaned = cleaned.str.replace(r"(?i)\b(usd|eur|gbp)\b", "", regex=True)
        cleaned = cleaned.str.replace(f"[{re.escape(strip_symbols)}]", "", regex=True)
    cleaned = cleaned.str.replace(r"\s+", "", regex=True)
    negative = cleaned.str.startswith("(") & cleaned.str.endswith(")")
    cleaned = cleaned.where(~negative.fillna(False), cleaned.str.slice(1, -1))
    # Move a leading minus that preceded a stripped currency symbol ("-$45" -> "-45" already).
    valid_shape = cleaned.str.match(_PLAIN_NUMBER) | cleaned.str.match(_THOUSANDS_NUMBER)
    bad = ~missing & ~valid_shape.fillna(False)
    if bad.any():
        raise DataValidationError(
            f"{field}: {int(bad.sum())} value(s) are not valid numbers, e.g. {_examples(s[bad])}"
        )
    numeric = pd.to_numeric(cleaned.str.replace(",", "", regex=False).where(~missing), errors="raise")
    numeric = numeric.astype(float)
    numeric = numeric.where(~negative.fillna(False), -numeric)
    if not allow_missing and missing.any():
        raise DataValidationError(f"{field}: {int(missing.sum())} required value(s) are missing")
    return numeric


def parse_occupancy_pct(series: pd.Series, field: str, allow_missing: bool = True) -> tuple[pd.Series, list]:
    """Parse occupancy into percentage points (0-100).

    Accepts '65%', '65', '65.0'. If no value carries a '%' sign and every non-zero value is <= 1,
    the column is interpreted as a fraction and multiplied by 100; this is reported in the notes.
    """
    s, missing = _as_clean_strings(series)
    has_pct = s.str.endswith("%").fillna(False)
    values = parse_number(s.str.rstrip("%"), field, allow_missing=allow_missing)
    notes = []
    non_zero = values[(values != 0) & values.notna()]
    if not has_pct.any() and len(non_zero) and (non_zero.abs() <= 1).all():
        values = values * 100
        notes.append(f"{field}: values had no '%' sign and were all <= 1; interpreted as fractions")
    out_of_range = values.notna() & ((values < 0) | (values > 100))
    if out_of_range.any():
        raise DataValidationError(f"{field}: occupancy outside 0-100%: {_examples(values[out_of_range])}")
    return values, notes


# --------------------------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------------------------
_DATE_TOKEN = re.compile(r"^(\d{4}-\d{1,2}-\d{1,2}|\d{1,2}[/.\-]\d{1,2}[/.\-]\d{2,4})(?:[ T].*)?$")


def _is_consecutive_daily(values: pd.Series) -> bool:
    d = values.dropna()
    if len(d) < 2:
        return True
    diffs = d.diff().dropna()
    return bool((diffs == pd.Timedelta(days=1)).all())


def parse_dates(
    series: pd.Series,
    field: str,
    fmt: str = "auto",
    allow_missing: bool = False,
    expect_consecutive: bool = False,
) -> tuple[pd.Series, str]:
    """Parse dates and return (normalized datetime64 series, format used).

    * Time of day is discarded: every value is normalized to midnight, so inclusive date filters
      include bookings made at any time on the last day.
    * 'auto' supports ISO (YYYY-MM-DD with optional time) and numeric day/month orders. When both
      day-first and month-first parse successfully and give different dates, the order is resolved by
      ``expect_consecutive`` (calendar files must be daily sequences); otherwise a
      DataValidationError asks the analyst to set the format explicitly.
    """
    s, missing = _as_clean_strings(series)
    if not allow_missing and missing.any():
        raise DataValidationError(f"{field}: {int(missing.sum())} required date value(s) are missing")

    if fmt != "auto":
        parsed = pd.to_datetime(s.where(~missing), format=fmt, errors="coerce")
        bad = ~missing & parsed.isna()
        if bad.any():
            raise DataValidationError(
                f"{field}: {int(bad.sum())} value(s) do not match format {fmt!r}, e.g. {_examples(s[bad])}"
            )
        return parsed.dt.normalize(), fmt

    tokens = s.str.extract(_DATE_TOKEN, expand=False)
    unsupported = ~missing & tokens.isna()
    if unsupported.any():
        raise DataValidationError(
            f"{field}: unsupported date format, e.g. {_examples(s[unsupported])}. "
            "Set the explicit date format in the configuration."
        )
    present = tokens[~missing]
    iso = present.str.match(r"^\d{4}-")
    if iso.all():
        parsed = pd.to_datetime(tokens.where(~missing), format="%Y-%m-%d", errors="coerce")
        bad = ~missing & parsed.isna()
        if bad.any():
            raise DataValidationError(f"{field}: invalid ISO dates, e.g. {_examples(s[bad])}")
        return parsed.dt.normalize(), "%Y-%m-%d"
    if iso.any():
        raise DataValidationError(f"{field}: mixes ISO and day/month date styles, e.g. {_examples(present)}")

    sep = present.str.extract(r"^\d{1,2}([/.\-])", expand=False).unique()
    if len(sep) != 1:
        raise DataValidationError(f"{field}: mixed date separators {list(sep)}")
    sep = sep[0]
    year_len = present.str.extract(r"(\d+)$", expand=False).str.len().unique()
    if len(year_len) != 1 or year_len[0] not in (2, 4):
        raise DataValidationError(f"{field}: inconsistent year lengths in dates")
    y = "%Y" if year_len[0] == 4 else "%y"
    candidates = {f"%m{sep}%d{sep}{y}": None, f"%d{sep}%m{sep}{y}": None}
    for cand in candidates:
        parsed = pd.to_datetime(tokens.where(~missing), format=cand, errors="coerce")
        if not (~missing & parsed.isna()).any():
            candidates[cand] = parsed
    ok = {k: v for k, v in candidates.items() if v is not None}
    if not ok:
        raise DataValidationError(f"{field}: dates do not parse as day-first or month-first, e.g. {_examples(present)}")
    if len(ok) == 1:
        fmt_used, parsed = next(iter(ok.items()))
        return parsed.dt.normalize(), fmt_used
    (f1, p1), (f2, p2) = ok.items()
    if p1.equals(p2):
        return p1.dt.normalize(), f1
    if expect_consecutive:
        consecutive = {k: v for k, v in ok.items() if _is_consecutive_daily(v.dropna())}
        if len(consecutive) == 1:
            fmt_used, parsed = next(iter(consecutive.items()))
            return parsed.dt.normalize(), fmt_used
    raise DataValidationError(
        f"{field}: ambiguous dates (both day-first and month-first are valid), e.g. {_examples(present)}. "
        "Set the explicit date format in the configuration."
    )


def resolve_listing(names, property_name: str, source: str) -> str:
    """Resolve the subject listing among names.

    An exact (case-insensitive) match wins. Otherwise exactly one substring match is required.
    """
    unique = sorted({str(n).strip() for n in names if str(n).strip()})
    key = property_name.casefold()
    exact = [n for n in unique if n.casefold() == key]
    if len(exact) == 1:
        return exact[0]
    partial = [n for n in unique if key in n.casefold()]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        raise DataValidationError(f"{source}: no listing matches property_name {property_name!r}")
    raise DataValidationError(
        f"{source}: property_name {property_name!r} matches several listings {partial}; "
        "use the exact listing name"
    )


def safe_log_ratio(numer: pd.Series, denom: pd.Series) -> pd.Series:
    with np.errstate(divide="ignore", invalid="ignore"):
        out = np.log(numer.astype(float) / denom.astype(float))
    return pd.Series(out, index=numer.index).replace([np.inf, -np.inf], np.nan)
