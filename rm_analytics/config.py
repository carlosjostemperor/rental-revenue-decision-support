"""Run configuration with up-front validation."""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import pandas as pd

from .errors import ConfigError

_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

INPUT_FILES = {
    "calendar": "competitor_calendar.csv",
    "bookings": "bookings.csv",
    "historical": "report_builder_historical.csv",
    "forward": "report_builder_forward.csv",
}


def _parse_config_date(name: str, value: str) -> pd.Timestamp:
    if not isinstance(value, str) or not _ISO_DATE.match(value):
        raise ConfigError(f"{name} must be an ISO date string 'YYYY-MM-DD'; got {value!r}")
    try:
        return pd.Timestamp(value)
    except ValueError as exc:  # e.g. 2026-02-30
        raise ConfigError(f"{name} is not a valid calendar date: {value!r}") from exc


@dataclass
class AnalysisConfig:
    """All analyst-controlled settings for one run.

    Date windows are inclusive on both ends and refer to calendar dates (time of day is ignored).
    """

    # --- Subject property and windows -------------------------------------------------------
    property_name: str
    booking_start: str  # Booked Date (reservation creation) window
    booking_end: str
    historical_stay_start: str  # Stay-date window used in the historical Report Builder export
    historical_stay_end: str
    forward_start: str  # Stay-date window used in the forward Report Builder export and calendar
    forward_end: str

    # --- Locations -----------------------------------------------------------------------
    data_dir: str = "data/input"
    output_dir: str = "output"

    # --- Method parameters ---------------------------------------------------------------
    min_active_comps: int = 5
    calendar_date_format: str = "auto"  # 'auto' or an explicit strftime format, e.g. '%d/%m/%Y'
    bookings_date_format: str = "auto"
    valid_booking_statuses: tuple = ("booked", "confirmed", "accepted", "active", "reserved")
    excluded_booking_statuses: tuple = (
        "cancelled",
        "canceled",
        "declined",
        "denied",
        "expired",
        "inquiry",
        "withdrawn",
    )
    duplicate_policy: str = "warn"  # 'warn' keeps flagged comps; 'drop' removes the second listing of a pair
    duplicate_corr_threshold: float = 0.98
    duplicate_max_median_abs_diff_pct: float = 3.0
    duplicate_min_availability_agreement: float = 0.90
    duplicate_min_overlap_days: int = 14
    exclude_comps: tuple = ()
    reconciliation_tolerance_pct: float = 2.0
    bootstrap_iterations: int = 2000
    random_seed: int = 42
    report_currency: str = "USD"

    # --- Governance: explicit, recorded human attestations ----------------------------------
    analyst: str = ""
    reviewer: str = ""
    attest_report_periods_verified: bool = False
    attest_comp_set_reviewed: bool = False
    attest_storage_approved: bool = False
    is_synthetic_example: bool = False

    # --- Derived (not set by users) --------------------------------------------------------
    _dates: dict = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self) -> None:
        if not isinstance(self.property_name, str) or not self.property_name.strip():
            raise ConfigError("property_name must be a non-empty string")
        self.property_name = self.property_name.strip()

        for name in (
            "booking_start",
            "booking_end",
            "historical_stay_start",
            "historical_stay_end",
            "forward_start",
            "forward_end",
        ):
            self._dates[name] = _parse_config_date(name, getattr(self, name))
        for start, end in (
            ("booking_start", "booking_end"),
            ("historical_stay_start", "historical_stay_end"),
            ("forward_start", "forward_end"),
        ):
            if self._dates[start] > self._dates[end]:
                raise ConfigError(f"{start} ({getattr(self, start)}) is after {end} ({getattr(self, end)})")
        if self._dates["historical_stay_end"] >= self._dates["forward_start"]:
            raise ConfigError("historical_stay_end must be before forward_start; the windows must not overlap")

        if not isinstance(self.min_active_comps, int) or self.min_active_comps < 1:
            raise ConfigError("min_active_comps must be an integer >= 1")
        if self.duplicate_policy not in {"warn", "drop"}:
            raise ConfigError("duplicate_policy must be 'warn' or 'drop'")
        if not 0 < self.duplicate_corr_threshold <= 1:
            raise ConfigError("duplicate_corr_threshold must be in (0, 1]")
        if self.reconciliation_tolerance_pct < 0:
            raise ConfigError("reconciliation_tolerance_pct must be >= 0")
        if self.bootstrap_iterations < 0:
            raise ConfigError("bootstrap_iterations must be >= 0")

        self.valid_booking_statuses = tuple(s.strip().casefold() for s in self.valid_booking_statuses)
        self.excluded_booking_statuses = tuple(s.strip().casefold() for s in self.excluded_booking_statuses)
        overlap = set(self.valid_booking_statuses) & set(self.excluded_booking_statuses)
        if overlap:
            raise ConfigError(f"Statuses cannot be both valid and excluded: {sorted(overlap)}")
        if not self.valid_booking_statuses:
            raise ConfigError("valid_booking_statuses cannot be empty")
        self.exclude_comps = tuple(self.exclude_comps)

    # ---------------------------------------------------------------------------------------
    def ts(self, name: str) -> pd.Timestamp:
        """Parsed timestamp for a configured date field."""
        return self._dates[name]

    def days_in(self, start: str, end: str) -> int:
        """Inclusive number of calendar days between two configured date fields."""
        return int((self.ts(end) - self.ts(start)).days) + 1

    def input_paths(self, project_root: Path | str = ".") -> dict:
        base = Path(project_root) / self.data_dir
        return {key: base / name for key, name in INPUT_FILES.items()}

    def to_dict(self) -> dict:
        data = asdict(self)
        data.pop("_dates", None)
        return data
