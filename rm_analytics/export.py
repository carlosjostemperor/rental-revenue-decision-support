"""Evidence export: one immutable folder per run with outputs, audit and a hashed manifest."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import platform
import subprocess
import sys
from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

from .audit import FAIL
from .pipeline import AnalysisResult, sha256_file

BOOKING_EXPORT_COLUMNS = [
    "booked_date", "check_in", "check_out", "nights", "los_reported", "lead_days",
    "booking_window_reported", "rental_revenue", "status_class",
]

DEFINITIONS = {
    "comp_prices": "Advertised nightly rates of manually selected comps that are available with price > 0 on the date; not realized ADR",
    "comp_percentiles": "Linear interpolation (Excel PERCENTILE.INC); equal weight per available listing",
    "gap_vs_median_pct": "(our advertised price / median available comp price - 1) * 100, per date; summary is the median across eligible dates",
    "gap_ci": "95% CI of the median daily gap from a weekly block bootstrap (dates within a week are correlated)",
    "gap_vs_all_priced_median_pct": "Sensitivity: same gap against all comps with a price, available or not",
    "booking_window": "Reservations filtered by Booked Date (creation date), inclusive, time of day ignored",
    "weighted_booking_adr": "sum(rental revenue) / sum(nights) for valid reservations created in the booking window",
    "market_adr": "PriceLabs Report Builder market benchmark, not derived from the manual comp set",
    "revpar_proxy": "ADR * occupancy / 100 using Report Builder Rental ADR and Adjusted Occupancy; market uses Market ADR * Market Occupancy",
    "stay_reconciliation": "Bookings allocated to stay dates (revenue spread evenly per night) and compared with Report Builder totals",
}


def _git_info(root: Path) -> dict:
    try:
        commit = subprocess.run(["git", "-C", str(root), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=5)
        dirty = subprocess.run(["git", "-C", str(root), "status", "--porcelain", "--", "rm_analytics"],
                               capture_output=True, text=True, timeout=5)
        if commit.returncode == 0:
            return {"commit": commit.stdout.strip(), "package_modified": bool(dirty.stdout.strip())}
    except (OSError, subprocess.SubprocessError):
        pass
    return {"commit": None, "package_modified": None}


def _package_hash() -> str:
    h = hashlib.sha256()
    for p in sorted(Path(__file__).parent.glob("*.py")):
        h.update(p.name.encode())
        h.update(p.read_bytes())
    return h.hexdigest()


def export_run(result: AnalysisResult, figures: dict | None = None, run_label: str = "") -> Path:
    """Write all evidence for the run and return the run folder.

    Inputs are re-hashed; if any file changed during the run a FAIL is recorded. Runs with FAIL
    checks are still exported (for traceability) into a folder ending in '_FAILED'.
    """
    from . import __version__

    cfg = result.cfg
    for key, path in result.input_paths.items():
        now = sha256_file(path)
        result.audit.require("governance", f"Input unchanged during run ({key})", now == result.input_hashes[key],
                             f"sha256 at load {result.input_hashes[key][:12]}..., at export {now[:12]}...", FAIL)

    status = result.audit.decision_status
    stamp = dt.datetime.now(dt.timezone.utc)
    seed = json.dumps([result.input_hashes, cfg.to_dict()], sort_keys=True, default=str).encode()
    run_id = f"{stamp:%Y%m%dT%H%M%SZ}_{hashlib.sha256(seed).hexdigest()[:8]}"
    if run_label:
        run_id += "_" + "".join(c if c.isalnum() or c in "-_" else "-" for c in run_label)
    if status == "FAILED":
        run_id += "_FAILED"
    elif status == "REVIEW_REQUIRED":
        run_id += "_REVIEW_REQUIRED"
    base = result.project_root / cfg.output_dir
    base.mkdir(parents=True, exist_ok=True)
    out, n = base / run_id, 1
    while True:  # never overwrite earlier evidence, even for two exports within the same second
        try:
            out.mkdir(exist_ok=False)
            break
        except FileExistsError:
            n += 1
            out = base / f"{run_id}_{n}"
    run_id = out.name

    tables = {
        "daily_positions.csv": result.positions.reset_index(),
        "minimum_stay_sensitivity.csv": _minimum_stay_sensitivity(result),
        "summary_metrics.csv": result.summary_table,
        "band_by_day_group.csv": result.band_by_day_group.reset_index(),
        "market_comparison.csv": result.market,
        "reconciliation.csv": result.reconciliation,
        "duplicate_listings.csv": result.duplicates,
        "booking_window_reservations.csv": result.window_bookings[BOOKING_EXPORT_COLUMNS],
        "audit_checks.csv": result.audit.to_frame(),
    }
    for name, frame in tables.items():
        frame.to_csv(out / name, index=False)
    (out / "position_summary.json").write_text(json.dumps(_clean(result.position_summary), indent=2, allow_nan=False))
    (out / "booking_summary.json").write_text(json.dumps(_clean(result.booking_summary), indent=2, allow_nan=False))
    for name, fig in (figures or {}).items():
        fig.savefig(out / f"{name}.png", dpi=150, bbox_inches="tight")

    decision_use = (
        "NOT FOR DECISIONS - audit failures" if status == "FAILED"
        else "NOT FOR DECISIONS - synthetic example" if cfg.is_synthetic_example
        else "REVIEW REQUIRED - resolve documented warnings before relying on this analysis" if status == "REVIEW_REQUIRED"
        else "VALIDATED ANALYTICAL CHECKS - human judgment and separate pricing approval still required"
    )
    _write_review_summary(out, result, status, decision_use)
    outputs = {p.name: sha256_file(p) for p in sorted(out.iterdir()) if p.is_file()}
    manifest = {
        "run_id": run_id,
        "status": status,
        "run_utc": stamp.isoformat(),
        "decision_use": decision_use,
        "eligible_for_analyst_review": status != "FAILED" and not cfg.is_synthetic_example,
        "approved_for_automated_price_changes": False,
        "outstanding_review_items": result.audit.review_items(),
        "code": {"package_version": __version__, "package_sha256": _package_hash(), **_git_info(result.project_root)},
        "environment": {
            "python": sys.version.split()[0], "platform": platform.platform(),
            "pandas": pd.__version__, "numpy": np.__version__, "matplotlib": matplotlib.__version__,
        },
        "config": cfg.to_dict(),
        "inputs": {k: {"file": p.name, "bytes": p.stat().st_size, "sha256": result.input_hashes[k]}
                   for k, p in result.input_paths.items()},
        "resolved": {"subject_listing": result.calendar.target, "comps": result.comps,
                     "dropped_duplicate_comps": result.dropped_comps,
                     "calendar_date_format": result.calendar.date_format,
                     "bookings_date_format": result.bookings.date_format},
        "audit": result.audit.counts(),
        "definitions": DEFINITIONS,
        "outputs_sha256": outputs,
    }
    (out / "run_manifest.json").write_text(json.dumps(_clean(manifest), indent=2, allow_nan=False), encoding="utf-8")
    return out


def _minimum_stay_sensitivity(result: AnalysisResult) -> pd.DataFrame:
    """Compare pricing-position summaries by minimum-stay comparability (not causation)."""
    p = result.eligible_positions
    groups = (
        ("matched", p.min_stay_matched),
        ("different", p.min_stay_differs),
        ("unknown", p.min_stay_unknown),
    )
    rows = []
    for name, mask in groups:
        subset = p.loc[mask]
        rows.append({
            "minimum_stay_group": name,
            "comparison_dates": len(subset),
            "median_gap_vs_comp_median_pct": float(subset.gap_vs_median_pct.median()) if len(subset) else float("nan"),
            "days_below_comp_median": int((subset.our_price < subset.comp_median).sum()),
            "share_below_comp_median_pct": (100 * float((subset.our_price < subset.comp_median).sum()) / len(subset)) if len(subset) else float("nan"),
            "median_available_comps": float(subset.n_comps.median()) if len(subset) else float("nan"),
        })
    return pd.DataFrame(rows)


def _write_review_summary(out: Path, result: AnalysisResult, status: str, decision_use: str) -> None:
    """Human-readable review queue, with the same gate as the machine manifest."""
    lines = [
        "# Run review summary", "", f"**Status:** {status}", f"**Decision use:** {decision_use}",
        "", "## Outstanding audit items", "",
    ]
    issues = result.audit.review_items()
    if issues:
        for i, entry in enumerate(issues, 1):
            lines.append(f"{i}. **{entry['status']} — {entry['category']} / {entry['check']}**: {entry['detail']}")
    else:
        lines.append("None. Automated checks passed. Human approval is still required for price changes.")
    lines += ["", "## Reviewer action", "", "Verify source periods, comparable listings, "
              "minimum-stay restrictions and the underlying PriceLabs definitions. "
              "Record any accepted exceptions outside this generated report. "
              "Re-run after correcting inputs or updating verified attestations.", ""]
    (out / "REVIEW_SUMMARY.md").write_text("\n".join(lines), encoding="utf-8")


def _clean(o):
    """Recursively convert values to strict-JSON types (NaN -> null)."""
    if isinstance(o, dict):
        return {str(k): _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (bool, np.bool_)):
        return bool(o)
    if isinstance(o, (int, np.integer)):
        return int(o)
    if isinstance(o, (float, np.floating)):
        return None if np.isnan(o) else float(o)
    if o is None or isinstance(o, str):
        return o
    return _json_default(o)


def _json_default(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return None if np.isnan(o) else float(o)
    if isinstance(o, (pd.Timestamp, dt.date)):
        return o.isoformat()
    if isinstance(o, float) and np.isnan(o):
        return None
    return str(o)
